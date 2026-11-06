"""DeepSeek离线验收：官方SDK+MockTransport，绝不作为真实模型效果证据。"""
from ui_isolation import IsolatedUITestCase
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
from openai import OpenAI
from ai_providers import get_provider, codespaces_values, billing_record
from ai_analysis import analyze_record, AIError, prepare_request, empty_analysis, build_sources
from core import extract
from live_acceptance import load_scenarios, run_suite, preparation_report
from model_runtime import invoke, ModelRuntimeError
from security import Settings, QuotaStore, SecurityError

ROOT = Path(__file__).resolve().parents[1]
HASH = 'pbkdf2_sha256$200000$' + 'ab'*16 + '$' + 'cd'*32
USAGE = {'input_tokens': 123, 'input_tokens_details': {'cached_tokens': 23},
         'output_tokens': 45, 'output_tokens_details': {'reasoning_tokens': 0}, 'total_tokens': 168}


def gold_payload(entry, record):
    """清单给定答案，非模型推理；只验证SIM_A/B的SDK、校验及报告通路。"""
    raw = empty_analysis(record)
    sources = build_sources(record)
    def ref(quote):
        return {'source_id': next(s['source_id'] for s in sources if quote in s['text']), 'quote': quote}
    def row(quote, kind='事实', reasoning=''):
        return {'kind': kind, 'text': quote, 'reasoning': reasoning, 'sources': [ref(quote)]}
    for section, kind in [('fact_phrases', '事实'), ('claim_phrases', '主张')]:
        for phrase in entry['gold'][section]:
            quote = next(u['text'] for u in record['units'] if phrase in u['text'])
            raw['facts'].append(row(quote, kind))
    for event in entry['gold']['timeline']:
        value = row(event['quote'])
        value.update(event_source=ref(event['quote']),
                     time_source=ref(event['quote']) if event['time_state']=='explicit' else None,
                     **{k: event[k] for k in ('time_state', 'time_text', 'time_precision')})
        raw['timeline'].append(value)
    raw['pending_evidence'] = [row(record['units'][-1]['text'], '推断', '待核实推断：原始日志是否完整？')]
    return raw


class ProviderConfigurationTests(unittest.TestCase):
    def test_defaults_keep_existing_openai(self):
        for settings in (Settings(), Settings.from_secrets({})):
            self.assertEqual(settings.provider, 'openai')
            self.assertEqual(settings.model, 'gpt-4.1-mini')

    def test_deepseek_defaults_and_selected_credentials_only(self):
        values = {'AI_PROVIDER':'deepseek', 'OPENAI_API_KEY':'offline-openai-only',
                  'DEEPSEEK_API_KEY':'offline-deepseek-only', 'OPENAI_MODEL':'wrong-provider-model'}
        settings = Settings.from_secrets(values)
        self.assertEqual(settings.api_key, 'offline-deepseek-only')
        self.assertEqual(settings.model, 'deepseek-flash')
        self.assertEqual(settings.provider_spec.base_url, 'https://api.deepseek.com')
        self.assertNotIn('offline-deepseek-only', repr(settings))
        values['AI_PROVIDER'] = 'openai'
        self.assertEqual(Settings.from_secrets(values).api_key, 'offline-openai-only')

    def test_missing_deepseek_key_does_not_use_openai_key(self):
        s = Settings.from_secrets({'AI_PROVIDER':'deepseek','OPENAI_API_KEY':'offline-only'})
        self.assertFalse(s.api_key)
        self.assertIn('DEEPSEEK_API_KEY', s.ai_disabled_reason(None))

    def test_missing_openai_key_does_not_use_deepseek_key(self):
        self.assertFalse(Settings.from_secrets({'DEEPSEEK_API_KEY':'offline-only'}).api_key)

    def test_unknown_provider_fails_closed(self):
        for provider in ('DEEPSEEK', '', 'https://untrusted.example', 'other'):
            with self.subTest(provider=provider), self.assertRaises(SecurityError):
                Settings.from_secrets({'AI_PROVIDER':provider})

    def test_provider_model_override_and_empty_model_rejection(self):
        self.assertEqual(Settings.from_secrets({'AI_PROVIDER':'deepseek','DEEPSEEK_MODEL':'custom-model'}).model, 'custom-model')
        with self.assertRaises(SecurityError):
            Settings.from_secrets({'AI_PROVIDER':'deepseek','DEEPSEEK_MODEL':' '})

    def test_codespaces_reads_only_selected_key_and_preserves_explicit_secret(self):
        env = {'CODESPACES':'true','DEEPSEEK_API_KEY':'offline-codespaces','OPENAI_API_KEY':'unused'}
        config = codespaces_values({'AI_PROVIDER':'deepseek'}, env)
        self.assertNotIn('OPENAI_API_KEY', config)
        self.assertEqual(Settings.from_secrets(config).api_key, 'offline-codespaces')
        config = codespaces_values({'AI_PROVIDER':'deepseek','DEEPSEEK_API_KEY':'offline-explicit'}, env)
        self.assertEqual(Settings.from_secrets(config).api_key, 'offline-explicit')

    def test_regular_environment_does_not_supply_key(self):
        config = codespaces_values({'AI_PROVIDER':'deepseek'}, {'DEEPSEEK_API_KEY':'offline-env'})
        self.assertFalse(Settings.from_secrets(config).api_key)

    def test_fee_unknown_is_not_zero_and_cache_usage_is_not_double_counted(self):
        record = billing_record(USAGE)
        self.assertEqual(record['input_tokens'],123)
        self.assertEqual(record['cached_input_tokens'],23)
        self.assertEqual(record['uncached_input_tokens'],100)
        self.assertEqual(record['total_tokens'],168)
        self.assertIsNone(record['amount'])
        self.assertEqual(record['status'],'not_reconciled')
        self.assertIsNone(billing_record(None)['total_tokens'])
        self.assertIsNone(billing_record({'input_tokens':True})['input_tokens'])
        self.assertIsNone(billing_record({'input_tokens':1,'input_tokens_details':{'cached_tokens':2}})['uncached_input_tokens'])


class DeepSeekSDKTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(provider='deepseek', api_key='offline-test-not-real', password_hash=HASH,
                                 mode='public', single_instance=True, cooldown=1)
        self.quota = QuotaStore(Path(self.tmp.name)/'quota.sqlite3')
        path = ROOT/'samples_ai'/'模拟_AI事故材料.docx'
        self.record = extract(path.name,path.read_bytes())
        self.payload = json.loads((ROOT/'samples_ai'/'mock_analysis.json').read_text())
        self.requests = []

    def factory(self, payload=None, status=200, state='completed', usage=USAGE, exception=None):
        def handler(request):
            self.requests.append(request)
            self.assertEqual(str(request.url),'https://api.deepseek.com/responses')
            self.assertEqual(request.headers['authorization'],'Bearer offline-test-not-real')
            if exception: raise exception
            if status != 200:
                return httpx.Response(status,json={'error':{'message':'SECRET_BODY_NOT_FOR_REPORT','type':'test'}})
            response = {'id':'resp_offline_deepseek','object':'response','created_at':1,
                        'model':'deepseek-flash-mock-not-real-version','status':state,'usage':usage,
                        'output':[{'id':'msg_offline','type':'message','role':'assistant','status':'completed',
                                   'content':[{'type':'output_text','annotations':[],
                                               'text':json.dumps(self.payload if payload is None else payload,ensure_ascii=False)}]}]}
            return httpx.Response(200,json=response)
        def create(**kwargs):
            self.assertEqual(kwargs['base_url'],'https://api.deepseek.com')
            self.assertEqual(kwargs['timeout'],30.0)
            self.assertEqual(kwargs['max_retries'],0)
            return OpenAI(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        return create

    def analyze(self, **kwargs):
        return analyze_record(self.record,self.settings,self.quota,self.settings.principal,True,self.factory(**kwargs))

    def test_deepseek_sdk_schema_and_safe_request_parameters(self):
        result = self.analyze()
        request = json.loads(self.requests[0].content)
        self.assertEqual(request['model'],'deepseek-flash')
        self.assertEqual(request['text']['format']['type'],'json_schema')
        self.assertEqual(request['text']['format']['schema'],prepare_request(self.record,self.settings)[1]['text']['format']['schema'])
        self.assertNotIn('strict',request['text']['format'])
        self.assertNotIn('store',request); self.assertNotIn('truncation',request)
        self.assertEqual(request['reasoning'],{'effort':'none'})
        self.assertEqual(request['max_output_tokens'],4000)
        self.assertEqual(result['call_receipt']['execution_mode'],'injected_test_client')
        self.assertEqual(result['call_receipt']['provider'],'deepseek')
        self.assertEqual(result['call_receipt']['validation_status'],'passed')
        self.assertNotIn(self.settings.api_key,json.dumps(result))

    def test_usage_cache_reasoning_fields_and_unknown_amount_retained(self):
        receipt = self.analyze()['call_receipt']
        self.assertEqual(receipt['token_usage'],USAGE)
        self.assertEqual(receipt['billing']['uncached_input_tokens'],100)
        self.assertEqual(receipt['billing']['reasoning_tokens'],0)
        self.assertIsNone(receipt['billing']['amount'])
        self.assertEqual(receipt['provider_model'],'deepseek-flash-mock-not-real-version')

    def test_missing_usage_is_unknown(self):
        receipt = self.analyze(usage=None)['call_receipt']
        self.assertIsNone(receipt['token_usage'])
        self.assertIsNone(receipt['billing']['input_tokens'])
        self.assertIsNone(receipt['billing']['amount'])

    def test_malformed_json_structure_keeps_usage_but_rejects_analysis(self):
        with self.assertRaises(AIError) as caught: self.analyze(payload={'wrong':'schema'})
        self.assertEqual(caught.exception.code,'output_validation_failed')
        self.assertEqual(caught.exception.receipt['validation_error_kind'],'schema')
        self.assertEqual(caught.exception.receipt['token_usage'],USAGE)

    def test_event_time_binding_not_weakened_for_deepseek(self):
        payload = deepcopy(self.payload)
        payload['timeline'][0]['time_text'] = '2099年1月1日'
        with self.assertRaises(AIError) as caught: self.analyze(payload=payload)
        self.assertEqual(caught.exception.receipt['validation_error_kind'],'evidence_binding')
        self.assertEqual(caught.exception.receipt['billing']['total_tokens'],168)

    def test_http_errors_safe_no_retry_unknown_bill_and_budget_not_refunded(self):
        for status, code in [(400,'provider_error'),(401,'authentication_failed'),(402,'provider_error'),
                             (429,'rate_limited'),(500,'provider_error')]:
            with self.subTest(status=status):
                self.quota = QuotaStore(Path(self.tmp.name)/f'quota-{status}.sqlite3')
                before = len(self.requests)
                with self.assertRaises(AIError) as caught: self.analyze(status=status)
                receipt = caught.exception.receipt
                self.assertEqual(caught.exception.code,code)
                self.assertEqual(receipt['http_status'],status)
                self.assertEqual(len(self.requests)-before,1)
                self.assertIsNone(receipt['billing']['amount'])
                self.assertNotIn('SECRET_BODY_NOT_FOR_REPORT',json.dumps(receipt))
                self.assertLess(self.quota.budget_snapshot(self.settings,self.settings.principal)['daily_chars_remaining'],100000)

    def test_network_timeout_and_connection_errors_are_safe(self):
        for i, (exception, code) in enumerate([(httpx.ReadTimeout('SECRET_BODY_NOT_FOR_REPORT'),'network_timeout'),
                                               (httpx.ConnectError('SECRET_BODY_NOT_FOR_REPORT'),'connection_failed')]):
            self.quota = QuotaStore(Path(self.tmp.name)/f'network-{i}.sqlite3')
            with self.assertRaises(AIError) as caught: self.analyze(exception=exception)
            self.assertEqual(caught.exception.code,code)
            self.assertNotIn('SECRET_BODY_NOT_FOR_REPORT',str(caught.exception))
            self.assertIsNone(caught.exception.receipt['billing']['amount'])

    def test_incomplete_output_does_not_save_partial_result(self):
        with self.assertRaises(AIError) as caught: self.analyze(state='incomplete')
        self.assertEqual(caught.exception.code,'refused_or_incomplete')
        self.assertEqual(caught.exception.receipt['token_usage'],USAGE)

    def test_deepseek_worker_keeps_process_deadline_and_provider(self):
        with patch('model_runtime.run_process',side_effect=ModelRuntimeError('deadline_exceeded')) as run:
            with self.assertRaises(AIError) as caught:
                analyze_record(self.record,self.settings,self.quota,self.settings.principal,True)
        self.assertEqual(run.call_args.args[1][-1],'deepseek')
        self.assertEqual(run.call_args.args[2],45)
        self.assertEqual(caught.exception.code,'deadline_exceeded')
        self.assertIsNone(caught.exception.receipt['billing']['amount'])

    def test_auth_consent_coverage_gates_block_before_sdk(self):
        with patch('ai_analysis.invoke') as call:
            for kwargs, code in [({'consent':False},'consent_required'),({'principal':'wrong'},'disabled')]:
                args = {'principal':self.settings.principal,'consent':True,**kwargs}
                with self.assertRaises(AIError) as caught:
                    analyze_record(self.record,self.settings,self.quota,**args)
                self.assertEqual(caught.exception.code,code)
            record = deepcopy(self.record)
            record['parse_report']['requires_acknowledgement'] = True
            with self.assertRaises(AIError) as caught:
                analyze_record(record,self.settings,self.quota,self.settings.principal,True)
            self.assertEqual(caught.exception.code,'coverage_confirmation_required')
            call.assert_not_called()

    def test_switching_provider_cannot_reset_global_call_or_input_budget(self):
        s = replace(self.settings,daily_limit=1)
        lease = self.quota.reserve_ai(s,s.principal,now=100000,input_chars=10,request_bytes=10)
        self.quota.release(lease)
        other = replace(s,provider='openai',model='gpt-4.1-mini')
        with self.assertRaises(SecurityError):
            self.quota.reserve_ai(other,other.principal,now=100002,input_chars=1,request_bytes=1)
        self.assertEqual(self.quota.budget_snapshot(other,other.principal,now=100002)['daily_chars_remaining'],99990)

    def test_sim_a_and_b_sdk_roundtrip_is_offline_not_real_acceptance(self):
        entries = {record['文件SHA256']:entry for entry,record in load_scenarios()[1]}
        def executor(record,settings,store,principal,consent,**kwargs):
            return analyze_record(record,settings,store,principal,consent,
                                  self.factory(payload=gold_payload(entries[record['文件SHA256']],record)),**kwargs)
        # 测试时不等待冷却；两次调用仍各自走原子SQLite预算检查。
        with patch('security.time.time',side_effect=[100000+i*2 for i in range(100)]):
            report,_ = run_suite(self.settings,self.quota,self.settings.principal,self.tmp.name,
                                confirm_paid=True,executor=executor,sleeper=lambda _:None)
        self.assertEqual(len(self.requests),2)
        self.assertEqual(report['provider'],'deepseek')
        self.assertEqual(report['execution_mode'],'offline_test')
        self.assertEqual(report['actual_live_attempts'],0)
        self.assertIsNone(report['accuracy'])
        self.assertTrue(all(c['call_status']=='response_validated' for c in report['cases']))
        self.assertTrue(all(c['automatic_checks']['status']=='passed' for c in report['cases']))
        self.assertEqual(report['acceptance_status'],'not_approved')

    def test_default_preparation_stays_provider_neutral_and_no_network(self):
        with patch('ai_analysis.invoke') as call:
            report = preparation_report()
            self.assertIsNone(report['provider'])
            self.assertEqual(report['actual_live_attempts'],0)
            call.assert_not_called()

    def test_wrong_provider_receipt_cannot_pass_real_batch_path(self):
        def wrong(record,*args,**kwargs):
            return {'call_receipt':{'execution_mode':'live_sdk','provider':'openai'}}
        with patch('live_acceptance.analyze_record',side_effect=wrong):
            report,_ = run_suite(self.settings,self.quota,self.settings.principal,self.tmp.name,confirm_paid=True)
        self.assertTrue(all(c['call_status']=='blocked_before_call' for c in report['cases']))
        self.assertEqual(report['actual_live_attempts'],0)

    def test_deepseek_balance_error_stops_before_second_material(self):
        error = AIError('模拟余额错误',code='provider_error',
                        receipt={'execution_mode':'injected_test_client','provider':'deepseek','http_status':402})
        with patch('live_acceptance.analyze_record',side_effect=error) as executor:
            # 显式注入以确保不计入真实尝试。
            report,_ = run_suite(self.settings,self.quota,self.settings.principal,self.tmp.name,
                                 confirm_paid=True,executor=executor)
        self.assertEqual(executor.call_count,1)
        self.assertEqual(report['cases'][1]['call_status'],'not_run')
        self.assertEqual(report['actual_live_attempts'],0)


class ProviderUITests(IsolatedUITestCase):
    def test_deepseek_without_key_disables_ai_and_names_correct_recipient(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as tmp, patch('ai_ui.analyze_record') as call:
            app = AppTest.from_file(str(ROOT/'app.py'),default_timeout=30)
            app.secrets['APP_MODE'] = 'local'
            app.secrets['AI_PROVIDER'] = 'deepseek'
            app.secrets['AI_LIMIT_DB'] = str(Path(tmp)/'quota.sqlite3')
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(app.button(key='run_ai').disabled)
            self.assertTrue(any('DEEPSEEK_API_KEY' in item.value for item in app.info))
            self.assertIn('DeepSeek API',app.checkbox(key='ai_consent').label)
            call.assert_not_called()

    def test_switching_provider_resets_consent_and_cached_result(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as tmp:
            app = AppTest.from_file(str(ROOT/'app.py'),default_timeout=30)
            app.secrets['APP_MODE'] = 'local'
            app.secrets['AI_LIMIT_DB'] = str(Path(tmp)/'quota.sqlite3')
            app.run()
            app.checkbox(key='ai_consent').check().run()
            app.session_state['_ai_result'] = {'record_id':'offline-only','value':{}}
            app.session_state['_last_ai_receipt'] = {'provider':'openai','execution_mode':'injected_test_client'}
            app.secrets['AI_PROVIDER'] = 'deepseek'
            app.run()
            self.assertFalse(app.exception)
            self.assertFalse(app.checkbox(key='ai_consent').value)
            self.assertNotIn('_ai_result',app.session_state)
            self.assertNotIn('_last_ai_receipt',app.session_state)
