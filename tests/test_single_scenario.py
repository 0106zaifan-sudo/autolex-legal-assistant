"""单场景验收、费用保护与UI配置隔离：全部离线，不读取实际Secrets。"""
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
from ai_analysis import AIError, analyze_record, empty_analysis, prepare_request
from live_acceptance import (AcceptanceError, load_scenarios, preparation_report, preflight,
                             run_suite, selected_scenarios)
from security import Settings, QuotaStore
from test_live_acceptance import valid_result
from ui_isolation import isolated_ui_runtime

ROOT=Path(__file__).resolve().parents[1]
HASH='pbkdf2_sha256$200000$'+'ab'*16+'$'+'cd'*32
NOW=1793966400.0


class SingleScenarioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.settings=Settings(api_key='offline-not-real',password_hash=HASH,mode='local',single_instance=True,cooldown=1,provider='deepseek')
        self.quota=QuotaStore(self.root/'quota.sqlite3')
        self.loaded=load_scenarios()[1]

    def fake(self,record,*args,**kwargs):
        entry=next(e for e,r in self.loaded if r['文件SHA256']==record['文件SHA256'])
        result=valid_result(entry,record)
        result['call_receipt']={'execution_mode':'injected_test_client','provider':'deepseek','token_usage':None}
        return result

    def test_preparation_default_keeps_both_scenarios(self):
        report=preparation_report()
        self.assertEqual(report['selected_scenarios'],['SIM_A','SIM_B'])
        self.assertTrue(all(row['selected'] and row['call_status']=='not_run' for row in report['cases']))
        self.assertEqual(report['actual_live_attempts'],0)

    def test_preparation_single_retains_other_scene_as_explicitly_not_selected(self):
        for scenario in ('SIM_A','SIM_B'):
            report=preparation_report(scenario=scenario)
            self.assertEqual(report['selected_scenarios'],[scenario])
            for row in report['cases']:
                self.assertEqual(row['selected'],row['scenario_id']==scenario)
                self.assertEqual(row['call_status'],'not_run')
                self.assertEqual(row['not_run_reason'],'awaiting_execution' if row['selected'] else 'not_selected')
                self.assertIsNone(row['token_usage'])
                self.assertIsNone(row['provider_model'])

    def test_each_single_scene_calls_only_selected_and_finish_ignores_unselected(self):
        for scenario in ('SIM_A','SIM_B'):
            executor=Mock(side_effect=self.fake)
            report,directory=run_suite(self.settings,self.quota,self.settings.principal,self.root,
                                      confirm_paid=True,scenario=scenario,executor=executor)
            executor.assert_called_once()
            expected=next(r for e,r in self.loaded if e['id']==scenario)
            self.assertEqual(executor.call_args.args[0]['文件SHA256'],expected['文件SHA256'])
            self.assertNotIn('debug_rejected_samples',executor.call_args.kwargs)
            self.assertEqual(report['execution_mode'],'offline_test')
            self.assertEqual(report['actual_live_attempts'],0)
            self.assertEqual(report['phase'],'awaiting_human_review')
            self.assertEqual(report['acceptance_status'],'not_approved')
            for row in report['cases']:
                if row['selected']:
                    self.assertEqual(row['call_status'],'response_validated')
                    self.assertIsNone(row['not_run_reason'])
                    self.assertTrue((directory/(row['scenario_id']+'_analysis.json')).exists())
                else:
                    self.assertEqual(row['call_status'],'not_run')
                    self.assertEqual(row['not_run_reason'],'not_selected')
                    self.assertIsNone(row['automatic_checks'])
                    self.assertFalse((directory/(row['scenario_id']+'_analysis.json')).exists())
            self.assertIn('未选择，未运行',(directory/'report.md').read_text())

    def test_default_execution_still_invokes_both(self):
        executor=Mock(side_effect=self.fake)
        report,_=run_suite(self.settings,self.quota,self.settings.principal,self.root,confirm_paid=True,executor=executor)
        self.assertEqual(executor.call_count,2)
        self.assertTrue(all(row['call_status']=='response_validated' for row in report['cases']))

    def test_invalid_selection_never_executes(self):
        for scenario in ('SIM_C','sim_b','../SIM_B',[],False):
            executor=Mock()
            with self.subTest(scenario=scenario),self.assertRaises(AcceptanceError):
                run_suite(self.settings,self.quota,self.settings.principal,self.root,
                          confirm_paid=True,scenario=scenario,executor=executor)
            executor.assert_not_called()

    def test_single_scenario_still_requires_paid_confirmation(self):
        executor=Mock()
        with self.assertRaises(AcceptanceError):
            run_suite(self.settings,self.quota,self.settings.principal,self.root,scenario='SIM_B',executor=executor)
        executor.assert_not_called()

    def test_single_preflight_only_prepares_selected_and_uses_remaining_one_call_budget(self):
        selected=selected_scenarios(self.loaded,'SIM_B')
        budget=prepare_request(selected[0][1],self.settings)[2]
        settings=replace(self.settings,daily_limit=2,hourly_limit=2,
                         daily_input_chars=budget['input_chars']+7,hourly_input_chars=budget['input_chars']+7,
                         daily_request_bytes=budget['request_bytes']+11,hourly_request_bytes=budget['request_bytes']+11)
        lease=self.quota.reserve_ai(settings,settings.principal,now=NOW-10,input_chars=7,request_bytes=11)
        self.quota.release(lease)
        with patch('security.time.time',return_value=NOW),patch('live_acceptance.prepare_request',wraps=prepare_request) as prepare:
            self.assertEqual(preflight(settings,self.quota,settings.principal,selected),[budget])
            prepare.assert_called_once()
            self.assertEqual(prepare.call_args.args[0]['文件SHA256'],selected[0][1]['文件SHA256'])
            with self.assertRaises(AcceptanceError):preflight(settings,self.quota,settings.principal,self.loaded)
            remaining=QuotaStore(self.quota.path).budget_snapshot(settings,settings.principal)
        self.assertEqual(remaining['daily_calls_remaining'],1)
        self.assertEqual(remaining['daily_chars_remaining'],budget['input_chars'])
        self.assertEqual(remaining['daily_bytes_remaining'],budget['request_bytes'])

    def test_single_preflight_still_blocks_insufficient_calls_or_input_budget(self):
        loaded=selected_scenarios(self.loaded,'SIM_B')
        for settings in (replace(self.settings,daily_request_bytes=1),replace(self.settings,daily_input_chars=1)):
            with self.subTest(settings=settings),self.assertRaises(AcceptanceError):
                preflight(settings,self.quota,settings.principal,loaded)
        limited=replace(self.settings,daily_limit=1)
        lease=self.quota.reserve_ai(limited,limited.principal,now=NOW-10);self.quota.release(lease)
        with patch('security.time.time',return_value=NOW),self.assertRaises(AcceptanceError):
            preflight(limited,self.quota,limited.principal,loaded)

    def test_single_selection_still_checks_all_fixed_hashes(self):
        fixtures=self.root/'fixtures';shutil.copytree(ROOT/'acceptance_samples',fixtures)
        manifest=json.loads((fixtures/'manifest.json').read_text())
        (fixtures/manifest['scenarios'][0]['file']).write_bytes(b'modified simulated file')
        executor=Mock()
        with self.assertRaises(AcceptanceError):
            run_suite(self.settings,self.quota,self.settings.principal,self.root,root=fixtures,
                      confirm_paid=True,scenario='SIM_B',executor=executor)
        executor.assert_not_called()

    def test_single_failure_debug_capture_and_existing_ledger_are_preserved(self):
        import sample_debug
        from sim_b_debug import reproduction_cases
        fixture_root=self.root/'project';fixture_root.mkdir()
        shutil.copytree(ROOT/'acceptance_samples',fixture_root/'acceptance_samples')
        _,cases=reproduction_cases()
        payload=cases[0][1]  # 人工构造的facts[5]/S006错误，不是模型响应。
        response={'provider_status':'completed','call_status':'response_received','refused':False,
                  'output_text':json.dumps(payload,ensure_ascii=False),'token_usage':None}
        budget=prepare_request(self.loaded[1][1],self.settings)[2]
        settings=replace(self.settings,daily_limit=2,hourly_limit=2,
                         daily_input_chars=budget['input_chars']+7,hourly_input_chars=budget['input_chars']+7,
                         daily_request_bytes=budget['request_bytes']+11,hourly_request_bytes=budget['request_bytes']+11)
        lease=self.quota.reserve_ai(settings,settings.principal,now=NOW-10,input_chars=7,request_bytes=11)
        self.quota.release(lease)
        def executor(record,settings,store,principal,consent,**kwargs):
            return analyze_record(record,settings,store,principal,consent,Mock(),**kwargs)
        with patch.object(sample_debug,'ROOT',fixture_root),patch('security.time.time',return_value=NOW),patch('ai_analysis.invoke',return_value=response) as invoke:
            report,directory=run_suite(settings,self.quota,settings.principal,self.root,
                                      confirm_paid=True,scenario='SIM_B',debug_rejected_samples=True,executor=executor)
            invoke.assert_called_once()
            remaining=QuotaStore(self.quota.path).budget_snapshot(settings,settings.principal)
        a,b=report['cases']
        self.assertEqual(a['call_status'],'not_run');self.assertEqual(a['not_run_reason'],'not_selected')
        self.assertEqual(b['call_status'],'failed')
        self.assertEqual(b['call_receipt']['debug_capture']['status'],'saved')
        self.assertEqual(b['call_receipt']['debug_capture']['fixture_id'],'SIM_B')
        self.assertEqual(report['actual_live_attempts'],0)
        self.assertEqual(remaining['daily_calls_remaining'],0)
        self.assertEqual(remaining['daily_chars_remaining'],0)
        self.assertEqual(remaining['daily_bytes_remaining'],0)
        self.assertFalse((directory/'SIM_B_analysis.json').exists())
        self.assertEqual(len(list((fixture_root/'.autolex_runtime'/'rejected_sample_debug').glob('*.json'))),1)


