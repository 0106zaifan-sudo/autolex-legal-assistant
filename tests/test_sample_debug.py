"""固定模拟样本调试的离线安全测试；不读取Secrets或使用真实SDK网络。"""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
import sample_debug
from sample_debug import capture_rejected_output, read_capture, fixed_record
from sim_b_debug import reproduction_cases, manual_report, replay_artifact
from ai_analysis import (AIError, analyze_record, empty_analysis)
from security import Settings
from live_acceptance import AcceptanceError, run_suite

ROOT = Path(__file__).resolve().parents[1]
HASH = 'pbkdf2_sha256$200000$'+'ab'*16+'$'+'cd'*32


class SIMBReproductionTests(unittest.TestCase):
    def test_nine_manual_cases_have_expected_classification_and_no_live_claim(self):
        with patch('sim_b_debug.capture_rejected_output') as capture:
            report = manual_report()
        capture.assert_not_called()
        self.assertEqual(report['execution_mode'],'manual_offline')
        self.assertEqual(report['actual_live_attempts'],0)
        self.assertIsNone(report['accuracy'])
        rows = {row['case_id']:row for row in report['cases']}
        self.assertEqual(len(rows),9)
        for name in ('s006_as_fact_index_5','directory_excerpt_full_quote','directory_excerpt_short_quote',
                     'driver_claim_as_fact','company_claim_as_fact'):
            self.assertTrue(rows[name]['schema_valid'])
            self.assertFalse(rows[name]['binding_valid'])
        for name in ('log_completeness_pending','driver_claim_kept','company_claim_kept','objective_receipt_record'):
            self.assertTrue(rows[name]['schema_valid'])
            self.assertTrue(rows[name]['binding_valid'])
        diagnostic = rows['s006_as_fact_index_5']['validation_diagnostic']
        self.assertEqual(diagnostic['section'],'facts')
        self.assertEqual(diagnostic['item_index'],5)
        self.assertEqual(diagnostic['source_id'],'S006')
        self.assertEqual(diagnostic['matched_markers'],['尚未核实'])
        self.assertEqual(rows['directory_excerpt_full_quote']['text'],'仅列出检查摘要')
        self.assertIn('尚未核实',rows['directory_excerpt_full_quote']['quote'])

    def test_offline_cli_does_not_read_config_or_call_model(self):
        from tools import replay_sim_b as cli
        with patch('ai_analysis.invoke') as invoke,patch('security.Settings.from_secrets') as secrets,patch('sys.stdout',new_callable=io.StringIO) as output:
            self.assertEqual(cli.main([]),0)
            report = json.loads(output.getvalue())
        self.assertEqual(report['actual_live_attempts'],0)
        invoke.assert_not_called();secrets.assert_not_called()

    def test_debug_flag_alone_cannot_start_live_cli_or_load_secrets(self):
        from tools import run_live_acceptance as cli
        with patch('security.Settings.from_secrets') as config,patch('ai_analysis.invoke') as call:
            with self.assertRaises(AcceptanceError):cli.main(['--debug-rejected-samples'])
        config.assert_not_called();call.assert_not_called()


class DebugStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'project';self.root.mkdir()
        shutil.copytree(ROOT/'acceptance_samples',self.root/'acceptance_samples')
        change_root = patch.object(sample_debug,'ROOT',self.root);change_root.start();self.addCleanup(change_root.stop)
        self.record,self.cases = reproduction_cases()
        self.payload = self.cases[0][1]
        self.raw = json.dumps(self.payload,ensure_ascii=False,indent=2)
        self.directory = self.root/'.autolex_runtime'/'rejected_sample_debug'

    def save(self, **kwargs):
        return capture_rejected_output(self.record,self.raw,enabled=True,**kwargs)

    def test_disabled_capture_never_inspects_record_or_creates_directory(self):
        with patch('sample_debug.fixture_id') as identity:
            self.assertEqual(capture_rejected_output({},'ignored')['status'],'disabled')
            self.assertEqual(capture_rejected_output({},'ignored',enabled='true')['status'],'disabled')
        identity.assert_not_called();self.assertFalse(self.directory.exists())

    def test_capture_exact_raw_string_permissions_and_invalid_analysis_envelope(self):
        capture = self.save()
        self.assertEqual(capture['status'],'saved')
        artifact = read_capture(capture['artifact_id'])
        self.assertEqual(artifact['raw_output'],self.raw)
        self.assertEqual(artifact['execution_mode'],'manual_offline')
        self.assertEqual(artifact['purpose'],'rejected_debug_not_valid_analysis')
        self.assertTrue(artifact['schema_valid']);self.assertFalse(artifact['evidence_binding_valid'])
        self.assertNotIn('sections',artifact)
        for directory in (self.directory,self.directory.parent):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode),0o700)
        self.assertEqual(stat.S_IMODE((self.directory/(capture['artifact_id']+'.json')).stat().st_mode),0o600)
        self.assertEqual(len(artifact['prompt_sha256']),64)

    def test_both_fixed_simulated_fixtures_can_capture_rejected_classification(self):
        for scenario in ('SIM_A','SIM_B'):
            record = fixed_record(scenario)
            payload = empty_analysis(record)
            quote = record['units'][3]['text']
            payload['facts']=[{'kind':'事实','text':quote,'reasoning':'','sources':[{'source_id':'S004','quote':quote}]}]
            result = capture_rejected_output(record,json.dumps(payload,ensure_ascii=False),enabled=True)
            self.assertEqual(result['status'],'saved')
            self.assertEqual(result['fixture_id'],scenario)

    def test_record_with_simulation_name_but_wrong_hash_is_refused(self):
        record = deepcopy(self.record);record['文件SHA256']='a'*64
        self.assertEqual(capture_rejected_output(record,self.raw,enabled=True)['status'],'refused_non_fixture')
        self.assertFalse(self.directory.exists())

    def test_copied_hash_with_changed_text_is_refused(self):
        record = deepcopy(self.record);record['units'][1]['text']='模拟标识不能使任意材料通过'
        self.assertEqual(capture_rejected_output(record,self.raw,enabled=True)['status'],'refused_non_fixture')
        self.assertFalse(self.directory.exists())

    def test_fixed_hash_does_not_trust_changed_local_fixture_or_manifest(self):
        name = sample_debug.FIXTURES['SIM_B'][0]
        (self.root/'acceptance_samples'/name).write_bytes(b'not-a-fixed-fixture')
        (self.root/'acceptance_samples'/'manifest.json').write_text('{}')
        self.assertEqual(self.save()['status'],'capture_failed')
        self.assertFalse(self.directory.exists())

    def test_schema_failure_is_not_captured(self):
        result = capture_rejected_output(self.record,'{"wrong":"schema"}',enabled=True)
        self.assertEqual(result['status'],'refused_schema')
        self.assertFalse(self.directory.exists())

    def test_valid_analysis_is_not_captured(self):
        raw = json.dumps(self.cases[3][1],ensure_ascii=False)
        self.assertEqual(capture_rejected_output(self.record,raw,enabled=True)['status'],'refused_valid_analysis')
        self.assertFalse(self.directory.exists())

    def test_foreign_context_is_not_captured(self):
        payload = deepcopy(self.payload);payload['document_sha256']='a'*64
        result = capture_rejected_output(self.record,json.dumps(payload,ensure_ascii=False),enabled=True)
        self.assertEqual(result['status'],'refused_context')
        self.assertFalse(self.directory.exists())

    def test_arbitrary_non_fixture_quote_cannot_be_written_under_sample_identity(self):
        payload = deepcopy(self.payload)
        payload['facts'][5]['text']='任意材料文字禁止落盘'
        result = capture_rejected_output(self.record,json.dumps(payload,ensure_ascii=False),enabled=True)
        self.assertEqual(result['status'],'refused_non_fixture_text')
        self.assertFalse(self.directory.exists())

    def test_secret_pattern_and_in_memory_forbidden_values_are_never_written(self):
        for text, blocked in [('API_KEY',()),('密码',()),('offline_sensitive_value',('offline_sensitive_value',))]:
            with self.subTest(text=text):
                payload = deepcopy(self.payload);payload['facts'][5]['reasoning']=text
                result = capture_rejected_output(self.record,json.dumps(payload,ensure_ascii=False),enabled=True,forbidden_values=blocked)
                self.assertEqual(result['status'],'refused_sensitive_output')
                self.assertNotIn(text,json.dumps(result))
        self.assertFalse(self.directory.exists())

    def test_symlink_runtime_directory_cannot_redirect_writes_or_change_target_permissions(self):
        external = Path(self.tmp.name)/'external';external.mkdir(mode=0o755)
        before = external.stat().st_mode
        (self.root/'.autolex_runtime').symlink_to(external,target_is_directory=True)
        self.assertEqual(self.save()['status'],'capture_failed')
        self.assertEqual(list(external.iterdir()),[])
        self.assertEqual(external.stat().st_mode,before)

    def test_json_unicode_escaping_cannot_hide_sensitive_values(self):
        for value in ('API_KEY','offline_sensitive_value'):
            payload = deepcopy(self.payload);payload['facts'][5]['reasoning']=value
            escaped = json.dumps(payload,ensure_ascii=False).replace(value,''.join('\\u%04x'%ord(char) for char in value))
            result = capture_rejected_output(self.record,escaped,enabled=True,forbidden_values=('offline_sensitive_value',))
            self.assertEqual(result['status'],'refused_sensitive_output')
        self.assertFalse(self.directory.exists())

    def test_symlink_debug_directory_is_refused(self):
        external = Path(self.tmp.name)/'external';external.mkdir()
        self.directory.parent.mkdir()
        self.directory.symlink_to(external,target_is_directory=True)
        self.assertEqual(self.save()['status'],'capture_failed')
        self.assertEqual(list(external.iterdir()),[])

    def test_capture_storage_errors_are_safe_and_not_logged(self):
        with patch('sample_debug._private_directory',side_effect=OSError('PRIVATE_PATH_DO_NOT_PRINT')):
            with patch('sys.stdout',new_callable=io.StringIO) as output,patch('sys.stderr',new_callable=io.StringIO) as error:
                result = self.save()
        self.assertEqual(result,{'status':'capture_failed'})
        self.assertEqual(output.getvalue()+error.getvalue(),'')

    def test_non_posix_storage_fails_closed(self):
        with patch('sample_debug.os.name','nt'):
            self.assertEqual(self.save()['status'],'capture_failed')
        self.assertFalse(self.directory.exists())

    def test_size_and_file_count_bounds(self):
        self.assertEqual(capture_rejected_output(self.record,'x'*(sample_debug.MAX_BYTES+1),enabled=True)['status'],'refused_output')
        self.directory.mkdir(parents=True)
        for i in range(100):(self.directory/f'{i}.json').write_text('test')
        self.assertEqual(self.save()['status'],'storage_limit_reached')

    def test_artifact_path_traversal_and_symlinks_are_rejected(self):
        for value in ('../secrets.toml','/tmp/private','A'*32):
            with self.subTest(value=value),self.assertRaises(ValueError):read_capture(value)
        self.directory.mkdir(parents=True)
        target = Path(self.tmp.name)/'private';target.write_text('PRIVATE_DO_NOT_READ')
        (self.directory/('a'*32+'.json')).symlink_to(target)
        with self.assertRaises(ValueError):read_capture('a'*32)

    def test_replay_reports_offline_diagnostic_without_printing_saved_text(self):
        capture = self.save()
        result = replay_artifact(capture['artifact_id'])
        self.assertEqual(result['actual_live_attempts'],0)
        self.assertEqual(result['execution_mode'],'offline_artifact_replay')
        self.assertFalse(result['binding_valid'])
        self.assertEqual(result['validation_diagnostic']['item_index'],5)
        self.assertNotIn('raw_output',result)
        self.assertNotIn('仅列出检查摘要',json.dumps(result,ensure_ascii=False))

    def test_nonregular_artifact_is_rejected_without_blocking_on_fifo(self):
        self.directory.mkdir(parents=True)
        os.mkfifo(self.directory/('b'*32+'.json'),mode=0o600)
        with self.assertRaises(ValueError):read_capture('b'*32)

    def settings(self):
        return Settings(api_key='offline-key-not-real',password_hash=HASH,mode='local',single_instance=True,provider='deepseek')

    def analyze(self, payload=None, *, debug=False):
        payload = self.payload if payload is None else payload
        response = {'provider_status':'completed','refused':False,'call_status':'response_received',
                    'output_text':json.dumps(payload,ensure_ascii=False),'token_usage':None}
        settings = self.settings();store = Mock()
        with patch('ai_analysis.invoke',return_value=response):
            try:
                return analyze_record(self.record,settings,store,settings.principal,True,Mock(),debug_rejected_samples=debug)
            finally:store.release.assert_called_once()

    def test_default_analysis_does_not_capture_rejected_output(self):
        with self.assertRaises(AIError) as caught:self.analyze()
        self.assertEqual(caught.exception.code,'output_validation_failed')
        self.assertNotIn('debug_capture',caught.exception.receipt)
        self.assertFalse(self.directory.exists())

    def test_enabled_capture_keeps_analysis_rejected_and_receipt_contains_only_identifier(self):
        with self.assertRaises(AIError) as caught:self.analyze(debug=True)
        receipt = caught.exception.receipt
        self.assertEqual(caught.exception.code,'output_validation_failed')
        self.assertEqual(receipt['validation_status'],'failed')
        self.assertEqual(receipt['validation_error_kind'],'evidence_binding')
        self.assertEqual(receipt['debug_capture']['status'],'saved')
        self.assertEqual(receipt['debug_capture']['execution_mode'],'injected_test_client')
        self.assertNotIn('仅列出检查摘要',json.dumps(receipt,ensure_ascii=False))
        self.assertNotIn(self.settings().api_key,json.dumps(read_capture(receipt['debug_capture']['artifact_id'])))

    def test_enabled_capture_not_used_for_schema_failure_or_success(self):
        with self.assertRaises(AIError) as caught:self.analyze({'wrong':'schema'},debug=True)
        self.assertEqual(caught.exception.receipt['validation_error_kind'],'schema')
        self.assertNotIn('debug_capture',caught.exception.receipt)
        result = self.analyze(self.cases[3][1],debug=True)
        self.assertEqual(result['call_receipt']['validation_status'],'passed')
        self.assertNotIn('debug_capture',result['call_receipt'])
        self.assertFalse(self.directory.exists())

    def test_enabled_capture_refuses_non_fixture_analysis_without_returning_valid_result(self):
        self.record = deepcopy(self.record);self.record['units'][0]['text']='模拟名称不能代替固定材料身份'
        # 对应上下文变化后先通过Schema，随后仍由原绑定校验拒绝。
        payload = deepcopy(self.payload)
        with self.assertRaises(AIError) as caught:self.analyze(payload,debug=True)
        self.assertEqual(caught.exception.receipt['debug_capture']['status'],'refused_non_fixture')
        self.assertEqual(caught.exception.code,'output_validation_failed')
        self.assertFalse(self.directory.exists())

    def test_live_suite_threads_debug_option_only_when_explicitly_enabled(self):
        settings = self.settings()
        from security import QuotaStore
        store = QuotaStore(self.root/'quota.sqlite3')
        error = AIError('模拟失败',code='authentication_failed',receipt={'execution_mode':'injected_test_client'})
        executor = Mock(side_effect=error)
        run_suite(settings,store,settings.principal,self.root/'reports',confirm_paid=True,executor=executor,debug_rejected_samples=True)
        self.assertIs(executor.call_args.kwargs['debug_rejected_samples'],True)

    def test_zip_and_git_ignore_exclude_raw_debug_artifacts(self):
        from project_archive import build_project_zip
        from zipfile import ZipFile
        import subprocess
        capture = self.save()
        with ZipFile(io.BytesIO(build_project_zip(self.root))) as archive:
            self.assertFalse(any('rejected_sample_debug' in name for name in archive.namelist()))
        path = '.autolex_runtime/rejected_sample_debug/'+capture['artifact_id']+'.json'
        self.assertEqual(subprocess.run(['git','check-ignore','-q',path],cwd=ROOT).returncode,0)
