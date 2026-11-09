"""时间线完整性人工离线反例；不读取私有验收文件或实际Secrets。"""
from copy import deepcopy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from docx import Document
from ai_analysis import (AIError,PROMPT,empty_analysis,build_sources,validate_analysis,
                         analyze_record,_apply_output_quality)
from core import extract
from live_acceptance import load_scenarios,automatic_checks
from sample_debug import fixed_record


class TimelineCompletenessTests(unittest.TestCase):
    def setUp(self):self.record=fixed_record('SIM_B')

    def row(self,source,*,kind='事实',text=None,reasoning=''):
        source=next(s for s in build_sources(self.record) if s['source_id']==source)
        quote=source['text']
        return {'kind':kind,'text':quote if text is None else text,'reasoning':reasoning,
                'sources':[{'source_id':source['source_id'],'quote':quote}]}

    def event(self,source,*,time=None,kind='事实'):
        row=self.row(source,kind=kind);ref=deepcopy(row['sources'][0])
        row.update(event_source=ref,time_source=ref if time else None,
                   time_state='explicit' if time else 'unknown',time_precision='date' if time else 'unknown',
                   time_text=time or '未知')
        return row

    def question(self,source='S002'):
        return self.row(source,kind='推断',reasoning='待核实推断：碰撞具体时间有无其他材料记载？')

    def payload(self,**sections):return {**empty_analysis(self.record),**sections}

    def analyze(self,payload):
        settings=SimpleNamespace(api_key='offline-not-real',password_hash='offline-hash',provider='deepseek',
                                 provider_spec=SimpleNamespace(base_url='https://api.deepseek.com',label='DeepSeek'),
                                 model='mock-not-real',total_timeout=45,max_request_bytes=128000,
                                 ai_disabled_reason=lambda _: '')
        response={'provider_status':'completed','refused':False,'call_status':'response_received','token_usage':None,
                  'output_text':json.dumps(payload,ensure_ascii=False)}
        with patch('ai_analysis.invoke',return_value=response) as invoke:
            result=analyze_record(self.record,settings,Mock(),'offline-principal',True,Mock())
        invoke.assert_called_once()
        return result

    def complete(self):
        return self.payload(facts=[self.row('S002'),self.row('S003')],
                            timeline=[self.event('S002'),self.event('S003',time='2026年11月4日')],
                            pending_evidence=[self.question()])

    def rules(self,result):return [item['rule'] for item in result['timeline_completeness']['diagnostics']]

    def test_sim_b_omission_is_reported_and_never_auto_filled(self):
        payload=self.complete();payload['timeline']=payload['timeline'][1:]
        payload['pending_evidence']=[self.row('S006',kind='推断',reasoning='待核实推断：原始车载日志是否完整？')]
        result=self.analyze(payload)
        self.assertEqual(len(result['sections']['timeline']),1)
        self.assertEqual(result['sections']['timeline'][0]['time_text'],'2026年11月4日')
        self.assertIn('important_fact_event_missing_from_timeline',self.rules(result))
        self.assertIn('unknown_event_time_question_missing',self.rules(result))
        self.assertEqual(result['timeline_completeness']['status'],'needs_review')
        self.assertEqual(result['call_receipt']['timeline_completeness_status'],'needs_review')
        entry=load_scenarios()[1][1][0]
        self.assertFalse(automatic_checks(entry,self.record,result)['checks']['timeline_expected_bindings'])

    def test_existing_quality_process_preserves_both_original_timeline_events(self):
        payload=self.complete()
        validated=validate_analysis(payload,self.record,build_sources(self.record))
        result=_apply_output_quality(validated,self.record)
        self.assertEqual(result['sections']['timeline'],validated['sections']['timeline'])
        self.assertEqual(len(result['sections']['timeline']),2)

    def test_complete_unknown_and_dated_events_with_time_question_have_no_gap(self):
        result=self.analyze(self.complete())
        self.assertEqual(result['timeline_completeness']['status'],'no_gap_detected')
        self.assertFalse(result['timeline_completeness']['completeness_verified'])
        self.assertEqual(self.rules(result),[])
        unknown=next(row for row in result['sections']['timeline'] if row['time_state']=='unknown')
        self.assertEqual((unknown['time_text'],unknown['time_precision'],unknown['time_source']),('未知','unknown',None))

    def test_unknown_event_without_time_question_is_not_claimed_fully_reviewed(self):
        payload=self.complete();payload['pending_evidence']=[]
        result=self.analyze(payload)
        self.assertEqual(self.rules(result),['unknown_event_time_question_missing'])
        self.assertEqual(len(result['sections']['timeline']),2)

    def test_explicit_receipt_event_missing_has_no_invented_unknown_time_question(self):
        result=self.analyze(self.payload(facts=[self.row('S003')]))
        self.assertEqual(self.rules(result),['important_fact_event_missing_from_timeline'])
        self.assertEqual(result['sections']['timeline'],[])

    def test_different_kind_same_anchor_requires_review_without_relabelling(self):
        payload=self.payload(facts=[self.row('S003')],timeline=[self.event('S003',time='2026年11月4日',kind='主张')])
        result=self.analyze(payload)
        self.assertIn('timeline_kind_mismatch',self.rules(result))
        self.assertEqual(result['sections']['timeline'][0]['kind'],'主张')
        self.assertEqual(result['sections']['facts'][0]['kind'],'事实')

    def test_borrowed_receipt_date_still_fails_original_binding_before_diagnosis(self):
        bad=self.event('S002',time='2026年11月4日')
        with self.assertRaises(AIError) as caught:self.analyze(self.payload(facts=[self.row('S002')],timeline=[bad]))
        self.assertEqual(caught.exception.receipt['validation_error_kind'],'evidence_binding')
        self.assertNotIn('timeline_completeness_status',caught.exception.receipt)

    def test_same_event_duplicate_still_rejected_not_deduped_to_pass(self):
        event=self.event('S002')
        with self.assertRaises(AIError) as caught:self.analyze(self.payload(timeline=[event,deepcopy(event)]))
        self.assertEqual(caught.exception.receipt['validation_error_kind'],'evidence_binding')

    def custom(self,*lines):
        doc=Document()
        for line in lines:doc.add_paragraph(line)
        buf=io.BytesIO();doc.save(buf);self.record=extract('模拟完整性测试.docx',buf.getvalue())

    def test_opposing_claims_with_different_sources_cannot_cover_each_other(self):
        self.custom('模拟驾驶人主张：2026年11月1日，车辆发生碰撞。','模拟企业主张：2026年11月2日，车辆发生碰撞。')
        payload=self.payload(facts=[self.row('S001',kind='主张'),self.row('S002',kind='主张')],
                             timeline=[self.event('S002',kind='主张',time='2026年11月2日')])
        result=self.analyze(payload)
        diagnostics=result['timeline_completeness']['diagnostics']
        self.assertEqual(len(diagnostics),1)
        self.assertEqual(diagnostics[0]['source_id'],'S001')
        self.assertEqual([r['kind'] for r in result['sections']['facts']],['主张','主张'])
        self.assertEqual(len(result['sections']['timeline']),1)

    def test_same_text_in_different_positions_is_not_timeline_coverage(self):
        text='模拟现场记录：车辆发生碰撞，原文未记载日期。';self.custom(text,text)
        result=self.analyze(self.payload(facts=[self.row('S001')],timeline=[self.event('S002')]))
        self.assertIn('important_fact_event_missing_from_timeline',self.rules(result))

    def test_partial_fact_excerpt_covered_by_full_event_and_bound_question(self):
        payload=self.complete();payload['facts'][0]['text']='车辆发生碰撞'
        result=self.analyze(payload)
        self.assertEqual(self.rules(result),[])

    def test_broad_fact_quote_cannot_borrow_next_sentence_repair_date(self):
        self.custom('模拟现场记录：车辆发生碰撞。模拟维修记录：2026年11月4日，车辆完成维修。')
        payload=self.payload(facts=[self.row('S001',text='车辆发生碰撞')])
        result=self.analyze(payload)
        self.assertIn('unknown_event_time_question_missing',self.rules(result))
        self.assertFalse(result['sections']['timeline'])

    def test_wrong_event_question_source_does_not_cover_unknown_collision_time(self):
        payload=self.complete();payload['pending_evidence']=[self.question('S003')]
        result=self.analyze(payload)
        self.assertIn('unknown_event_time_question_missing',self.rules(result))

    def test_multi_reference_fact_is_only_flagged_ambiguous_not_copied(self):
        row=self.row('S002');row['sources'].append(self.row('S003')['sources'][0])
        result=self.analyze(self.payload(facts=[row]))
        self.assertEqual(self.rules(result),['event_context_ambiguous'])
        self.assertFalse(result['sections']['timeline'])

    def test_diagnostic_is_read_only_and_contains_no_source_text(self):
        payload=self.payload(facts=[self.row('S002')]);saved=deepcopy(payload);record=deepcopy(self.record)
        result=self.analyze(payload)
        self.assertEqual(payload,saved);self.assertEqual(self.record,record)
        encoded=json.dumps(result['timeline_completeness'],ensure_ascii=False)
        self.assertNotIn('车辆发生碰撞',encoded)
        self.assertNotIn('原文未记载',encoded)
        item=result['timeline_completeness']['diagnostics'][0]
        self.assertEqual(item['document_sha256'],self.record['文件SHA256'])
        self.assertEqual(item['unit_index'],1)

    def test_non_events_negated_or_conditional_statements_not_manufactured(self):
        self.custom('模拟企业主张：车辆未发生碰撞。','模拟驾驶人主张：如果车辆发生碰撞，应当记录。')
        result=self.analyze(self.payload(facts=[self.row('S001',kind='主张'),self.row('S002',kind='主张')]))
        self.assertEqual(result['timeline_completeness']['status'],'not_assessed')
        self.assertFalse(result['sections']['timeline'])

    def test_empty_output_is_not_completeness_proof_for_entire_document(self):
        result=self.analyze(self.payload())
        self.assertEqual(result['timeline_completeness']['status'],'not_assessed')
        self.assertFalse(result['timeline_completeness']['completeness_verified'])

    def test_revision_and_prompt_require_unknown_events_without_cross_module_erasure(self):
        self.assertIn('时间未知不等于事件不存在',PROMPT)
        self.assertIn('不能因为facts已有',PROMPT)
        self.assertIn('碰撞具体时间有无其他材料记载',PROMPT)
        result=self.analyze(self.complete())
        self.assertEqual(result['output_quality_version'],'output-quality-p1/v1')
        self.assertEqual(result['call_receipt']['prompt_revision'],'output-quality-p1-timeline/v1')
        self.assertEqual(result['schema_version'],'2.0')

    def test_sim_a_existing_positive_events_and_opposing_prompt_claims_preserved(self):
        from test_providers import gold_payload
        entry,self.record=load_scenarios()[1][0]
        payload=gold_payload(entry,self.record)
        before=validate_analysis(payload,self.record,build_sources(self.record))
        result=self.analyze(payload)
        self.assertEqual(result['sections']['timeline'],before['sections']['timeline'])
        self.assertEqual([r['kind'] for r in result['sections']['facts']],['事实','主张','主张'])
        self.assertEqual(result['timeline_completeness']['status'],'no_gap_detected')

    def test_ui_displays_needs_review_without_inserting_rows(self):
        from streamlit.testing.v1 import AppTest
        from ui_isolation import isolated_ui_runtime
        result=self.analyze(self.payload(facts=[self.row('S002')]))
        with isolated_ui_runtime():
            app=AppTest.from_string("import streamlit as st\nfrom ai_ui import render_result\nrender_result(st.session_state['result'],'timeline-test')",default_timeout=30)
            app.session_state['result']=result;app.run()
            self.assertFalse(app.exception)
            self.assertTrue(any('时间线完整性' in warning.value for warning in app.warning))
        self.assertFalse(result['sections']['timeline'])
