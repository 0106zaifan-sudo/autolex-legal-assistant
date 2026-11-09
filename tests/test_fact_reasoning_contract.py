"""只使用虚构材料、本地Mock和官方SDK的HTTP Mock；不访问模型服务。"""
import json
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from pydantic import ValidationError
import httpx
from openai import OpenAI
import test_multidoc_ai as fixtures
from security import QuotaStore
from ai_analysis import empty_analysis, build_sources, validate_analysis, AIError


class FactReasoningContract(unittest.TestCase):
    def setUp(self):
        self.base = fixtures.MultiAI()
        self.base.setUp()
        self.addCleanup(self.base.tmp.cleanup)

    def test_schema_requires_exact_empty_string(self):
        schema = self.base.m.FactItem.model_json_schema()
        field = schema['properties']['reasoning']
        self.assertEqual(field['type'], 'string')
        self.assertEqual(field['maxLength'], 0)
        self.assertEqual(field['enum'], [''])
        self.assertIn('reasoning', schema['required'])
        self.assertNotIn('default', field)

    def test_both_non_inference_kinds_allow_empty_reasoning(self):
        for kind in ('事实', '主张'):
            with self.subTest(kind=kind):
                row = self.base.row(kind=kind)
                self.assertEqual(self.base.m.FactItem.model_validate(row).reasoning, '')

    def test_nonempty_and_nonstring_reasoning_rejected_without_coercion(self):
        for kind in ('事实', '主张'):
            for value in ('材料记载明确', '待核实推断：是否有记录？', ' ', '\n', None, 0, [], {}):
                with self.subTest(kind=kind, value=value):
                    row = self.base.row(kind=kind)
                    row['reasoning'] = value
                    with self.assertRaises(ValidationError):
                        self.base.m.FactItem.model_validate(row)
                    self.assertEqual(row['reasoning'], value)

    def test_missing_reasoning_not_filled_automatically(self):
        row = self.base.row()
        del row['reasoning']
        with self.assertRaises(ValidationError):
            self.base.m.FactItem.model_validate(row)

    def test_prompt_explicit_for_both_kinds(self):
        prompt = self.base.m.PROMPT
        self.assertIn('kind=事实或kind=主张', prompt)
        self.assertIn('reasoning必须为严格的空字符串""', prompt)

    def test_legacy_validator_still_rejects_nonempty_reasoning(self):
        b = self.base
        record = next(iter(b.batch['records'].values()))
        source = build_sources(record)[0]
        for kind in ('事实', '主张'):
            raw = empty_analysis(record)
            raw['facts'] = [{'kind': kind, 'text': source['text'], 'reasoning': '不能静默删除',
                             'sources': [{'source_id': source['source_id'], 'quote': source['text']}]}]
            with self.assertRaises(AIError) as err:
                validate_analysis(raw, record, build_sources(record))
            self.assertEqual(str(err.exception), '事实或主张不允许附加未经核验的生成说明，结果已拒绝。')

    def test_inference_and_relation_reasoning_contract_unchanged(self):
        b = self.base
        pending = b.row(kind='推断')
        self.assertEqual(b.m.InferenceItem.model_validate(pending).reasoning, pending['reasoning'])
        relation = b.payload()['relations'][0]
        self.assertEqual(b.m.RelationItem.model_validate(relation).reasoning, relation['reasoning'])
        self.assertEqual(b.m.InferenceItem.model_json_schema()['properties']['reasoning']['maxLength'], 600)
        self.assertEqual(b.m.RelationItem.model_json_schema()['properties']['reasoning']['maxLength'], 600)

    def sdk_run(self, provider, invalid=False):
        b = self.base
        settings = replace(b.settings, provider=provider, model='offline-model')
        batch = b.m.prepare_case(b.store, b.cid, b.ids, settings)
        payload = b.payload()
        payload['batch_sha256'] = batch['batch_sha256']
        payload['facts'][1]['kind'] = '主张'
        if invalid:
            payload['facts'][0]['reasoning'] = 'PRIVATE_MOCK_REASONING_DO_NOT_LOG'
        original = deepcopy(payload)
        before = b.store.export_json(b.cid)
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={
                'id': 'mock-contract', 'object': 'response', 'created_at': 1, 'model': 'offline-mock',
                'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 30, 'total_tokens': 130},
                'output': [{'id': 'mock-message', 'type': 'message', 'role': 'assistant', 'status': 'completed',
                            'content': [{'type': 'output_text', 'text': json.dumps(payload, ensure_ascii=False), 'annotations': []}]}]})

        def factory(**kwargs):
            self.assertEqual(kwargs['max_retries'], 0)
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler)))

        quota = QuotaStore(Path(b.tmp.name) / (provider + str(invalid) + '.sqlite3'))
        kwargs = dict(authorized_batch=batch['batch_sha256'], client_factory=factory)
        if invalid:
            with self.assertRaises(b.m.MultiAIError) as caught:
                b.m.analyze_case(b.store, b.cid, b.ids, settings, quota, settings.principal, **kwargs)
            receipt = caught.exception.receipt
            diag = receipt['validation_diagnostic']
            self.assertEqual((diag['stage'], diag['section'], diag['item_index'], diag['rule']),
                             ('format', 'facts', 0, 'schema_rejected'))
            self.assertEqual(diag['source_ids'], [payload['facts'][0]['sources'][0]['source_id']])
            self.assertEqual(receipt['format_status'], 'failed_or_unavailable')
            self.assertEqual(receipt['evidence_status'], 'not_run')
            self.assertEqual(receipt['error_code'], 'output_validation_failed')
            self.assertNotIn('PRIVATE_MOCK_REASONING', json.dumps(receipt))
        else:
            result = b.m.analyze_case(b.store, b.cid, b.ids, settings, quota, settings.principal, **kwargs)
            receipt = result['receipt']
            self.assertEqual(receipt['evidence_status'], 'passed')
            self.assertTrue(all(row['reasoning'] == '' for row in result['facts']))
            self.assertTrue(result['relations'][0]['reasoning'])
        self.assertEqual(receipt['provider_status'], 'completed')
        self.assertEqual(receipt['token_usage']['total_tokens'], 130)
        self.assertEqual(quota.budget_snapshot(settings, settings.principal)['daily_calls_remaining'], 19)
        self.assertEqual(b.store.export_json(b.cid), before)
        self.assertEqual(payload, original)
        self.assertEqual(len(calls), 1)
        body = json.loads(calls[0].content)
        self.assertEqual(calls[0].url.host, 'api.deepseek.com' if provider == 'deepseek' else 'api.openai.com')
        field = body['text']['format']['schema']['$defs']['FactItem']['properties']['reasoning']
        self.assertEqual((field['maxLength'], field['enum']), (0, ['']))
        self.assertEqual(body['text']['format']['type'], 'json_schema')
        if provider == 'deepseek':
            self.assertNotIn('strict', body['text']['format'])
            self.assertNotIn('store', body)
            self.assertNotIn('truncation', body)
            self.assertEqual(body['reasoning'], {'effort': 'none'})
        else:
            self.assertTrue(body['text']['format']['strict'])
            self.assertFalse(body['store'])

    def test_deepseek_sdk_mock_accepts_empty_reasoning(self):
        self.sdk_run('deepseek')

    def test_deepseek_sdk_mock_rejects_nonempty_reasoning_and_keeps_usage(self):
        self.sdk_run('deepseek', invalid=True)

    def test_openai_sdk_mock_accepts_empty_reasoning(self):
        self.sdk_run('openai')

    def test_openai_sdk_mock_rejects_nonempty_reasoning_and_keeps_usage(self):
        self.sdk_run('openai', invalid=True)

    def test_import_revalidates_tampered_reasoning_without_mutation(self):
        b = self.base
        result, _ = b.run_ai()
        before = b.store.export_json(b.cid)
        result['raw_output']['facts'][0]['reasoning'] = '不应自动删除'
        with self.assertRaises(b.m.MultiAIError):
            b.m.import_case_analysis(b.store, b.cid, result)
        self.assertEqual(result['raw_output']['facts'][0]['reasoning'], '不应自动删除')
        self.assertEqual(b.store.export_json(b.cid), before)
