"""默认1.3与旧入口切换，本地B01响应注入，不读取Secrets。"""
import json,sys
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from ui_isolation import IsolatedUITestCase
import test_v13_catalog_ownership as fixtures

class Protocol13UI(IsolatedUITestCase):
 def setUp(self):
  super().setUp();main=sys.modules['__main__'];self.addCleanup(sys.modules.__setitem__,'__main__',main)
  self.helper=fixtures.ProgramOwnedCatalog();self.helper.setUp();self.addCleanup(self.helper.doCleanups);self.f=self.helper.f
 def app(self):
  f=self.f
  app=AppTest.from_string("import streamlit as st\nfrom multidoc_ui import render_multidoc_ai\nrender_multidoc_ai(st.session_state['store'],st.session_state['cid'],st.session_state['settings'],st.session_state['principal'])",default_timeout=30)
  for key,value in {'store':f.store,'cid':f.cid,'settings':f.settings,'principal':f.settings.principal}.items():app.session_state[key]=value
  app.run();app.multiselect(key='md_select_'+f.cid).set_value(list(f.ids.values())).run();return app
 def authorize(self,app):
  for did in self.f.batch['required_ack']:app.checkbox(key='md_ack_'+self.f.batch['batch_sha256']+'_'+did).check()
  app.checkbox(key='md_consent').check().run()
 def test_default13_and_switch_to12_requires_new_authorization(self):
  app=self.app();self.assertEqual(app.selectbox(key='md_protocol').value,'1.3');self.assertTrue(app.button(key='run_multidoc_ai').disabled)
  self.authorize(app);self.assertFalse(app.button(key='run_multidoc_ai').disabled)
  app.selectbox(key='md_protocol').select('1.2').run();self.assertFalse(app.checkbox(key='md_consent').value)
  self.assertTrue(app.button(key='run_multidoc_ai').disabled)
 def test_success_without_model_hash_is_not_automatically_imported(self):
  app=self.app();self.authorize(app);p=self.helper.payload();f=self.f
  response={'provider_status':'completed','call_status':'response_received','provider_model':'offline13',
   'token_usage':{'total_tokens':120},'output_text':json.dumps(p,ensure_ascii=False)}
  with patch('multidoc_ai.invoke',return_value=response) as call,patch('multidoc_ui.QuotaStore',return_value=f.quota):app.button(key='run_multidoc_ai').click().run()
  call.assert_called_once();self.assertFalse(app.exception);self.assertFalse(f.store.get_case(f.cid).inferences)
  result=app.session_state['_md_result'];self.assertEqual(result['raw_output'],p)
  self.assertEqual(result['receipt']['pending_catalog_sha256'],f.batch['pending_catalog']['sha256'])
  app.button(key='import_multidoc_ai').click().run();self.assertFalse(app.exception);self.assertTrue(f.store.get_case(f.cid).inferences)
 def test_bad_candidate_still_refuses_import_with_safe_receipt(self):
  app=self.app();self.authorize(app);p=self.helper.payload();p['pending_evidence'][0]['evidence_ids'][1]='PE_'+'f'*24
  response={'provider_status':'completed','call_status':'response_received','token_usage':{'total_tokens':120},'output_text':json.dumps(p,ensure_ascii=False)}
  with patch('multidoc_ai.invoke',return_value=response),patch('multidoc_ui.QuotaStore',return_value=self.f.quota):app.button(key='run_multidoc_ai').click().run()
  self.assertFalse(app.exception);self.assertTrue(app.button(key='import_multidoc_ai').disabled)
  self.assertTrue(any('pending_candidate_not_in_catalog' in x.value for x in app.json));self.assertFalse(self.f.store.get_case(self.f.cid).inferences)
