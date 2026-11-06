"""分类范围回归：所有材料均为内存虚构/既有SIM样本；无联网或付费调用。"""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from ai_analysis import (AIError, build_sources, empty_analysis, validate_analysis, analyze_record)
from core import extract
from live_acceptance import load_scenarios
from security import Settings

ROOT = Path(__file__).resolve().parents[1]


class FactClassificationTests(unittest.TestCase):
    def record(self, text):
        path = ROOT/'samples_ai'/'模拟_AI事故材料.docx'
        record = extract(path.name,path.read_bytes())
        record['units'] = [{'text':text,'location':'模拟内存段落'}]
        return record

    def payload(self, record, quote, *, kind='事实', section='facts', text=None):
        sources = build_sources(record)
        source = next(s for s in sources if quote in s['text'])
        ref = {'source_id':source['source_id'],'quote':quote}
        row = {'kind':kind,'text':quote if text is None else text,'reasoning':'','sources':[ref]}
        if section == 'timeline':
            row.update(event_source=deepcopy(ref),time_state='unknown',time_text='未知',
                       time_precision='unknown',time_source=None)
        result = empty_analysis(record); result[section] = [row]
        return result

    def validate(self, record, quote, **kwargs):
        return validate_analysis(self.payload(record,quote,**kwargs),record,build_sources(record))

    def test_fact_sentence_not_contaminated_by_later_unverified_sentence(self):
        quote = '模拟接收记录：测试方收到车辆检查材料。'
        record = self.record(quote+'原始日志是否完整尚未核实。')
        result = self.validate(record,quote)
        self.assertEqual(result['sections']['facts'][0]['kind'],'事实')
        self.assertEqual(result['verification'],'待人工核验')

    def test_fact_sentence_not_contaminated_by_later_party_claim(self):
        quote = '模拟现场记录：车辆发生碰撞。'
        record = self.record(quote+'模拟驾驶人主张：系统未提示。')
        self.assertEqual(self.validate(record,quote)['sections']['facts'][0]['text'],quote)

    def test_unknown_timeline_before_unverified_sentence_keeps_binding(self):
        quote = '模拟现场记录：车辆发生碰撞，原文未记载日期。'
        record = self.record(quote+'日志完整性待核实。')
        row = self.validate(record,quote,section='timeline')['sections']['timeline'][0]
        self.assertEqual(row['time_text'],'未知')
        self.assertIsNone(row['normalized_time'])
        self.assertIsNone(row['time_source'])
        self.assertEqual(row['event_source']['quote'],quote)

    def test_sim_b_objective_records_pass_and_original_positions_replay(self):
        entry,record = load_scenarios()[1][1]
        self.assertEqual(entry['id'],'SIM_B')
        for unit in record['units'][1:3]:
            quote = unit['text']
            result = self.validate(record,quote)
            ref = result['sections']['facts'][0]['sources'][0]
            self.assertEqual(record['units'][ref['unit_index']]['text'][ref['start']:ref['end']],quote)
            self.assertEqual(ref['document_sha256'],record['文件SHA256'])

    def test_sim_b_directory_partial_fact_remains_conservative(self):
        _,record = load_scenarios()[1][1]
        with self.assertRaises(AIError) as caught:
            self.validate(record,'仅列出检查摘要')
        self.assertEqual(caught.exception.diagnostic['matched_markers'],['尚未核实'])
        self.assertEqual(caught.exception.diagnostic['source_id'],'S006')

    def test_driver_and_company_claims_rejected_even_without_prefix_in_quote(self):
        for actor in ('驾驶人','企业'):
            for prefix in ('主张：','称','陈述：','认为','否认','自述：','表示：'):
                with self.subTest(actor=actor,prefix=prefix):
                    record = self.record('模拟'+actor+prefix+'碰撞前未收到提示。')
                    with self.assertRaises(AIError) as caught:
                        self.validate(record,'碰撞前未收到提示。')
                    diagnostic = caught.exception.diagnostic
                    self.assertEqual(diagnostic['section'],'facts')
                    self.assertEqual(diagnostic['item_index'],0)
                    self.assertEqual(diagnostic['source_id'],'S001')
                    self.assertTrue(diagnostic['matched_markers'])
                    self.assertEqual(diagnostic['rule'],'fact_from_claim_or_unverified_context')

    def test_claim_scope_is_not_reset_by_period_or_newline(self):
        for separator in ('。','\n','；'):
            with self.subTest(separator=separator):
                record = self.record('模拟驾驶人主张：车辆已接管'+separator+'碰撞前未收到提示。')
                with self.assertRaises(AIError):
                    self.validate(record,'碰撞前未收到提示。')

    def test_claim_prefix_cannot_hide_in_previous_thousand_character_chunk(self):
        record = self.record('模拟驾驶人主张：'+'甲'*1000+'碰撞前未收到提示。')
        with self.assertRaises(AIError) as caught:
            self.validate(record,'碰撞前未收到提示。')
        self.assertEqual(caught.exception.diagnostic['source_id'],'S002')
        self.assertIn('主张',caught.exception.diagnostic['matched_markers'])

    def test_same_sentence_qualifier_cannot_be_trimmed_or_hidden_after_comma(self):
        for text in ('模拟记录：碰撞前未收到提示，尚未核实。',
                     '模拟记录：碰撞前未收到提示（待核实）。',
                     '模拟记录：尚未核实是否碰撞前未收到提示。'):
            with self.subTest(text=text),self.assertRaises(AIError):
                self.validate(self.record(text),'碰撞前未收到提示')

    def test_broad_quote_with_claim_markers_still_rejected(self):
        quote = '模拟现场记录：车辆发生碰撞。模拟驾驶人主张：系统未提示。'
        with self.assertRaises(AIError):
            self.validate(self.record(quote),quote,text='车辆发生碰撞')

    def test_followup_qualifier_cannot_be_removed_by_sentence_or_semicolon(self):
        quote = '模拟现场记录：车辆发生碰撞。'
        for tail in ('上述记录尚未核实。','该情况待核实。','此事尚未核实。','尚未核实。'):
            with self.subTest(tail=tail),self.assertRaises(AIError):
                self.validate(self.record(quote+tail),quote)
        quote = '模拟现场记录：车辆发生碰撞；'
        with self.assertRaises(AIError):
            self.validate(self.record(quote+'尚未核实。'),quote)

    def test_claim_kind_keeps_original_marker_and_manual_review(self):
        quote = '模拟驾驶人主张：碰撞前未收到提示。'
        result = self.validate(self.record(quote),quote,kind='主张')
        self.assertEqual(result['sections']['facts'][0]['kind'],'主张')
        self.assertEqual(result['sections']['facts'][0]['verification'],'待人工核验')

    def test_all_cited_sources_checked_not_only_first_reference(self):
        record = self.record('模拟现场记录：车辆发生碰撞。\n模拟驾驶人主张：系统未提示。')
        payload = self.payload(record,'模拟现场记录：车辆发生碰撞。')
        payload['facts'][0]['sources'].append({'source_id':'S002','quote':'系统未提示。'})
        with self.assertRaises(AIError) as caught:
            validate_analysis(payload,record,build_sources(record))
        self.assertEqual(caught.exception.diagnostic['source_id'],'S002')

    def test_diagnostic_reports_actual_section_and_zero_based_index_without_text(self):
        record = self.record('模拟现场记录：车辆发生碰撞。\n模拟企业主张：私密占位内容。')
        payload = self.payload(record,'模拟现场记录：车辆发生碰撞。')
        bad = self.payload(record,'模拟企业主张：私密占位内容。')['facts'][0]
        payload['facts'].append(bad)
        with self.assertRaises(AIError) as caught:
            validate_analysis(payload,record,build_sources(record))
        d = caught.exception.diagnostic
        self.assertEqual(d['section'],'facts');self.assertEqual(d['item_index'],1)
        self.assertEqual(d['source_id'],'S002')
        self.assertNotIn('私密占位内容',str(d)+str(caught.exception))
        with self.assertRaises(AIError) as timeline_error:
            self.validate(record,'模拟企业主张：私密占位内容。',section='timeline')
        self.assertEqual(timeline_error.exception.diagnostic['section'],'timeline')

    def test_safe_diagnostic_reaches_offline_receipt_without_raw_output(self):
        import json
        from unittest.mock import Mock
        from security import hash_password
        record = self.record('模拟企业主张：私密占位内容。')
        payload = self.payload(record,'私密占位内容。')
        # 仅使用内存测试设置/替身，不加载Secrets或SDK，不可能产生网络请求。
        settings = Settings(api_key='offline-not-real',password_hash=hash_password('simulation-password'),
                            mode='local',single_instance=True,provider='deepseek')
        with patch('ai_analysis.invoke',return_value={'provider_status':'completed','refused':False,
                    'output_text':json.dumps(payload),'call_status':'response_received','token_usage':None}):
            with self.assertRaises(AIError) as caught:
                analyze_record(record,settings,Mock(),settings.principal,True,client_factory=Mock())
        receipt = caught.exception.receipt
        self.assertEqual(caught.exception.code,'output_validation_failed')
        self.assertEqual(receipt['validation_error_kind'],'evidence_binding')
        self.assertEqual(receipt['validation_diagnostic']['matched_markers'],['主张'])
        self.assertEqual(receipt['execution_mode'],'injected_test_client')
        self.assertNotIn('私密占位内容',json.dumps(receipt,ensure_ascii=False))
