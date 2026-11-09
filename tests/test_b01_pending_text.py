"""CASE-001 D01/D04人工离线反例，不是用户真实DeepSeek返回内容。"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from case_store import CaseStore
from security import Settings,QuotaStore
import multidoc_ai as m

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'datasets'/'CASE-001'/'standard'
HASH='pbkdf2_sha256$200000$'+'ab'*16+'$'+'cd'*32
QA='事故时间栏目08:30来自P01口述，仅按分钟填写，未作时钟校核。'
QB='首行是事故时刻汇总栏；08:31转录自IN-01接报分钟，不是EDR绝对时钟。'
QUESTION='待核实推断：是否需要分别核对口述与接报卡转录来源，再核查两份材料的时钟基准？'


class B01PendingText(unittest.TestCase):
    def setUp(self):
        self.store=CaseStore();self.cid=self.store.create_case('模拟CASE-001待核实文本反例')
        manifest=json.loads((DATA/'manifest.json').read_text());self.ids=[]
        for item in manifest['documents']:
            if item['material_id'] in ('D01','D04'):
                path=DATA/item['path'];self.ids.append(self.store.attach_document(self.cid,path.name,path.read_bytes()))
        self.settings=Settings(api_key='offline-not-real',password_hash=HASH,mode='local',single_instance=True,provider='deepseek')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.quota=QuotaStore(Path(self.tmp.name)/'test-only.sqlite3')
        self.batch=m.prepare_case(self.store,self.cid,self.ids,self.settings)
        self.refs=[{'source_id':next(s['source_id'] for s in self.batch['sources'] if q in s['text']),'quote':q} for q in (QA,QB)]

    def payload(self,text=QA):
        return {'schema_version':'multidoc-analysis/1.1','prompt_version':'multidoc/candidates-v1','case_id':self.cid,
                'batch_sha256':self.batch['batch_sha256'],'facts':[],'timeline':[],'relations':[],
                'pending_evidence':[{'kind':'推断','text':text,'reasoning':QUESTION,'sources':deepcopy(self.refs)}]}

    def analyze(self,payload):
        response={'provider_status':'completed','provider_model':'offline-mock-not-real','provider_response_id':'mock-only',
                  'call_status':'response_received','refused':False,'token_usage':{'input_tokens':100,'output_tokens':13,'total_tokens':113},
                  'output_text':json.dumps(payload,ensure_ascii=False)}
        with patch('multidoc_ai.invoke',return_value=response) as invoke:
            result=m.analyze_case_candidates(self.store,self.cid,self.ids,self.settings,self.quota,self.settings.principal,
                   authorized_batch=self.batch['batch_sha256'],coverage_acknowledged=self.batch['required_ack'],client_factory=Mock())
        invoke.assert_called_once();return result

    def rejected(self,payload,rule,format_passed=True):
        before=self.store.export_json(self.cid);original=deepcopy(payload)
        with self.assertRaises(m.MultiAIError) as caught:self.analyze(payload)
        receipt=caught.exception.receipt;d=receipt['validation_diagnostic']
        self.assertEqual(d['rule'],rule);self.assertEqual((d['section'],d['item_index']),('pending_evidence',0))
        self.assertEqual(receipt['provider_status'],'completed');self.assertEqual(receipt['token_usage']['total_tokens'],113)
        self.assertEqual(receipt['format_status'],'passed' if format_passed else 'failed_or_unavailable')
        self.assertEqual(receipt['evidence_status'],'failed' if format_passed else 'not_run')
        self.assertEqual(receipt['error_code'],'output_validation_failed')
        self.assertEqual(self.store.export_json(self.cid),before);self.assertEqual(payload,original)
        self.assertEqual(self.quota.budget_snapshot(self.settings,self.settings.principal)['daily_calls_remaining'],19)
        return d

    def test_prompt_explicit_contiguous_anchor_and_preserved_multisource_reasoning(self):
        for prompt in (m.PROMPT,m.CANDIDATE_PROMPT):
            for fragment in ('至少一条sources.quote中连续存在的原文','不得概括、改写或拼接跨文件内容作为text',
                             '跨文件核验问题放在reasoning','sources可以保留多个文档的独立引用','不要求text出现在每条quote'):
                with self.subTest(fragment=fragment):self.assertIn(fragment,prompt)

    def test_summary_not_in_any_quote_reproduces_reported_rule(self):
        d=self.rejected(self.payload('现场与EDR事故时间存在差异，需确认实际碰撞时刻。'),'text_not_in_quote')
        self.assertEqual(d['stage'],'inference');self.assertEqual(set(d['source_ids']),{r['source_id'] for r in self.refs})

    def test_concatenation_across_valid_quotes_is_rejected(self):
        self.rejected(self.payload(QA+QB),'text_not_in_quote')

    def test_question_in_text_is_rejected_even_if_reasoning_is_valid(self):
        self.rejected(self.payload('两份事故时间来源是否应当核对？'),'text_not_in_quote')

    def test_rewritten_whitespace_or_wording_is_not_auto_fixed(self):
        for text in ('事故时间栏目08:30来自驾驶人口述。','事故时间栏目08:30 来自P01口述，仅按分钟填写，未作时钟校核。'):
            # 纯验证路径分别构造，不重复请求、重试或绕过额度。
            p=self.payload(text);before=deepcopy(p)
            with self.assertRaises(m.MultiAIError) as error:m.validate_candidate_output(self.store,self.cid,self.batch,p)
            self.assertEqual(error.exception.diagnostic['rule'],'text_not_in_quote');self.assertEqual(p,before)

    def test_anchor_in_first_quote_accepts_and_keeps_both_document_refs(self):
        result=self.analyze(self.payload());row=result['pending_evidence'][0]
        self.assertEqual(row['text'],QA);self.assertNotIn(QA,QB)
        self.assertEqual(row['reasoning'],QUESTION);self.assertEqual(len({r['document_id'] for r in row['sources']}),2)
        self.assertEqual(result['receipt']['evidence_status'],'passed')
        self.assertEqual(self.store.get_case(self.cid).inferences,[])

    def test_anchor_in_second_quote_is_also_valid(self):
        result=self.analyze(self.payload(QB));self.assertEqual(result['pending_evidence'][0]['text'],QB)
        self.assertEqual(len(result['pending_evidence'][0]['sources']),2)

    def test_contiguous_substring_is_valid_not_forced_to_full_quote(self):
        result=self.analyze(self.payload('仅按分钟填写，未作时钟校核。'))
        self.assertEqual(result['pending_evidence'][0]['text'],'仅按分钟填写，未作时钟校核。')
        self.assertEqual(result['pending_evidence'][0]['reasoning'],QUESTION)

    def test_other_source_still_must_pass_original_quote_binding(self):
        p=self.payload();p['pending_evidence'][0]['sources'][1]['quote']='原文没有的第二条引文'
        self.rejected(p,'quote_not_found')

    def test_reasoning_still_requires_pending_prefix_and_question(self):
        p=self.payload();p['pending_evidence'][0]['reasoning']='请核查两份资料的时钟基准？'
        self.rejected(p,'inference_prefix_missing')

    def test_successful_explicit_import_preserves_multifile_question_and_positions(self):
        result=self.analyze(self.payload());m.import_case_analysis(self.store,self.cid,result)
        case=self.store.get_case(self.cid);row=case.inferences[0]
        self.assertEqual(row.text,QUESTION);self.assertEqual(row.verification,'unverified')
        self.assertEqual(len({case.evidence[e].document_id for e in row.evidence_ids}),2)
        for eid in row.evidence_ids:
            s=case.evidence[eid];unit=case.documents[s.document_id].units[s.unit_index]
            self.assertEqual(unit['text'][s.start:s.end],s.quote)
        self.assertEqual(case.reviews,[])

    def test_b01_preflight_remains_bounded_and_only_instructions_change(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('pending_budget_generator',ROOT/'tools'/'generate_case_001.py')
        gen=importlib.util.module_from_spec(spec);spec.loader.exec_module(gen)
        manifest=json.loads((DATA/'manifest.json').read_text());files={}
        for d in manifest['documents']:
            if d['material_id'] in ('D01','D02','D03','D04'):
                path=DATA/d['path'];files[d['material_id']]=(path.name,path.read_bytes())
        store,ids=gen.build_store(files);batch=m.prepare_case(store,gen.CASE_ID,list(ids.values()),self.settings)
        request,budget=m.candidate_request_for(batch,self.settings)
        self.assertLessEqual(budget['input_chars'],16000);self.assertLessEqual(budget['request_bytes'],128000)
        self.assertEqual(len(json.loads(request['input'])['documents']),4)
        self.assertEqual(request['instructions'],m.CANDIDATE_PROMPT)
