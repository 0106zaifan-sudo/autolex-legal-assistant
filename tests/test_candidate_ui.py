"""AppTest实际走新候选协议、本地注入返回；禁止外部调用和磁盘Secrets。"""
import json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
from ui_isolation import IsolatedUITestCase
import test_multidoc_ui as fixtures
from multidoc_ai import prepare_case
from timeline_candidates import build_event_catalog
from security import QuotaStore

class CandidateUI(IsolatedUITestCase):
    def test_ui_uses_candidate_request_and_explicit_import(self):
        main=sys.modules['__main__'];self.addCleanup(sys.modules.__setitem__,'__main__',main)
        app,store,cid,ids=fixtures.JointUI().app()
        settings=app.session_state['settings'];batch=prepare_case(store,cid,ids[:2],settings)
        catalog=build_event_catalog(batch)
        payload={'schema_version':'multidoc-analysis/1.1','prompt_version':'multidoc/candidates-v1','case_id':cid,
                 'batch_sha256':batch['batch_sha256'],'facts':[],'pending_evidence':[],'relations':[],
                 'timeline':[{'candidate_id':c['candidate_id'],'kind':'事实'} for c in catalog['candidates']]}
        response={'provider_status':'completed','call_status':'response_received','refused':False,
                  'token_usage':{'total_tokens':250},'output_text':json.dumps(payload,ensure_ascii=False)}
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        quota=QuotaStore(Path(tmp.name)/'mock.sqlite3')
        # 仅替换此已禁止外部调用的入口；实际执行新Schema解析、恢复和完整验证。
        with patch('multidoc_ai.invoke',return_value=response) as invoke,patch('multidoc_ui.QuotaStore',return_value=quota):
            app.checkbox(key='md_consent').check().run();app.button(key='run_multidoc_ai').click().run()
            invoke.assert_called_once()
            request=invoke.call_args.args[1]
            self.assertIn('event_catalog',json.loads(request['input']))
            self.assertEqual(request['text']['format']['name'],'CandidateAnalysis')
        self.assertFalse(app.exception)
        self.assertFalse(store.get_case(cid).timeline)
        self.assertEqual(app.session_state['_md_result']['receipt']['schema_version'],'multidoc-analysis/1.1')
        app.button(key='import_multidoc_ai').click().run()
        self.assertFalse(app.exception);self.assertEqual(len(store.get_case(cid).timeline),2)
