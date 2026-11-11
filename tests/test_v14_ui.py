"""1.4 AppTest，仅人工B01响应与临时额度，不读Secrets。"""
import json,sys
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from ui_isolation import IsolatedUITestCase
import test_v14_aliases as fixtures

class AliasUI(IsolatedUITestCase):
 def setUp(self):
  super().setUp();main=sys.modules['__main__'];self.addCleanup(sys.modules.__setitem__,'__main__',main)
  self.h=fixtures.Alias14();self.h.setUp();self.addCleanup(self.h.doCleanups);self.f=self.h.f
 def app(self):
  f=self.f
  app=AppTest.from_string("import streamlit as st\nfrom multidoc_ui import render_multidoc_ai\nrender_multidoc_ai(st.session_state['store'],st.session_state['cid'],st.session_state['settings'],st.session_state['principal'])",default_timeout=30)
  for k,v in {'store':f.store,'cid':f.cid,'settings':f.settings,'principal':f.settings.principal}.items():app.session_state[k]=v
  app.run();app.multiselect(key='md_select_'+f.cid).set_value(list(f.ids.values())).run();return app
 def authorize(self,app):
  for did in self.f.batch['required_ack']:app.checkbox(key='md_ack_'+self.f.batch['batch_sha256']+'_'+did).check()
  app.checkbox(key='md_consent').check().run()
 def test_new_default_and_protocol_change_require_consent(self):
  app=self.app();self.assertEqual(app.selectbox(key='md_protocol').value,'1.4');self.assertTrue(app.button(key='run_multidoc_ai').disabled)
  self.authorize(app);self.assertFalse(app.button(key='run_multidoc_ai').disabled)
  app.selectbox(key='md_protocol').select('1.3').run();self.assertFalse(app.checkbox(key='md_consent').value)
  self.assertTrue(app.button(key='run_multidoc_ai').disabled)
 def test_alias_success_explicit_import_and_safe_audit(self):
  app=self.app();self.authorize(app);p=self.h.payload()
  response={'provider_status':'completed','call_status':'response_received','provider_model':'offline14','token_usage':{'total_tokens':120},'output_text':json.dumps(p,ensure_ascii=False)}
  with patch('multidoc_ai.invoke',return_value=response) as call,patch('multidoc_ui.QuotaStore',return_value=self.f.quota):app.button(key='run_multidoc_ai').click().run()
  call.assert_called_once();self.assertFalse(app.exception);self.assertFalse(self.f.store.get_case(self.f.cid).inferences)
  r=app.session_state['_md_result'];self.assertEqual(r['raw_output'],p);self.assertEqual(r['receipt']['pending_alias_version'],'pending-alias-map/1')
  app.button(key='import_multidoc_ai').click().run();self.assertFalse(app.exception);self.assertTrue(self.f.store.get_case(self.f.cid).inferences)
 def test_typo_diagnostic_shows_exact_unknown_no_auto_import(self):
  app=self.app();self.authorize(app);p=self.h.payload();bad=self.h.bad_alias();p['pending_evidence'][0]['evidence_aliases'][1]=bad
  response={'provider_status':'completed','call_status':'response_received','token_usage':{'total_tokens':120},'output_text':json.dumps(p,ensure_ascii=False)}
  with patch('multidoc_ai.invoke',return_value=response),patch('multidoc_ui.QuotaStore',return_value=self.f.quota):app.button(key='run_multidoc_ai').click().run()
  self.assertFalse(app.exception);self.assertTrue(app.button(key='import_multidoc_ai').disabled)
  d=app.session_state['_md_receipt']['validation_diagnostic'];self.assertEqual(d['unknown_aliases'],[bad])
  self.assertEqual(d['selected_aliases'],p['pending_evidence'][0]['evidence_aliases'])
