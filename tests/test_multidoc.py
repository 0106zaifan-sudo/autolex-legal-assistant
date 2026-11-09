import unittest,json
from case_store import CaseStore,CaseError
from test_case_store import document

class MultiDocTests(unittest.TestCase):
 def setUp(self):
  self.s=CaseStore();self.c=self.s.create_case('模拟多材料')
 def add(self,text,name='模拟材料.docx',case=None):
  c=case or self.c;d=self.s.attach_document(c,name,document(text,title=name));return self.s.add_evidence(c,d,0,0,len(text),text)
 def pair(self,a,b):return self.s.link_evidence(self.c,a,b)
 def test_emit_receive_not_conflict(self):
  a=self.add('事件编号：SIM-1；驾驶人未收到接管提示。');b=self.add('事件编号：SIM-1；系统已发出接管提示。','模拟企业.docx')
  r=self.pair(a,b);self.assertEqual(r.relation_type,'related');self.assertEqual(r.status,'candidate')
 def test_closed_opposition_candidate(self):
  a=self.add('事件编号：SIM-1；系统未发出接管提示。');b=self.add('事件编号：SIM-1；系统已发出接管提示。','模拟企业.docx')
  self.assertEqual(self.pair(a,b).relation_type,'inconsistency_candidate')
 def test_support_only_with_event_and_predicate(self):
  a=self.add('事件编号：SIM-1；系统已发出接管提示。');b=self.add('事件编号：SIM-1；系统已发出接管提示。','模拟电子.docx')
  self.assertNotEqual(a,b);self.assertEqual(self.pair(a,b).relation_type,'support_candidate')
 def test_missing_event_identifier_uncertain(self):
  a=self.add('系统已发出接管提示。');b=self.add('系统已发出接管提示。','模拟企业.docx');self.assertEqual(self.pair(a,b).relation_type,'needs_verification')
 def test_time_difference(self):
  a=self.add('事件编号：SIM-1；2026年11月1日08:30车辆发生碰撞。');b=self.add('事件编号：SIM-1；2026年11月1日08:31车辆发生碰撞。','模拟电子.docx')
  self.assertEqual(self.pair(a,b).relation_type,'inconsistency_candidate')
 def test_precision_difference(self):
  a=self.add('事件编号：SIM-1；2026年11月1日车辆发生碰撞。');b=self.add('事件编号：SIM-1；2026年11月1日08:30车辆发生碰撞。','模拟电子.docx')
  self.assertEqual(self.pair(a,b).relation_type,'needs_verification')
 def test_cross_case_rejected(self):
  a=self.add('接管提示。');c=self.s.create_case('另一模拟案件');b=self.add('接管提示。',case=c)
  with self.assertRaises(CaseError):self.pair(a,b)
 def test_same_document_rejected(self):
  a=self.add('接管提示。')
  with self.assertRaises(CaseError):self.pair(a,a)
 def test_duplicate_reverse_idempotent(self):
  a=self.add('接管提示。');b=self.add('接管提示。','模拟电子.docx');r=self.pair(a,b)
  self.assertEqual(r.relation_id,self.pair(b,a).relation_id);self.assertEqual(len(self.s.get_case(self.c).relations),1)
 def test_reviews_append_not_overwrite(self):
  a=self.add('接管提示。');b=self.add('接管提示。','模拟电子.docx');r=self.pair(a,b)
  self.s.review_relation(self.c,r.relation_id,'confirmed','related','模拟复核人','仅确认主题关联')
  self.s.review_relation(self.c,r.relation_id,'rejected','needs_verification','模拟复核人','来源仍不明确')
  case=self.s.get_case(self.c);self.assertEqual(len(case.relation_reviews),2);self.assertEqual(case.relations[0].status,'candidate');self.assertFalse(case.reviews)
 def test_empty_reviewer_rejected(self):
  a=self.add('接管提示。');b=self.add('接管提示。','模拟电子.docx');r=self.pair(a,b)
  with self.assertRaises(CaseError):self.s.review_relation(self.c,r.relation_id,'confirmed','related','','原因')
 def test_tampered_anchor_rejected(self):
  a=self.add('接管提示。');b=self.add('接管提示。','模拟电子.docx');self.s._cases[self.c].evidence[a].start=1
  with self.assertRaises(ValueError):self.pair(a,b)
 def test_export_no_binary(self):
  a=self.add('接管提示。');b=self.add('接管提示。','模拟电子.docx');self.pair(a,b)
  data=json.loads(self.s.export_json(self.c));self.assertEqual(data['schema_version'],'1.1');self.assertEqual(len(data['relations']),1)
  self.assertTrue(all('original_bytes' not in d for d in data['documents'].values()))
 def test_discovery_idempotent(self):
  self.add('接管提示。');self.add('接管提示。','模拟电子.docx');self.s.discover_relations(self.c);self.s.discover_relations(self.c)
  self.assertEqual(len(self.s.get_case(self.c).relations),1)
 def test_different_event_ids_not_associated(self):
  from evidence_relations import compare_quotes
  self.assertIsNone(compare_quotes('事件编号：A；系统已发出接管提示。','事件编号：B；系统未发出接管提示。'))
 def test_keyword_only_is_not_support(self):
  a=self.add('事件编号：A；接管提示需要检查。');b=self.add('事件编号：A；接管提示资料。','模拟乙.docx')
  self.assertEqual(self.pair(a,b).relation_type,'related')
 def test_missing_data_never_means_nonexistence(self):
  a=self.add('事件编号：A；原始日志未提供。');b=self.add('事件编号：A；原始日志摘要。','模拟乙.docx')
  self.assertEqual(self.pair(a,b).relation_type,'needs_verification')
 def test_identical_bytes_renamed_are_not_independent(self):
  raw=document('接管提示。');a=self.s.attach_document(self.c,'模拟甲.docx',raw);b=self.s.attach_document(self.c,'模拟乙.docx',raw)
  x=self.s.add_evidence(self.c,a,0,0,5,'接管提示。');y=self.s.add_evidence(self.c,b,0,0,5,'接管提示。')
  with self.assertRaises(CaseError):self.pair(x,y)
 def test_legacy_upgrade_explicit_and_no_confirmations(self):
  from case_schema import upgrade_case_payload
  old=json.loads(self.s.export_json(self.c));old['schema_version']='1.0';old.pop('relations');old.pop('relation_reviews')
  new=upgrade_case_payload(old);self.assertEqual(old['schema_version'],'1.0');self.assertEqual(new['schema_version'],'1.1');self.assertFalse(new['relation_reviews']);self.assertEqual(new['facts'],old['facts'])
 def test_upgrade_cannot_smuggle_reviewed_relations(self):
  from case_schema import upgrade_case_payload
  with self.assertRaises(ValueError):upgrade_case_payload({'schema_version':'1.0','relations':[{'status':'confirmed'}]})
 def test_review_wrong_case_denied(self):
  a=self.add('接管提示。');b=self.add('接管提示。','模拟乙.docx');r=self.pair(a,b);other=self.s.create_case('模拟另一案')
  with self.assertRaises(CaseError):self.s.review_relation(other,r.relation_id,'confirmed','related','模拟复核人','理由')
 def test_review_chain_preserves_original_type(self):
  a=self.add('接管提示。');b=self.add('接管提示。','模拟乙.docx');r=self.pair(a,b)
  for typ in ('related','needs_verification'):self.s.review_relation(self.c,r.relation_id,'modified',typ,'模拟复核人','新的审阅依据')
  reviews=self.s.get_case(self.c).relation_reviews;self.assertEqual(reviews[1].previous_review_id,reviews[0].review_id)
  self.assertEqual(self.s.get_case(self.c).relations[0],r)
 def test_original_file_or_snapshot_change_rejected(self):
  a=self.add('接管提示。');b=self.add('接管提示。','模拟乙.docx');did=self.s._cases[self.c].evidence[a].document_id
  self.s._cases[self.c].documents[did].units[0]['text']='不同文本'
  with self.assertRaises(ValueError):self.pair(a,b)
 def test_four_public_samples_trace_back_to_files(self):
  from pathlib import Path
  import hashlib
  root=Path(__file__).resolve().parents[1]/'samples_multidoc'
  for path in sorted(root.iterdir()):
   did=self.s.attach_document(self.c,path.name,path.read_bytes());doc=self.s.get_case(self.c).documents[did]
   self.assertEqual(doc.file_sha256,hashlib.sha256(path.read_bytes()).hexdigest())
   unit=next((i,u) for i,u in enumerate(doc.units) if '事件编号' in u['text']);i,u=unit
   quote=u['text'][u['text'].index('事件编号'):].split('原始日志')[0].strip()
   self.s.add_evidence(self.c,did,i,u['text'].index(quote),u['text'].index(quote)+len(quote),quote)
  self.s.discover_relations(self.c);case=self.s.get_case(self.c)
  self.assertEqual(len(case.documents),4);self.assertTrue(case.relations)
  for r in case.relations:
   self.assertNotEqual(case.evidence[r.left_id].document_id,case.evidence[r.right_id].document_id)

