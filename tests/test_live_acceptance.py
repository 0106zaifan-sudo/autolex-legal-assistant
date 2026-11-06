"""离线准备/预算/SDK记录/硬截止测试。此文件不执行真实模型调用。"""
from copy import deepcopy
from dataclasses import replace
import io
import json
import multiprocessing
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import httpx
from openai import OpenAI
from security import Settings,QuotaStore,SecurityError
from ai_analysis import (AIError,Analysis,analyze_record,analysis_context,empty_analysis,
                         prepare_request,build_sources,validate_analysis)
from live_acceptance import (SAMPLES,AcceptanceError,load_scenarios,preparation_report,
                             preflight,run_suite)
from model_runtime import run_process,ModelRuntimeError

HASH='pbkdf2_sha256$200000$'+'ab'*16+'$'+'cd'*32


def sleeping_worker(connection):
    time.sleep(30)


def completed_worker(connection):
    connection.send_bytes(b'{"call_status":"response_received","token_usage":null}')
    connection.close()


def invalid_worker(connection):
    connection.send_bytes(b'not json')
    connection.close()


def valid_result(entry,record):
    raw=empty_analysis(record)
    sources=build_sources(record)
    def ref(quote):
        s=next(s for s in sources if quote in s['text'])
        return {'source_id':s['source_id'],'quote':quote}
    def item(quote,kind='事实',reason=''):
        return {'kind':kind,'text':quote,'reasoning':reason,'sources':[ref(quote)]}
    for phrase in entry['gold']['fact_phrases']:
        quote=next(u['text'] for u in record['units'] if phrase in u['text'])
        raw['facts'].append(item(quote))
    for phrase in entry['gold']['claim_phrases']:
        quote=next(u['text'] for u in record['units'] if phrase in u['text'])
        raw['facts'].append(item(quote,'主张'))
    for event in entry['gold']['timeline']:
        row=item(event['quote']);r=ref(event['quote'])
        row.update(event_source=r,time_source=r if event['time_state']=='explicit' else None,
                   **{k:event[k] for k in ('time_state','time_text','time_precision')})
        raw['timeline'].append(row)
    quote=record['units'][-1]['text']
    raw['pending_evidence']=[item(quote,'推断','待核实推断：原始日志是否完整？')]
    return validate_analysis(raw,record,sources)


def provider_response(payload):
    return {'id':'resp_unit_test_only','object':'response','created_at':1,
            'model':'mock-returned-snapshot','status':'completed',
            'usage':{'input_tokens':123,'output_tokens':45,'total_tokens':168},
            'output':[{'id':'msg_test','type':'message','role':'assistant','status':'completed',
                       'content':[{'type':'output_text','text':json.dumps(payload,ensure_ascii=False),'annotations':[]}]}]}


class InputBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'quota.sqlite3';self.q=QuotaStore(self.path)
        self.s=Settings(password_hash=HASH,daily_limit=20,hourly_limit=20,cooldown=1,
                        daily_input_chars=10,hourly_input_chars=10,daily_request_bytes=100,hourly_request_bytes=100,
                        max_request_bytes=50)
        self.now=1793923200.0

    def test_cumulative_chars_and_bytes_survive_reopen(self):
        a=self.q.reserve_ai(self.s,self.s.principal,now=self.now,input_chars=3,request_bytes=30);self.q.release(a)
        b=self.q.reserve_ai(self.s,self.s.principal,now=self.now+2,input_chars=4,request_bytes=30);self.q.release(b)
        other=QuotaStore(self.path)
        with self.assertRaises(SecurityError):other.reserve_ai(self.s,self.s.principal,now=self.now+4,input_chars=4,request_bytes=1)
        with self.assertRaises(SecurityError):other.reserve_ai(self.s,self.s.principal,now=self.now+4,input_chars=1,request_bytes=41)
        snapshot=other.budget_snapshot(self.s,self.s.principal,now=self.now+4)
        self.assertEqual(snapshot['daily_chars_remaining'],3)
        self.assertEqual(snapshot['daily_bytes_remaining'],40)

    def test_rotating_password_cannot_reset_daily_input_budget(self):
        lease=self.q.reserve_ai(self.s,self.s.principal,now=self.now,input_chars=9,request_bytes=10);self.q.release(lease)
        other=replace(self.s,password_hash=HASH+'different')
        with self.assertRaises(SecurityError):self.q.reserve_ai(other,other.principal,now=self.now+2,input_chars=2,request_bytes=1)

    def test_request_byte_cap_and_invalid_counters_fail_before_reservation(self):
        for chars,bytes_ in [(1,51),(-1,1),(True,1)]:
            with self.subTest(chars=chars,bytes_=bytes_),self.assertRaises(SecurityError):
                self.q.reserve_ai(self.s,self.s.principal,input_chars=chars,request_bytes=bytes_)
        self.assertEqual(self.q.budget_snapshot(self.s,self.s.principal)['daily_calls_remaining'],20)

    def test_old_ledger_is_migrated_without_treating_unknown_input_as_zero(self):
        old=Path(self.tmp.name)/'old.sqlite3'
        with sqlite3.connect(old) as db:
            db.execute('CREATE TABLE events(kind TEXT,principal TEXT,ts REAL,lease TEXT,active_until REAL)')
            db.execute('INSERT INTO events VALUES(?,?,?,?,?)',('ai',self.s.principal,self.now,'old',0))
        q=QuotaStore(old);s=replace(self.s,daily_input_chars=100000,hourly_input_chars=50000,
                                  daily_request_bytes=512000,hourly_request_bytes=256000)
        snapshot=q.budget_snapshot(s,s.principal,now=self.now+2)
        self.assertEqual(snapshot['daily_chars_remaining'],76000)
        self.assertEqual(snapshot['hourly_bytes_remaining'],0)
        with sqlite3.connect(old) as db:
            self.assertEqual(db.execute('SELECT budget_basis FROM events').fetchone()[0],'legacy_upper_bound')

    def test_new_budget_and_deadline_config_bounds(self):
        for config in ({'AI_TOTAL_TIMEOUT_SECONDS':91},{'AI_DAILY_INPUT_CHARS':0},
                       {'AI_MAX_REQUEST_BYTES':300000},{'AI_HOURLY_REQUEST_BYTES':True}):
            with self.subTest(config=config),self.assertRaises(SecurityError):Settings.from_secrets(config)


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.entry,self.record=load_scenarios()[1][0]
        self.settings=Settings(api_key='mock-test-key-not-real',password_hash=HASH,mode='local',single_instance=True)
        self.quota=QuotaStore(Path(self.tmp.name)/'quota.sqlite3')
        self.requests=[]

    def factory(self,payload=None,status=200):
        payload=payload or valid_result(self.entry,self.record)
        if 'sections' in payload:
            # 将正常化结果还原为模型原始契约，仅用于HTTP模拟响应。
            p=empty_analysis(self.record)
            for name,rows in payload['sections'].items():
                for row in rows:
                    item={k:row[k] for k in ('kind','text','reasoning')}
                    item['sources']=[{k:r[k] for k in ('source_id','quote')} for r in row['sources']]
                    if name=='timeline':
                        ref={k:row['event_source'][k] for k in ('source_id','quote')}
                        item.update(event_source=ref,time_source=ref if row['time_state']=='explicit' else None,
                                    **{k:row[k] for k in ('time_text','time_state','time_precision')})
                    p[name].append(item)
            payload=p
        def handler(request):
            self.requests.append(request)
            if status!=200:return httpx.Response(status,json={'error':{'message':'SECRET_PROVIDER_BODY','type':'test','code':'test'}})
            return httpx.Response(200,json=provider_response(payload))
        def factory(**kwargs):return OpenAI(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        return factory

    def test_actual_returned_identifier_usage_and_safe_budget_are_retained_in_mock_mode(self):
        result=analyze_record(self.record,self.settings,self.quota,self.settings.principal,True,self.factory())
        receipt=result['call_receipt']
        self.assertEqual(receipt['execution_mode'],'injected_test_client')
        self.assertEqual(receipt['requested_model'],'gpt-4.1-mini')
        self.assertEqual(receipt['provider_model'],'mock-returned-snapshot')
        self.assertEqual(receipt['token_usage']['input_tokens'],123)
        self.assertEqual(receipt['validation_status'],'passed')
        self.assertGreaterEqual(receipt['input_budget']['request_bytes'],len(self.requests[0].content))
        self.assertNotIn(self.settings.api_key,json.dumps(receipt))
        self.assertNotIn('output_text',receipt)

    def test_schema_failure_keeps_usage_and_does_not_save_analysis(self):
        with self.assertRaises(AIError) as caught:
            analyze_record(self.record,self.settings,self.quota,self.settings.principal,True,self.factory({'wrong':'schema'}))
        receipt=caught.exception.receipt
        self.assertEqual(receipt['validation_status'],'failed')
        self.assertEqual(receipt['validation_error_kind'],'schema')
        self.assertEqual(receipt['token_usage']['total_tokens'],168)
        self.assertEqual(receipt['provider_status'],'completed')

    def test_binding_failure_keeps_metadata_without_provider_body(self):
        payload=valid_result(self.entry,self.record)
        payload['sections']['timeline'][0]['time_text']='2099年1月1日'
        with self.assertRaises(AIError) as caught:
            analyze_record(self.record,self.settings,self.quota,self.settings.principal,True,self.factory(payload))
        self.assertEqual(caught.exception.receipt['validation_error_kind'],'evidence_binding')
        self.assertEqual(caught.exception.receipt['token_usage']['output_tokens'],45)

    def test_http_failure_usage_is_unknown_and_input_budget_not_refunded(self):
        with self.assertRaises(AIError) as caught:
            analyze_record(self.record,self.settings,self.quota,self.settings.principal,True,self.factory(status=401))
        receipt=caught.exception.receipt
        self.assertEqual(receipt['http_status'],401);self.assertIsNone(receipt['token_usage'])
        self.assertNotIn('SECRET_PROVIDER_BODY',json.dumps(receipt))
        q=QuotaStore(self.quota.path)
        remaining=q.budget_snapshot(self.settings,self.settings.principal)
        self.assertLess(remaining['daily_chars_remaining'],self.settings.daily_input_chars)
        self.assertEqual(len(self.requests),1)

    def test_default_production_path_uses_bounded_worker_not_parent_sdk(self):
        with patch('ai_analysis.invoke',side_effect=ModelRuntimeError('deadline_exceeded')) as invoke:
            with self.assertRaises(AIError) as caught:
                analyze_record(self.record,self.settings,self.quota,self.settings.principal,True)
        self.assertIsNone(invoke.call_args.args[3])
        self.assertEqual(caught.exception.code,'deadline_exceeded')
        self.assertEqual(caught.exception.receipt['execution_mode'],'live_sdk')
        self.assertIsNone(caught.exception.receipt['token_usage'])

    def test_create_schema_matches_official_sdk_structured_parse_schema(self):
        _,request,_=prepare_request(self.record,self.settings)
        # 在完全离线的官方SDK.parse调用中捕获其标准Schema，核对create没有弱化严格输出。
        calls=[]
        def handler(req):
            calls.append(json.loads(req.content))
            return httpx.Response(200,json=provider_response({'invalid':'not-used'}))
        client=OpenAI(api_key='mock-only',http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        try:client.responses.parse(model='mock',input='mock',text_format=Analysis)
        except ValueError:pass
        finally:client.close()
        self.assertEqual(calls[0]['text']['format'],request['text']['format'])


class DeadlineProcessTests(unittest.TestCase):
    def test_sleeping_worker_is_terminated_before_lease_expiry(self):
        before={p.pid for p in multiprocessing.active_children()};started=time.monotonic()
        with self.assertRaises(ModelRuntimeError) as caught:run_process(sleeping_worker,(),2)
        self.assertEqual(caught.exception.code,'deadline_exceeded')
        self.assertLess(time.monotonic()-started,5)
        self.assertEqual({p.pid for p in multiprocessing.active_children()},before)

    def test_worker_success_and_invalid_output_are_handled(self):
        self.assertEqual(run_process(completed_worker,(),5)['call_status'],'response_received')
        with self.assertRaises(ModelRuntimeError):run_process(invalid_worker,(),5)


class AcceptancePreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.settings=Settings(api_key='mock-test-key-not-real',password_hash=HASH,mode='local',single_instance=True)
        self.quota=QuotaStore(Path(self.tmp.name)/'quota.sqlite3')

    def test_preparation_report_has_two_simulated_inputs_and_no_fabricated_metrics(self):
        report=preparation_report()
        self.assertEqual(report['actual_live_attempts'],0)
        self.assertEqual(report['execution_mode'],'preparation_only')
        self.assertEqual(len(report['cases']),2)
        for case in report['cases']:
            self.assertEqual(case['call_status'],'not_run')
            self.assertIsNone(case['provider_model']);self.assertIsNone(case['token_usage'])
            self.assertIsNone(case['automatic_checks'])
        self.assertIsNone(report['accuracy'])

    def test_modified_sample_hash_or_escaped_path_is_rejected(self):
        root=Path(self.tmp.name)/'samples';shutil.copytree(SAMPLES,root)
        manifest=json.loads((root/'manifest.json').read_text())
        path=root/manifest['scenarios'][0]['file'];path.write_bytes(path.read_bytes()+b'modified')
        with self.assertRaises(AcceptanceError):load_scenarios(root)
        manifest['scenarios'][0]['file']='../outside.docx'
        (root/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(AcceptanceError):load_scenarios(root)

    def test_preflight_checks_single_instance_and_two_call_budget(self):
        loaded=load_scenarios()[1]
        for settings in (replace(self.settings,single_instance=False),replace(self.settings,daily_limit=1),
                         replace(self.settings,daily_request_bytes=10)):
            with self.subTest(settings=settings),self.assertRaises(AcceptanceError):
                preflight(settings,self.quota,settings.principal,loaded)
        self.assertEqual(len(preflight(self.settings,self.quota,self.settings.principal,loaded)),2)

    def test_mock_executor_cannot_be_reported_as_real_live_acceptance(self):
        loaded={record['文件SHA256']:entry for entry,record in load_scenarios()[1]}
        def fake(record,*args,**kwargs):
            result=valid_result(loaded[record['文件SHA256']],record)
            result['call_receipt']={'execution_mode':'injected_test_client','provider_model':'mock-only','token_usage':None}
            return result
        report,directory=run_suite(self.settings,self.quota,self.settings.principal,Path(self.tmp.name)/'runs',
                                   confirm_paid=True,executor=fake,sleeper=Mock())
        self.assertEqual(report['execution_mode'],'offline_test')
        self.assertEqual(report['actual_live_attempts'],0)
        self.assertEqual(report['acceptance_status'],'not_approved')
        self.assertTrue(all(c['automatic_checks']['status']=='passed' for c in report['cases']))
        self.assertTrue((directory/'report.json').is_file())
        with patch('live_acceptance.analyze_record',side_effect=fake):
            report,_=run_suite(self.settings,self.quota,self.settings.principal,Path(self.tmp.name)/'rejected',confirm_paid=True)
        self.assertEqual(report['actual_live_attempts'],0)
        self.assertTrue(all(c['call_status']=='blocked_before_call' for c in report['cases']))

    def test_no_explicit_paid_flag_means_no_executor_call(self):
        executor=Mock()
        with self.assertRaises(AcceptanceError):
            run_suite(self.settings,self.quota,self.settings.principal,self.tmp.name,executor=executor)
        executor.assert_not_called()

    def test_cli_preparation_never_loads_secret_config_or_prompts_for_password(self):
        from tools import run_live_acceptance as cli
        with patch.object(cli,'ROOT',Path(self.tmp.name)),patch.object(cli.Settings,'from_secrets') as load,patch.object(cli.getpass,'getpass') as password:
            self.assertEqual(cli.main([]),0)
            load.assert_not_called();password.assert_not_called()
            with self.assertRaises(AcceptanceError):cli.main(['--run-live','--confirm-paid-calls'])
            password.assert_not_called()

    def test_noninteractive_live_cli_never_reads_password_or_secrets(self):
        from tools import run_live_acceptance as cli
        with patch.object(cli.sys.stdin,'isatty',return_value=False),patch.object(cli.Settings,'from_secrets') as load,patch.object(cli.getpass,'getpass') as password:
            with self.assertRaises(AcceptanceError):cli.main(['--run-live','--confirm-paid-calls'])
            password.assert_not_called();load.assert_not_called()

    def test_cancelled_batch_does_not_attempt_second_input(self):
        error=AIError('模拟取消',code='cancelled',receipt={'execution_mode':'injected_test_client','token_usage':None})
        executor=Mock(side_effect=error)
        report,_=run_suite(self.settings,self.quota,self.settings.principal,self.tmp.name,confirm_paid=True,executor=executor)
        self.assertEqual(executor.call_count,1)
        self.assertEqual(report['actual_live_attempts'],0)
        self.assertEqual(report['cases'][1]['call_status'],'not_run')

    def test_relative_ledger_path_is_consistent_for_cli_and_streamlit(self):
        import security
        settings=Settings.from_secrets({'AI_LIMIT_DB':'.autolex_runtime/test.sqlite3'})
        self.assertEqual(Path(settings.db_path),Path(security.__file__).resolve().parent/'.autolex_runtime'/'test.sqlite3')
