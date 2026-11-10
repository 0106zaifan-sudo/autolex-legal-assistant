"""新版默认入口AppTest，固定虚构B01、本地注入、临时额度库。"""
import json,sys
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from ui_isolation import IsolatedUITestCase
import test_v2e_integration as fixtures
from security import QuotaStore

class V2EUI(IsolatedUITestCase):
 def setUp(self):
  super().setUp();main=sys.modules['__main__'];self.addCleanup(sys.modules.__setitem__,'__main__',main)
  self.f=fixtures.V2E();self.f.setUp();self.addCleanup(self.f.tmp.cleanup)
 def app(self):
  f=self.f
  app=AppTest.from_string("import streamlit as st\nfrom multidoc_ui import render_multidoc_ai\nrender_multidoc_ai(st.session_state['store'],st.session_state['cid'],st.session_state['settings'],st.session_state['principal'])",default_timeout=30)
  for k,v in {'store':f.store,'cid':f.cid,'settings':f.settings,'principal':f.settings.principal}.items():app.session_state[k]=v
  # 保留1.2历史入口回归；新的默认1.3由独立AppTest覆盖。
  app.session_state['md_protocol']='1.2'
  app.run();app.multiselect(key='md_select_'+f.cid).set_value(list(f.ids.values())).run()
  return app
 def authorize(self,app):
  f=self.f
  for did in f.batch['required_ack']:app.checkbox(key='md_ack_'+f.batch['batch_sha256']+'_'+did).check()
  app.checkbox(key='md_consent').check().run()
 def test_default_new_protocol_and_coverage_authorization_required(self):
  app=self.app();self.assertFalse(app.exception);self.assertEqual(app.selectbox(key='md_protocol').value,'1.2')
  self.assertTrue(app.button(key='run_multidoc_ai').disabled)
  app.checkbox(key='md_consent').check().run();self.assertTrue(app.button(key='run_multidoc_ai').disabled)
  self.authorize(app);self.assertFalse(app.button(key='run_multidoc_ai').disabled)
 def test_success_waits_for_explicit_import_and_shows_safe_receipt(self):
  f=self.f;app=self.app();self.authorize(app)
  response={'provider_status':'completed','call_status':'response_received','provider_model':'offline-mock',
            'token_usage':{'total_tokens':120},'output_text':json.dumps(f.payload(),ensure_ascii=False)}
  with patch('multidoc_ai.invoke',return_value=response) as invoke,patch('multidoc_ui.QuotaStore',return_value=f.quota):
   app.button(key='run_multidoc_ai').click().run();invoke.assert_called_once()
  self.assertFalse(app.exception);self.assertFalse(f.store.get_case(f.cid).inferences)
  self.assertFalse(app.checkbox(key='md_consent').value)
  self.assertEqual(app.session_state['_md_result']['receipt']['schema_version'],'multidoc-analysis/1.2')
  self.assertFalse(app.button(key='import_multidoc_ai').disabled)
  app.button(key='import_multidoc_ai').click().run();self.assertFalse(app.exception)
  self.assertTrue(f.store.get_case(f.cid).inferences)
 def test_failure_safe_diagnostic_and_import_disabled(self):
  f=self.f;app=self.app();self.authorize(app);p=f.payload();p['pending_evidence'][0]['evidence_ids'][1]='PE_'+'f'*24
  response={'provider_status':'completed','call_status':'response_received','token_usage':{'total_tokens':120},'output_text':json.dumps(p,ensure_ascii=False)}
  with patch('multidoc_ai.invoke',return_value=response),patch('multidoc_ui.QuotaStore',return_value=f.quota):app.button(key='run_multidoc_ai').click().run()
  self.assertFalse(app.exception);self.assertTrue(app.button(key='import_multidoc_ai').disabled)
  self.assertTrue(any('pending_candidate_not_in_catalog' in x.value for x in app.json))
  self.assertFalse(f.store.get_case(f.cid).inferences)
 def test_changing_protocol_consumes_consent_and_clears_result(self):
  app=self.app();self.authorize(app);app.selectbox(key='md_protocol').select('1.1').run()
  self.assertFalse(app.checkbox(key='md_consent').value);self.assertTrue(app.button(key='run_multidoc_ai').disabled)