class AmbiguousRelationTests(unittest.TestCase):
 def test_nested_negation_is_not_positive_support(self):
  from evidence_relations import compare_quotes
  self.assertEqual(compare_quotes('事件编号：A；并非系统已发出接管提示。','事件编号：A；系统已发出接管提示。')[0],'needs_verification')
 def test_quoted_statement_not_resolved_as_truth(self):
  from evidence_relations import compare_quotes
  self.assertEqual(compare_quotes('事件编号：A；引述：系统未发出接管提示。','事件编号：A；系统已发出接管提示。')[0],'needs_verification')

class RelationUITests(unittest.TestCase):
 def test_side_by_side_and_append_review(self):
  from ui_isolation import isolated_ui_runtime
  from streamlit.testing.v1 import AppTest
  s=CaseStore();c=s.create_case('模拟UI')
  for name,text in [('模拟甲.docx','事件编号：A；驾驶人未收到接管提示。'),('模拟乙.docx','事件编号：A；系统已发出接管提示。')]:
   d=s.attach_document(c,name,document(text,title=name));s.add_evidence(c,d,0,0,len(text),text)
  with isolated_ui_runtime():
   app=AppTest.from_string("import streamlit as st\nfrom relation_ui import render_relations\nrender_relations(st.session_state['store'],st.session_state['cid'])",default_timeout=30)
   app.session_state['store']=s;app.session_state['cid']=c;app.run();app.button(key='discover_relations').click().run()
   self.assertFalse(app.exception);self.assertEqual(len(app.code),2)
   app.text_input(key='relation_reviewer').set_value('模拟审阅人');app.text_area(key='relation_reason').set_value('仅为主题关联，未核实真实性')
   app.selectbox(key='relation_status').set_value('confirmed');app.selectbox(key='relation_type').set_value('related')
   app.button(key='save_relation_review').click().run();self.assertFalse(app.exception)
   self.assertEqual(len(s.get_case(c).relation_reviews),1);self.assertFalse(s.get_case(c).facts)