class VirtualConfigPath:
    """CLI测试专用内存路径，不会打开、创建或更改真实Secrets。"""
    def __truediv__(self,part):return self
    def is_file(self):return True
    def is_symlink(self):return False
    def stat(self):return SimpleNamespace(st_mode=0o100600)
    def open(self,*args,**kwargs):return io.BytesIO(b'')


class SingleScenarioCLITests(unittest.TestCase):
    def test_scenario_only_prepares_without_loading_config_password_or_model(self):
        from tools import run_live_acceptance as cli
        with tempfile.TemporaryDirectory() as tmp,patch.object(cli,'ROOT',Path(tmp)),patch.object(cli.Settings,'from_secrets') as config,patch.object(cli.getpass,'getpass') as password,patch.object(cli,'run_suite') as run,patch('sys.stdout',new_callable=io.StringIO):
            self.assertEqual(cli.main(['--scenario','SIM_B']),0)
            report=json.loads((Path(tmp)/'.autolex_runtime'/'acceptance'/'preparation'/'report.json').read_text())
        self.assertEqual(report['selected_scenarios'],['SIM_B'])
        self.assertEqual(report['cases'][0]['not_run_reason'],'not_selected')
        config.assert_not_called();password.assert_not_called();run.assert_not_called()

    def test_single_live_requires_paid_flag_before_reading_config(self):
        from tools import run_live_acceptance as cli
        with patch.object(cli.Settings,'from_secrets') as config,patch.object(cli.getpass,'getpass') as password,patch.object(cli,'run_suite') as run:
            with self.assertRaises(AcceptanceError):cli.main(['--run-live','--scenario','SIM_B'])
        config.assert_not_called();password.assert_not_called();run.assert_not_called()

    def test_single_live_rejects_noninteractive_auth_before_config(self):
        from tools import run_live_acceptance as cli
        with patch.object(cli.sys.stdin,'isatty',return_value=False),patch.object(cli.Settings,'from_secrets') as config,patch.object(cli.getpass,'getpass') as password:
            with self.assertRaises(AcceptanceError):cli.main(['--run-live','--confirm-paid-calls','--scenario','SIM_B'])
        config.assert_not_called();password.assert_not_called()

    def test_invalid_cli_scene_rejected_before_config_or_execution(self):
        from tools import run_live_acceptance as cli
        with patch.object(cli,'run_suite') as run,patch.object(cli.Settings,'from_secrets') as config,patch('sys.stderr',new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as error:cli.main(['--scenario','SIM_C'])
        self.assertEqual(error.exception.code,2)
        run.assert_not_called();config.assert_not_called()

    def call_fake_live(self, *, authenticated=True):
        from tools import run_live_acceptance as cli
        settings=Settings(api_key='offline-not-real',password_hash=HASH,mode='local',single_instance=True)
        report={'actual_live_attempts':0,'cases':[{'scenario_id':'SIM_A','selected':False,'call_status':'not_run'},
                                               {'scenario_id':'SIM_B','selected':True,'call_status':'response_validated'}]}
        with patch.object(cli,'ROOT',VirtualConfigPath()),patch.object(cli.sys.stdin,'isatty',return_value=True),patch.object(cli.tomllib,'load',return_value={}),patch.object(cli,'codespaces_values',return_value={}),patch.object(cli.Settings,'from_secrets',return_value=settings),patch.object(cli,'QuotaStore') as quota,patch.object(cli.getpass,'getpass',return_value='offline-simulation-password'),patch.object(cli,'verify_password',return_value=authenticated),patch.object(cli,'run_suite',return_value=(report,Path('/virtual/reports'))) as run,patch('sys.stdout',new_callable=io.StringIO):
            args=['--run-live','--confirm-paid-calls','--scenario','SIM_B','--debug-rejected-samples']
            if authenticated:
                result=cli.main(args)
            else:
                with self.assertRaises(AcceptanceError):cli.main(args)
                result=None
            quota.return_value.reserve_login.assert_called_once()
        return result,run

    def test_single_success_exit_and_debug_option_use_only_selected_rows(self):
        result,run=self.call_fake_live()
        self.assertEqual(result,0)
        self.assertEqual(run.call_args.kwargs['scenario'],'SIM_B')
        self.assertIs(run.call_args.kwargs['confirm_paid'],True)
        self.assertIs(run.call_args.kwargs['debug_rejected_samples'],True)

    def test_wrong_password_stops_before_execution(self):
        _,run=self.call_fake_live(authenticated=False)
        run.assert_not_called()


class UIIsolationTests(unittest.TestCase):
    def test_ambient_codespaces_keys_and_global_secrets_never_enter_ui_settings(self):
        import ai_ui
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        # 全部为显式虚构的宿主对象；不读取或覆盖真实os.environ/Secrets文件。
        ambient=SimpleNamespace(environ={'CODESPACES':'true','DEEPSEEK_API_KEY':'ambient-simulated-key','OPENAI_API_KEY':'ambient-other-key'})
        class UnreadableSecrets:
            def __iter__(self):raise AssertionError('ambient Secrets must not be read')
        with patch.object(ai_ui,'os',ambient),patch.object(st,'secrets',UnreadableSecrets()),isolated_ui_runtime():
            # at.secrets为空也不能退回磁盘/全局Secrets。
            app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('应用已锁定' in item.value for item in app.error))
            app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30)
            app.secrets.update({'APP_MODE':'local','AI_PROVIDER':'deepseek'})
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(any('DEEPSEEK_API_KEY' in item.value for item in app.info))
            self.assertTrue(app.button(key='run_ai').disabled)

    def test_explicit_simulated_codespaces_environment_still_exercises_provider_bridge(self):
        import streamlit as st
        from ai_ui import load_settings
        with isolated_ui_runtime(environment={'CODESPACES':'true','DEEPSEEK_API_KEY':'explicit-offline-only'}):
            st.secrets._secrets={'AI_PROVIDER':'deepseek'}
            self.assertEqual(load_settings().api_key,'explicit-offline-only')
