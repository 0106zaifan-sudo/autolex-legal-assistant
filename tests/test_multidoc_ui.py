from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from ui_isolation import IsolatedUITestCase
from case_store import CaseStore
from security import Settings
from test_case_store import document

HASH='pbkdf2_sha256$200000$'+'ab'*16+'$'+'cd'*32

class JointUI(IsolatedUITestCase):
 def app(self):
  store=CaseStore();cid=store.create_case('模拟联合UI');ids=[]
  for i in range(3):ids.append(store.attach_document(cid,f'模拟UI{i}.docx',document(f'模拟记录{i}：车辆发生碰撞。',title=str(i))))
  app=AppTest.from_string("import streamlit as st\nfrom multidoc_ui import render_multidoc_ai\nrender_multidoc_ai(st.session_state['store'],st.session_state['cid'],st.session_state['settings'],st.session_state['principal'])",default_timeout=30)
  # 此夹具显式保留1.1历史入口；1.2默认入口由独立V2E AppTest覆盖。
  app.session_state['md_protocol']='1.1'
  app.session_state['store']=store;app.session_state['cid']=cid
  settings=Settings(api_key='offline-not-real',password_hash=HASH,mode='local',single_instance=True)
  app.session_state['settings']=settings;app.session_state['principal']=settings.principal
  app.run();app.multiselect(key='md_select_'+cid).set_value(ids[:2]).run()
  return app,store,cid,ids
 def test_selection_changes_reset_batch_consent(self):
  app,_,cid,ids=self.app();app.checkbox(key='md_consent').check().run()
  self.assertFalse(app.button(key='run_multidoc_ai').disabled)
  app.multiselect(key='md_select_'+cid).set_value(ids[1:]).run()
  self.assertFalse(app.checkbox(key='md_consent').value)
  self.assertTrue(app.button(key='run_multidoc_ai').disabled)
 def test_call_is_explicit_and_consent_is_consumed_even_on_failure(self):
  from multidoc_ai import MultiAIError
  app,_,cid,ids=self.app()
  with patch('multidoc_ui.analyze_case',side_effect=MultiAIError()) as analyze:
   app.run();analyze.assert_not_called()
   app.checkbox(key='md_consent').check().run();analyze.assert_not_called()
   # 不创建真实配额路径；额度行为由核心测试的真实临时SQLite验证。
   with patch('multidoc_ui.QuotaStore'):
    app.button(key='run_multidoc_ai').click().run()
   analyze.assert_called_once()
   self.assertFalse(app.exception);self.assertFalse(app.checkbox(key='md_consent').value)
   self.assertTrue(app.button(key='import_multidoc_ai').disabled)
 def test_partial_file_requires_its_own_acknowledgement(self):
  app,store,cid,ids=self.app()
  store._cases[cid].documents[ids[0]].parse_report['requires_acknowledgement']=True
  app.run();app.checkbox(key='md_consent').check().run()
  self.assertTrue(app.button(key='run_multidoc_ai').disabled)
  ack=next(c for c in app.checkbox if c.key.startswith('md_ack_'))
  ack.check().run();self.assertFalse(app.button(key='run_multidoc_ai').disabled)
 def test_relation_switch_never_reuses_previous_review_fields(self):
  store=CaseStore();cid=store.create_case('模拟复核隔离')
  for i in range(3):
   text=f'模拟记录{i}：车辆发生碰撞。';did=store.attach_document(cid,f'模拟复核{i}.docx',document(text,title=str(i)))
   store.add_evidence(cid,did,0,0,len(text),text)
  store.discover_relations(cid)
  app=AppTest.from_string("import streamlit as st\nfrom relation_ui import render_relations\nrender_relations(st.session_state['store'],st.session_state['cid'])",default_timeout=30)
  # 此夹具显式保留1.1历史入口；1.2默认入口由独立V2E AppTest覆盖。
  app.session_state['md_protocol']='1.1'
  app.session_state['store']=store;app.session_state['cid']=cid;app.run()
  app.text_input(key='relation_reviewer').set_value('模拟人员');app.text_area(key='relation_reason').set_value('前一个候选的理由');app.selectbox(key='relation_status').set_value('confirmed');app.run()
  ids=[r.relation_id for r in store.get_case(cid).relations]
  app.selectbox(key='relation_'+cid).set_value(ids[1]).run()
  self.assertFalse(app.exception);self.assertEqual(app.text_input(key='relation_reviewer').value,'')
  self.assertEqual(app.selectbox(key='relation_status').value,'needs_review')
