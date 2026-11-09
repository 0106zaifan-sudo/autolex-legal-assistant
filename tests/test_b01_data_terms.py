"""D04术语来源的人工离线反例；不代表未保存的真实模型响应。"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from case_store import CaseStore
from security import Settings, QuotaStore
import multidoc_ai as m

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'datasets' / 'CASE-001' / 'standard'
TITLE = '模拟材料：EDR摘要'
BODY = '原始二进制数据及提取过程镜像未提供，摘要为二次转写。'
EDR_BODY = 'EDR只提供相对触发锚点t=0的测试摘要，未提供可信绝对日期。'
SITE = '事故时间栏目08:30来自P01口述，仅按分钟填写，未作时钟校核。'
QUESTION = '待核实推断：D04的EDR摘要所涉原始二进制数据及提取过程镜像是否需要进一步核查？'
HASH = 'pbkdf2_sha256$200000$' + 'ab'*16 + '$' + 'cd'*32


class B01DataTerms(unittest.TestCase):
    def setUp(self):
        self.store = CaseStore()
        self.cid = self.store.create_case('完全虚构 CASE-001 术语审查')
        self.ids = {}
        for item in json.loads((DATA/'manifest.json').read_text())['documents']:
            if item['material_id'] in ('D01', 'D04'):
                path = DATA/item['path']
                self.ids[item['material_id']] = self.store.attach_document(self.cid, path.name, path.read_bytes())
        self.settings = Settings(api_key='offline-not-real', password_hash=HASH, mode='local', single_instance=True,
                                 provider='deepseek', model='deepseek-flash')
        self.batch = m.prepare_case(self.store, self.cid, list(self.ids.values()), self.settings)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.quota = QuotaStore(Path(self.tmp.name)/'test-only.sqlite3')

    def ref(self, quote, material='D04'):
        source = next(s for s in self.batch['sources'] if s['document_id'] == self.ids[material] and quote in s['text'])
        return {'source_id': source['source_id'], 'quote': quote}

    def payload(self, reasoning=QUESTION, refs=None, text=BODY):
        return {'schema_version': m.CANDIDATE_SCHEMA_VERSION, 'prompt_version': m.CANDIDATE_PROMPT_VERSION,
                'case_id': self.cid, 'batch_sha256': self.batch['batch_sha256'], 'facts': [], 'timeline': [], 'relations': [],
                'pending_evidence': [{'kind': '推断', 'text': text, 'reasoning': reasoning,
                                      'sources': refs if refs is not None else [self.ref(BODY)]}]}

    def analyze(self, payload):
        response = {'provider_status': 'completed', 'provider_model': 'offline-mock-not-real',
                    'provider_response_id': 'mock-only', 'call_status': 'response_received', 'refused': False,
                    'token_usage': {'input_tokens': 110, 'output_tokens': 17, 'total_tokens': 127},
                    'output_text': json.dumps(payload, ensure_ascii=False)}
        with patch('multidoc_ai.invoke', return_value=response) as invoke:
            try:
                return m.analyze_case_candidates(self.store, self.cid, list(self.ids.values()), self.settings,
                        self.quota, self.settings.principal, authorized_batch=self.batch['batch_sha256'],
                        coverage_acknowledged=self.batch['required_ack'], client_factory=Mock())
            finally:
                invoke.assert_called_once()

    def reject(self, payload, rule='unsupported_data_term'):
        before = self.store.export_json(self.cid)
        with self.assertRaises(m.MultiAIError) as caught:
            self.analyze(payload)
        receipt = caught.exception.receipt
        d = receipt['validation_diagnostic']
        self.assertEqual(d['rule'], rule)
        self.assertEqual((d['section'], d['item_index']), ('pending_evidence', 0))
        self.assertEqual(receipt['format_status'], 'passed')
        self.assertEqual(receipt['evidence_status'], 'failed')
        self.assertEqual(receipt['token_usage']['total_tokens'], 127)
        self.assertEqual(self.store.export_json(self.cid), before)
        self.assertEqual(self.quota.budget_snapshot(self.settings, self.settings.principal)['daily_calls_remaining'], 19)
        return d

    def test_prompt_requires_explicit_title_quote_and_document_scope(self):
        for prompt in (m.PROMPT, m.CANDIDATE_PROMPT):
            for fragment in ('EDR/DSSAD术语必须出现在本条sources.quote中', '文件名或未引用的标题不能代替引文',
                             '同一文档的解析标题作为独立来源引用', '标题只标识材料，不证明技术功能或数据真实存在',
                             '不得把一个文档的术语、字段或功能转移到另一文档', '跨文件问题明确区分各文档的核查对象'):
                with self.subTest(fragment=fragment):
                    self.assertIn(fragment, prompt)

    def test_title_exists_in_verified_snapshot_but_is_not_implicitly_cited(self):
        self.assertIn('EDR', next(d for d in self.batch['documents'] if d['document_id'] == self.ids['D04'])['file_name'])
        self.assertTrue(self.ref(TITLE))
        self.assertNotIn('EDR', BODY)
        self.reject(self.payload())

    def test_body_quote_with_separate_same_document_title_is_accepted(self):
        result = self.analyze(self.payload(refs=[self.ref(BODY), self.ref(TITLE)]))
        row = result['pending_evidence'][0]
        self.assertEqual(row['text'], BODY)
        self.assertEqual(row['reasoning'], QUESTION)
        self.assertEqual([r['quote'] for r in row['sources']], [BODY, TITLE])
        self.assertEqual(result['receipt']['semantic_status'], 'pending_human_review')
        self.assertEqual(self.store.get_case(self.cid).inferences, [])

    def test_explicit_title_is_not_imported_as_confirmed_case_fact(self):
        result = self.analyze(self.payload(refs=[self.ref(BODY), self.ref(TITLE)]))
        m.import_case_analysis(self.store, self.cid, result)
        case = self.store.get_case(self.cid)
        self.assertEqual(case.facts, [])
        self.assertEqual(len(case.inferences), 1)
        self.assertEqual(case.inferences[0].text, QUESTION)
        self.assertEqual(case.inferences[0].verification, 'unverified')
        quotes = [case.evidence[e].quote for e in case.inferences[0].evidence_ids]
        self.assertCountEqual(quotes, [BODY, TITLE])
        for eid in case.inferences[0].evidence_ids:
            span = case.evidence[eid]
            self.assertEqual(span.document_id, self.ids['D04'])
            doc = case.documents[span.document_id]
            self.assertEqual(doc.units[span.unit_index]['text'][span.start:span.end], span.quote)
            self.assertEqual(span.document_sha256, doc.file_sha256)
        self.assertEqual(case.reviews, [])

    def test_term_in_original_body_quote_is_accepted(self):
        result = self.analyze(self.payload(refs=[self.ref(EDR_BODY)], text=EDR_BODY,
                    reasoning='待核实推断：D04的EDR相对触发锚点与绝对时刻的对应关系是否需要核对？'))
        self.assertEqual(result['receipt']['evidence_status'], 'passed')

    def test_fabricated_title_cannot_be_accepted_as_metadata(self):
        ref = self.ref(BODY)
        ref['quote'] = '模拟材料：DSSAD摘要'
        self.reject(self.payload(reasoning='待核实推断：DSSAD摘要的来源是否需要核对？', refs=[self.ref(BODY), ref]), 'quote_not_found')

    def test_title_cannot_be_bound_to_another_documents_source_id(self):
        fake = self.ref(SITE, 'D01')
        fake['quote'] = TITLE
        self.reject(self.payload(refs=[self.ref(BODY), fake]), 'quote_not_found')

    def test_renaming_file_to_include_dssad_does_not_supply_quote(self):
        self.store._cases[self.cid].documents[self.ids['D04']].file_name = '模拟_DSSAD_EDR摘要.pdf'
        self.batch = m.prepare_case(self.store, self.cid, list(self.ids.values()), self.settings)
        self.reject(self.payload(reasoning='待核实推断：D04的DSSAD字段是否需要核对？'))

    def test_edr_title_does_not_authorize_dssad(self):
        self.reject(self.payload(reasoning='待核实推断：D04的DSSAD记录是否需要核对？',
                                 refs=[self.ref(BODY), self.ref(TITLE)]))

    def test_edr_body_does_not_authorize_dssad(self):
        self.reject(self.payload(reasoning='待核实推断：EDR与DSSAD是否属于同一数据记录？',
                                 refs=[self.ref(EDR_BODY)], text=EDR_BODY))

    def test_negated_unsupported_term_is_not_a_license_to_introduce_it(self):
        self.reject(self.payload(reasoning='待核实推断：DSSAD是否不存在？'))

    def test_asserted_data_existence_still_rejected_with_valid_edr_citation(self):
        self.reject(self.payload(reasoning='待核实推断：EDR必然存在的原始数据是否需要核查？',
                                 refs=[self.ref(BODY), self.ref(TITLE)]), 'asserted_data_existence')

    def test_term_support_does_not_bypass_contiguous_text_requirement(self):
        self.reject(self.payload(refs=[self.ref(BODY), self.ref(TITLE)],
                                 text='EDR摘要缺失原始数据，因而不可信。'), 'text_not_in_quote')

    def test_valid_cross_document_question_preserves_each_independent_source(self):
        refs = [self.ref(SITE, 'D01'), self.ref(EDR_BODY), self.ref(TITLE)]
        result = self.analyze(self.payload(refs=refs, text=SITE,
                    reasoning='待核实推断：D01的口述分钟与D04的EDR相对触发锚点之间是否有可核对的时钟基准？'))
        row = result['pending_evidence'][0]
        self.assertEqual(len(row['sources']), 3)
        self.assertEqual({r['document_id'] for r in row['sources']}, set(self.ids.values()))
        self.assertTrue(all(r['case_id'] == self.cid for r in row['sources']))

    def test_unreferenced_edr_document_cannot_license_other_document_question(self):
        self.reject(self.payload(refs=[self.ref(SITE, 'D01')], text=SITE,
                    reasoning='待核实推断：D01的EDR原始数据是否需要核查？'))

    def test_lexical_guard_does_not_certify_semantic_attribution(self):
        # 明确记录既有局限：引用集合的词面支持不是跨文件语义蕴涵校验，仍须人工拒绝错误归属。
        result = self.analyze(self.payload(refs=[self.ref(SITE, 'D01'), self.ref(TITLE)], text=SITE,
                    reasoning='待核实推断：D01的EDR相对锚点是否需要核查？'))
        self.assertEqual(result['receipt']['semantic_status'], 'pending_human_review')
        self.assertEqual(self.store.get_case(self.cid).inferences, [])
        self.assertEqual(self.store.get_case(self.cid).facts, [])

    def test_diagnostic_only_reports_fixed_missing_term_not_raw_text(self):
        d = self.reject(self.payload())
        self.assertEqual(d['unsupported_terms'], ['EDR'])
        self.assertEqual(d['term_support_scope'], 'explicit_quotes_only')
        self.assertEqual(d['stage'], 'inference')
        self.assertEqual(d['document_ids'], [self.ids['D04']])
        text = json.dumps(d, ensure_ascii=False)
        for private in (BODY, TITLE, QUESTION, 'offline-not-real'):
            self.assertNotIn(private, text)

    def test_diagnostic_multiple_terms_are_fixed_vocabulary(self):
        d = self.reject(self.payload(reasoning='待核实推断：EDR和DSSAD是否有可核对来源？'))
        self.assertEqual(d['unsupported_terms'], ['EDR', 'DSSAD'])

    def test_case_insensitive_edr_support_preserves_exact_quote(self):
        p = self.payload(reasoning=QUESTION.replace('EDR', 'edr'), refs=[self.ref(BODY), self.ref(TITLE)])
        result = self.analyze(p)
        self.assertEqual(result['pending_evidence'][0]['sources'][1]['quote'], TITLE)
        self.assertIn('edr', result['pending_evidence'][0]['reasoning'])

    def test_no_term_question_keeps_original_contract_without_title(self):
        p = self.payload(reasoning='待核实推断：原始二进制数据及提取过程镜像是否需要进一步核查？')
        result = self.analyze(p)
        self.assertEqual(len(result['pending_evidence'][0]['sources']), 1)
        self.assertEqual(result['pending_evidence'][0]['text'], BODY)

    def test_d04_failure_at_index_four_is_located_without_import(self):
        p = self.payload()
        safe = deepcopy(p['pending_evidence'][0])
        safe['reasoning'] = '待核实推断：原始二进制数据的来源是否需要核查？'
        p['pending_evidence'] = [deepcopy(safe) for _ in range(4)] + p['pending_evidence']
        before = self.store.export_json(self.cid)
        with self.assertRaises(m.MultiAIError) as caught:
            self.analyze(p)
        d = caught.exception.receipt['validation_diagnostic']
        self.assertEqual((d['section'], d['item_index'], d['stage'], d['rule']),
                         ('pending_evidence', 4, 'inference', 'unsupported_data_term'))
        self.assertEqual(d['document_ids'], [self.ids['D04']])
        self.assertEqual(d['unsupported_terms'], ['EDR'])
        self.assertEqual(self.store.export_json(self.cid), before)

    def test_explicit_dssad_boundary_in_d05_is_supported_not_a_presence_claim(self):
        manifest = json.loads((DATA/'manifest.json').read_text())
        entry = next(d for d in manifest['documents'] if d['material_id'] == 'D05')
        path = DATA/entry['path']
        self.ids['D05'] = self.store.attach_document(self.cid, path.name, path.read_bytes())
        self.batch = m.prepare_case(self.store, self.cid, list(self.ids.values()), self.settings)
        quote = 'L2场景使用ADAS状态日志，本材料不是DSSAD记录。'
        p = self.payload(text=quote, refs=[self.ref(quote, 'D05')],
            reasoning='待核实推断：D05明确说明不是DSSAD记录，其ADAS状态日志的来源是否需要核查？')
        result = self.analyze(p)
        self.assertEqual(result['pending_evidence'][0]['sources'][0]['document_id'], self.ids['D05'])
        self.assertEqual(result['receipt']['semantic_status'], 'pending_human_review')
        self.assertEqual(self.store.get_case(self.cid).facts, [])

    def test_relations_keep_same_explicit_term_support_rule(self):
        p = self.payload()
        p['pending_evidence'] = []
        p['relations'] = [{'left': self.ref(EDR_BODY), 'right': self.ref(SITE, 'D01'),
                          'relation_type': 'needs_verification',
                          'reasoning': '待核实推断：D04的EDR相对时标与D01的口述分钟是否有可核对的基准？'}]
        result = self.analyze(p)
        self.assertEqual(len(result['relations']), 1)
        self.assertEqual(result['relations'][0]['status'], 'candidate')
        self.assertEqual(result['receipt']['semantic_status'], 'pending_human_review')
