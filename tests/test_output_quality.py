"""SIM_A/B输出质量人工反例：无真实模型、Secrets或私有验收记录。"""
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from docx import Document
from ai_analysis import (AIError,analyze_record,empty_analysis,build_sources,validate_analysis,prepare_request,PROMPT)
from core import extract
from sample_debug import fixed_record
from security import Settings,QuotaStore

HASH='pbkdf2_sha256$200000$'+'ab'*16+'$'+'cd'*32
USAGE={'input_tokens':123,'output_tokens':45,'total_tokens':168} # 仅供模拟断言


class OutputQualityTests(unittest.TestCase):
    def setUp(self):
        self.record=fixed_record('SIM_B')
        self.settings=Settings(api_key='offline-only',password_hash=HASH,mode='local',single_instance=True,provider='deepseek')

    def row(self,source_id,kind='推断',reasoning='待核实推断：原始车载日志是否完整？',text=None):
        source=next(s for s in build_sources(self.record) if s['source_id']==source_id)
        quote=source['text']
        return {'kind':kind,'text':quote if text is None else text,'reasoning':reasoning if kind=='推断' else '',
                'sources':[{'source_id':source_id,'quote':quote}]}

    def payload(self,**sections):
        return {**empty_analysis(self.record),**sections}

    def analyze(self,payload,store=None):
        response={'provider_status':'completed','provider_model':'offline-mock-not-real','provider_response_id':'mock-quality',
                  'call_status':'response_received','refused':False,'token_usage':USAGE,
                  'output_text':json.dumps(payload,ensure_ascii=False)}
        store=Mock() if store is None else store
        with patch('ai_analysis.invoke',return_value=response):
            return analyze_record(self.record,self.settings,store,self.settings.principal,True,Mock())

    def test_sim_b_inference_in_facts_is_routed_without_relabelling_or_lost_evidence(self):
        original=self.row('S006')
        result=self.analyze(self.payload(facts=[original]))
        self.assertEqual(result['sections']['facts'],[])
        pending=result['sections']['pending_evidence']
        self.assertEqual(len(pending),1)
        self.assertEqual(pending[0]['kind'],'推断')
        self.assertEqual(pending[0]['text'],original['text'])
        self.assertEqual(pending[0]['reasoning'],original['reasoning'])
        self.assertEqual(result['quality_audit']['actions'][0]['rule'],'route_inference_to_pending')

    def test_sim_a_exact_cross_module_duplicate_has_one_pending_and_audit(self):
        self.record=fixed_record('SIM_A');row=self.row('S006')
        result=self.analyze(self.payload(facts=[deepcopy(row)],pending_evidence=[deepcopy(row)]))
        self.assertEqual(result['sections']['facts'],[])
        self.assertEqual(len(result['sections']['pending_evidence']),1)
        self.assertTrue(any(a['rule']=='merge_exact_duplicate' for a in result['quality_audit']['actions']))
        self.assertTrue(all(a['original_item']['sources'] for a in result['quality_audit']['actions']))

    def test_reasoning_duplicate_rejected_instead_of_silently_rewritten(self):
        for scenario in ('SIM_A','SIM_B'):
            self.record=fixed_record(scenario)
            with self.subTest(scenario=scenario),self.assertRaises(AIError) as caught:
                self.analyze(self.payload(pending_evidence=[self.row('S006',reasoning='待核实推断：原始日志是否完整是否尚未核实？')]))
            self.assertEqual(caught.exception.code,'output_quality_failed')
            self.assertEqual(caught.exception.receipt['validation_error_kind'],'output_quality')
            self.assertEqual(caught.exception.receipt['evidence_validation_status'],'passed')
            self.assertEqual(caught.exception.receipt['token_usage'],USAGE)
            self.assertNotIn('原始日志',json.dumps(caught.exception.receipt,ensure_ascii=False))

    def test_metadata_declaration_goes_to_auditable_document_metadata(self):
        for scenario in ('SIM_A','SIM_B'):
            self.record=fixed_record(scenario)
            result=self.analyze(self.payload(facts=[self.row('S001','事实')]))
            self.assertEqual(result['sections']['facts'],[])
            self.assertEqual(result['document_metadata'][0]['text'],self.record['units'][0]['text'])
            ref=result['document_metadata'][0]['sources'][0]
            self.assertEqual(self.record['units'][ref['unit_index']]['text'][ref['start']:ref['end']],ref['quote'])
            self.assertEqual(ref['document_sha256'],self.record['文件SHA256'])
            self.assertEqual(result['verification'],'待人工核验')

    def test_metadata_removed_from_timeline_only_after_original_binding_validation(self):
        row=self.row('S001','事实');ref=deepcopy(row['sources'][0])
        row.update(event_source=ref,time_source=None,time_state='unknown',time_precision='unknown',time_text='未知')
        result=self.analyze(self.payload(timeline=[row]))
        self.assertEqual(result['sections']['timeline'],[])
        self.assertEqual(result['document_metadata'][0]['event_source']['quote'],ref['quote'])

    def test_same_anchor_with_distinct_questions_is_not_semantically_merged(self):
        first=self.row('S006')
        second=self.row('S006',reasoning='待核实推断：检查摘要能否反映日志的完整性？')
        result=self.analyze(self.payload(facts=[first],pending_evidence=[second]))
        self.assertFalse(result['sections']['facts'])
        self.assertEqual(len(result['sections']['pending_evidence']),2)
        self.assertEqual({r['reasoning'] for r in result['sections']['pending_evidence']},{first['reasoning'],second['reasoning']})

    def test_explicit_opposing_claims_and_reused_evidence_are_preserved(self):
        self.record=fixed_record('SIM_A')
        claims=[self.row('S003','主张'),self.row('S004','主张')]
        question=self.row('S003',reasoning='待核实推断：接管提示是否发出，驾驶人是否收到？')
        result=self.analyze(self.payload(facts=claims,pending_evidence=[question]))
        self.assertEqual([r['kind'] for r in result['sections']['facts']],['主张','主张'])
        self.assertEqual(len(result['sections']['pending_evidence']),1)
        self.assertTrue(all(r['verification']=='待人工核验' for r in result['sections']['facts']))

    def test_natural_questions_with_multiple_whether_are_preserved_exactly(self):
        for question in ('待核实推断：是否需要核实原始日志是否完整？',
                         '待核实推断：原始日志是否完整，检查摘要是否齐全？'):
            with self.subTest(question=question):
                result=self.analyze(self.payload(pending_evidence=[self.row('S006',reasoning=question)]))
                self.assertEqual(result['sections']['pending_evidence'][0]['reasoning'],question)

    def test_natural_question_does_not_rewrite_literal_unverified_quote(self):
        row=self.row('S006')
        result=self.analyze(self.payload(pending_evidence=[row]))
        self.assertEqual(result['sections']['pending_evidence'][0]['text'],row['text'])
        self.assertEqual(result['sections']['pending_evidence'][0]['sources'][0]['quote'],row['sources'][0]['quote'])

    def test_exact_duplicates_within_facts_removed_without_merging_claim_with_fact(self):
        row=self.row('S003','事实')
        claim=deepcopy(row);claim['kind']='主张'
        result=self.analyze(self.payload(facts=[row,deepcopy(row),claim]))
        self.assertEqual([r['kind'] for r in result['sections']['facts']],['事实','主张'])

    def test_different_sources_with_same_wording_are_not_merged(self):
        doc=Document();quote='模拟目录：原始日志完整性尚未核实。'
        doc.add_paragraph(quote);doc.add_paragraph(quote)
        buf=io.BytesIO();doc.save(buf)
        self.record=extract('模拟不同来源.docx',buf.getvalue())
        result=self.analyze(self.payload(pending_evidence=[self.row('S001'),self.row('S002')]))
        self.assertEqual(len(result['sections']['pending_evidence']),2)

    def test_metadata_phrase_in_accident_record_not_hidden(self):
        doc=Document();quote='模拟记录：材料提及“模拟数据声明”，车辆发生碰撞。';doc.add_paragraph(quote)
        buf=io.BytesIO();doc.save(buf)
        self.record=extract('模拟声明提及.docx',buf.getvalue())
        result=self.analyze(self.payload(facts=[self.row('S001','事实')]))
        self.assertEqual(result['sections']['facts'][0]['text'],quote)

    def test_literal_question_bad_phrase_does_not_change_or_reject_original_quote(self):
        doc=Document();quote='模拟目录原文：是否完整是否尚未核实。';doc.add_paragraph(quote)
        buf=io.BytesIO();doc.save(buf)
        self.record=extract('模拟原文保真.docx',buf.getvalue())
        result=self.analyze(self.payload(pending_evidence=[self.row('S001')]))
        self.assertEqual(result['sections']['pending_evidence'][0]['sources'][0]['quote'],quote)

    def test_input_and_original_evidence_snapshots_unchanged_by_routing(self):
        payload=self.payload(facts=[self.row('S006')]);saved=deepcopy(payload);record=deepcopy(self.record)
        expected=validate_analysis(payload,self.record,build_sources(self.record))['sections']['facts'][0]
        result=self.analyze(payload)
        self.assertEqual(payload,saved);self.assertEqual(self.record,record)
        self.assertEqual(result['sections']['pending_evidence'][0],expected)

    def test_original_claim_as_fact_rejection_precedes_quality_processing(self):
        with self.assertRaises(AIError) as caught:
            self.analyze(self.payload(facts=[self.row('S004','事实')]))
        self.assertEqual(caught.exception.receipt['validation_error_kind'],'evidence_binding')

    def test_bad_reference_in_duplicate_cannot_be_hidden_by_deduplication(self):
        good=self.row('S006');bad=deepcopy(good);bad['sources'][0]['source_id']='S999'
        with self.assertRaises(AIError) as caught:
            self.analyze(self.payload(facts=[bad],pending_evidence=[good]))
        self.assertEqual(caught.exception.receipt['validation_error_kind'],'evidence_binding')

    def test_bad_time_in_metadata_cannot_be_hidden_by_metadata_processing(self):
        row=self.row('S001','事实');ref=deepcopy(row['sources'][0])
        row.update(event_source=ref,time_source=ref,time_state='explicit',time_precision='date',time_text='2099年1月1日')
        with self.assertRaises(AIError) as caught:self.analyze(self.payload(timeline=[row]))
        self.assertEqual(caught.exception.receipt['validation_error_kind'],'evidence_binding')

    def test_quality_failure_still_consumes_original_budget_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QuotaStore(Path(tmp)/'quota.sqlite3')
            payload=self.payload(pending_evidence=[self.row('S006',reasoning='待核实推断：原始日志是否是否完整？')])
            with self.assertRaises(AIError):self.analyze(payload,store)
            remaining=store.budget_snapshot(self.settings,self.settings.principal)
            self.assertEqual(remaining['daily_calls_remaining'],self.settings.daily_limit-1)
            self.assertLess(remaining['daily_chars_remaining'],self.settings.daily_input_chars)

    def test_wire_contract_compatible_and_quality_revision_is_explicit(self):
        result=self.analyze(self.payload(pending_evidence=[self.row('S006')]))
        self.assertEqual(result['schema_version'],'2.0')
        self.assertEqual(result['prompt_version'],'evidence-binding-v2')
        self.assertEqual(result['output_quality_version'],'output-quality-p1/v1')
        self.assertEqual(result['call_receipt']['prompt_revision'],'output-quality-p1/v1')
        self.assertTrue(result['call_receipt']['prompt_sha256'])

    def test_routing_over_pending_capacity_fails_without_dropping_questions(self):
        doc=Document()
        for i in range(9):doc.add_paragraph(f'模拟目录{i}：原始日志完整性尚未核实。')
        buf=io.BytesIO();doc.save(buf)
        self.record=extract('模拟待核实容量.docx',buf.getvalue())
        payload=self.payload(facts=[self.row(f'S{i:03}') for i in range(1,10)])
        original=deepcopy(payload)
        with self.assertRaises(AIError) as caught:self.analyze(payload)
        self.assertEqual(caught.exception.code,'output_quality_failed')
        self.assertEqual(caught.exception.receipt['validation_diagnostic']['rule'],'pending_capacity_exceeded')
        self.assertEqual(payload,original)

    def test_quality_result_import_preserves_evidence_and_excludes_file_declaration(self):
        from case_store import CaseStore
        payload=self.payload(facts=[self.row('S001','事实'),self.row('S002','事实'),self.row('S006')])
        result=self.analyze(payload)
        store=CaseStore();cid=store.create_case('模拟质量导入')
        did=store.attach_document(cid,self.record['文件名'],self.record['original_bytes'])
        store.import_analysis(cid,did,result)
        case=store.get_case(cid)
        self.assertEqual(len(case.facts),1)
        self.assertEqual(len(case.inferences),1)
        self.assertEqual(len(case.pending_items),1)
        self.assertTrue(all(row.verification=='unverified' for row in case.facts))
        self.assertEqual(result['document_metadata'][0]['text'],self.record['units'][0]['text'])

    def test_quality_version_never_bypasses_case_import_coordinate_validation(self):
        from case_store import CaseStore,CaseError
        result=self.analyze(self.payload(facts=[self.row('S006')]))
        store=CaseStore();cid=store.create_case('模拟质量防篡改')
        did=store.attach_document(cid,self.record['文件名'],self.record['original_bytes'])
        result['sections']['pending_evidence'][0]['sources'][0]['start']+=1
        with self.assertRaises(CaseError):store.import_analysis(cid,did,result)
        self.assertFalse(store.get_case(cid).inferences)

    def test_normal_timeline_binding_and_sorting_are_identical_after_quality(self):
        unknown=self.row('S002','事实');ref=deepcopy(unknown['sources'][0])
        unknown.update(event_source=ref,time_source=None,time_state='unknown',time_precision='unknown',time_text='未知')
        dated=self.row('S003','事实');ref=deepcopy(dated['sources'][0])
        dated.update(event_source=ref,time_source=ref,time_state='explicit',time_precision='date',time_text='2026年11月4日')
        payload=self.payload(facts=[self.row('S006')],timeline=[unknown,dated])
        expected=validate_analysis(payload,self.record,build_sources(self.record))['sections']['timeline']
        self.assertEqual(self.analyze(payload)['sections']['timeline'],expected)

    def test_prompt_separates_inference_deduplication_metadata_and_questions(self):
        self.assertIn('facts禁止kind=推断',PROMPT)
        self.assertIn('是否完整是否尚未核实',PROMPT)
        self.assertIn('模拟数据声明',PROMPT)
        self.assertIn('同一证据锚点',PROMPT)
