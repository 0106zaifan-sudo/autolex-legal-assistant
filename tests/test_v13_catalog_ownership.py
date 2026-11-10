"""1.3程序管理目录哈希；人工B01/官方SDK本地HTTP Mock，非真实响应复现。"""
from copy import deepcopy
from dataclasses import replace
import json,unittest,io,zipfile,hashlib
from unittest.mock import patch
import httpx
from openai import OpenAI
from case_store import CaseStore
from security import QuotaStore
from pathlib import Path
from pydantic import ValidationError
import multidoc_ai as old
import multidoc_v12 as v12
import test_v2e_integration as fixtures

class ProgramOwnedCatalog(unittest.TestCase):
 def setUp(self):
  import multidoc_v13 as m
  self.m=m;self.f=fixtures.V2E();self.f.setUp();self.addCleanup(self.f.tmp.cleanup)
  self.f.m=m;self.f.batch=m.prepare_case(self.f.store,self.f.cid,list(self.f.ids.values()),self.f.settings)
 def payload(self):
  # 构造发送前的人工1.3夹具；运行时代码不得补旧响应字段。
  p=self.f.payload();p.pop('pending_catalog_sha256');return p
 def run_ai(self,p=None):return self.f.run_ai(self.payload() if p is None else p)
 def reject(self,p,rule):
  f=self.f;before=f.store.export_json(f.cid)
  with self.assertRaises(old.MultiAIError) as caught:self.run_ai(p)
  receipt=caught.exception.receipt
  self.assertEqual(receipt['schema_version'],'multidoc-analysis/1.3')
  self.assertEqual(receipt['validation_diagnostic']['rule'],rule)
  self.assertEqual(receipt['token_usage']['total_tokens'],120)
  self.assertEqual(f.store.export_json(f.cid),before)
  return receipt
 def test_schema_does_not_have_output_catalog_hash(self):
  f=self.f;req,budget=self.m.request_for(f.batch,f.settings);schema=req['text']['format']['schema']
  self.assertNotIn('pending_catalog_sha256',schema['properties']);self.assertNotIn('pending_catalog_sha256',schema['required'])
  self.assertFalse(schema['additionalProperties'])
  self.assertEqual(set(schema['$defs']['PendingSelection']['properties']),{'anchor_id','evidence_ids','reasoning'})
 def test_single_request_four_sections_without_echo_hash(self):
  r=self.run_ai();self.assertEqual(r['schema_version'],'multidoc-analysis/1.3')
  for key in ('facts','timeline','relations','pending_evidence'):self.assertTrue(r[key])
  self.assertNotIn('pending_catalog_sha256',r['raw_output'])
  self.assertEqual(r['receipt']['pending_catalog_sha256'],self.f.batch['pending_catalog']['sha256'])
  self.assertEqual(r['pending_selection']['catalog_sha256'],self.f.batch['pending_catalog']['sha256'])
  self.assertFalse(self.f.store.get_case(self.f.cid).inferences)
 def test_legacy_12_missing_hash_still_rejected(self):
  f=self.f;p=self.payload();p.update(schema_version=v12.SCHEMA_VERSION,prompt_version=v12.PROMPT_VERSION)
  with self.assertRaises(ValidationError) as e:v12.Analysis12.model_validate(p)
  self.assertTrue(any(x['loc']==('pending_catalog_sha256',) and x['type']=='missing' for x in e.exception.errors(include_input=False)))
 def test_new_protocol_does_not_ignore_extra_hash(self):
  p=self.payload();p['pending_catalog_sha256']='0'*64
  r=self.reject(p,'schema_rejected');self.assertEqual(r['evidence_status'],'not_run')
 def test_tampered_catalog_is_rejected(self):
  f=self.f;batch=deepcopy(f.batch);batch['pending_catalog']['entries'][0]['quote']='篡改原文'
  with self.assertRaises(old.MultiAIError) as e:self.m.validate_output(f.store,f.cid,batch,self.payload())
  self.assertEqual(e.exception.diagnostic['rule'],'pending_catalog_mismatch')
 def test_unknown_id_still_rejected(self):
  p=self.payload();p['pending_evidence'][0]['evidence_ids'][1]='PE_'+'f'*24
  self.reject(p,'pending_candidate_not_in_catalog')
 def test_foreign_case_candidate_still_rejected(self):
  f=self.f;cid=f.store.create_case('完全虚构其他案件')
  ids=[f.store.attach_document(cid,d.file_name,d.original_bytes) for d in f.store.get_case(f.cid).documents.values()]
  batch=self.m.prepare_case(f.store,cid,ids,f.settings);p=self.payload()
  p['pending_evidence'][0]['evidence_ids'][1]=batch['pending_catalog']['entries'][0]['candidate_id']
  self.reject(p,'pending_candidate_not_in_catalog')
 def test_stale_batch_context_still_rejected(self):
  p=self.payload();p['batch_sha256']='0'*64;self.reject(p,'case_or_batch_mismatch')
 def test_old_12_batch_authorization_not_reused(self):
  f=self.f;batch=v12.prepare_case(f.store,f.cid,list(f.ids.values()),f.settings)
  with patch('multidoc_ai.invoke') as call,self.assertRaises(old.MultiAIError):
   self.m.analyze_case(f.store,f.cid,list(f.ids.values()),f.settings,f.quota,f.settings.principal,
      authorized_batch=batch['batch_sha256'],coverage_acknowledged=f.batch['required_ack'])
  call.assert_not_called()
 def test_post_response_directory_change_detected_independently_of_model(self):
  f=self.f;original=self.m.prepare_case;count=[]
  def prepare(*a,**kw):
   batch=original(*a,**kw);count.append(1)
   if len(count)>1:batch['pending_catalog']['sha256']='0'*64
   return batch
  with patch('multidoc_v13.prepare_case',side_effect=prepare):
   self.reject(self.payload(),'pending_catalog_changed_during_call')
 def test_changed_original_is_rejected_before_binding(self):
  f=self.f;p=self.payload()
  def callback(*a,**kw):
   f.store._cases[f.cid].documents[f.ids['D04']].original_bytes+=b'bad'
   return {'provider_status':'completed','call_status':'response_received','token_usage':{'total_tokens':120},'output_text':json.dumps(p,ensure_ascii=False)}
  with patch('multidoc_ai.invoke',side_effect=callback),self.assertRaises(old.MultiAIError):
   self.m.analyze_case(f.store,f.cid,list(f.ids.values()),f.settings,f.quota,f.settings.principal,
    authorized_batch=f.batch['batch_sha256'],coverage_acknowledged=f.batch['required_ack'])
  self.assertFalse(f.store.get_case(f.cid).inferences)
 def test_hash_in_receipt_and_audit_cannot_be_forged(self):
  f=self.f;r=self.run_ai();r['receipt']['pending_catalog_sha256']='0'*64
  with self.assertRaises(old.MultiAIError):old.import_case_analysis(f.store,f.cid,r)
  self.assertFalse(f.store.get_case(f.cid).inferences)
 def test_zip_with_full_analysis_roundtrip(self):
  import workspace_bundle as w
  f=self.f;r=self.run_ai();old.import_case_analysis(f.store,f.cid,r)
  archive=w.export_workspace(f.store,f.cid,analysis=r);target=CaseStore();out=w.restore_workspace(target,archive)
  self.assertEqual(out['analysis']['raw_output'],r['raw_output']);self.assertNotIn('pending_catalog_sha256',out['analysis']['raw_output'])
  self.assertEqual(target.get_case(f.cid).analysis_receipts,f.store.get_case(f.cid).analysis_receipts)
 def test_zip_without_attachment_rebuilds_server_directory(self):
  import workspace_bundle as w
  f=self.f;r=self.run_ai();old.import_case_analysis(f.store,f.cid,r)
  target=CaseStore();out=w.restore_workspace(target,w.export_workspace(f.store,f.cid))
  self.assertIsNone(out['analysis']);self.assertEqual(target.get_case(f.cid).analysis_receipts,f.store.get_case(f.cid).analysis_receipts)
 def test_zip_receipt_hash_tamper_refused_atomically(self):
  import workspace_bundle as w
  f=self.f;r=self.run_ai();old.import_case_analysis(f.store,f.cid,r)
  with zipfile.ZipFile(io.BytesIO(w.export_workspace(f.store,f.cid))) as z:members={n:z.read(n) for n in z.namelist()}
  payload=json.loads(members['case.json']);payload['analysis_receipts'][0]['pending_catalog_sha256']='0'*64
  members['case.json']=w.encoded(payload);manifest=json.loads(members['manifest.json'])
  for item in manifest['members']:
   if item['path']=='case.json':item.update(size=len(members['case.json']),sha256=hashlib.sha256(members['case.json']).hexdigest())
  members['manifest.json']=w.encoded(manifest);out=io.BytesIO()
  with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
   for n,data in members.items():z.writestr(n,data)
  target=CaseStore();cid=target.create_case('保留当前虚构案件');before=target.export_json(cid)
  with self.assertRaises(w.WorkspaceError):w.restore_workspace(target,out.getvalue())
  self.assertEqual(target.export_json(cid),before);self.assertNotIn(f.cid,target.list_cases())
 def test_sdk_both_providers_accept_13_without_hash_output(self):
  f=self.f
  for provider in ('deepseek','openai'):
   cfg=replace(f.settings,provider=provider);f.batch=self.m.prepare_case(f.store,f.cid,list(f.ids.values()),cfg);p=self.payload();calls=[]
   def handler(req):
    calls.append(json.loads(req.content))
    return httpx.Response(200,json={'id':'mock13','object':'response','created_at':1,'status':'completed','model':'offline',
      'usage':{'total_tokens':120},'output':[{'id':'msg','type':'message','role':'assistant','status':'completed',
      'content':[{'type':'output_text','text':json.dumps(p,ensure_ascii=False),'annotations':[]}]}]})
   def factory(**kw):
    self.assertEqual(kw['max_retries'],0);return OpenAI(**kw,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
   quota=QuotaStore(Path(f.tmp.name)/(provider+'13.sqlite3'))
   r=self.m.analyze_case(f.store,f.cid,list(f.ids.values()),cfg,quota,cfg.principal,
      authorized_batch=f.batch['batch_sha256'],coverage_acknowledged=f.batch['required_ack'],client_factory=factory)
   self.assertEqual(len(calls),1);self.assertNotIn('pending_catalog_sha256',calls[0]['text']['format']['schema']['properties'])
   self.assertEqual(r['receipt']['format_status'],'passed');self.assertEqual(r['receipt']['semantic_status'],'pending_human_review')
 def test_hash_is_server_metadata_not_filled_into_any_raw_response(self):
  p=self.payload();before=deepcopy(p);r=self.run_ai(p)
  self.assertEqual(p,before);self.assertEqual(r['raw_output'],before)
  self.assertNotIn('pending_catalog_sha256',r['raw_output'])
 def test_title_support_and_original_technical_guard_remain(self):
  f=self.f;p=self.payload();p['pending_evidence']=[f.item((fixtures.BODY,fixtures.TITLE),'待核实推断：EDR摘要原始数据是否需要核查？')]
  self.assertTrue(self.run_ai(p)['pending_evidence'])
 def test_no_title_is_still_unsupported(self):
  p=self.payload();p['pending_evidence']=[self.f.item((fixtures.BODY,),'待核实推断：EDR摘要原始数据是否需要核查？')]
  self.reject(p,'unsupported_data_term')
 def test_wrong_version_not_auto_upgraded(self):
  p=self.payload();p['schema_version']='multidoc-analysis/1.2';self.reject(p,'schema_rejected')
 def test_repeated_import_is_idempotent_and_keeps_manual_reviews(self):
  f=self.f;r=self.run_ai();old.import_case_analysis(f.store,f.cid,r)
  fact=f.store.get_case(f.cid).facts[0];f.store.confirm_fact(f.cid,fact.statement_id,'虚构复核人','仅用于测试')
  before=f.store.export_json(f.cid);old.import_case_analysis(f.store,f.cid,r)
  self.assertEqual(f.store.export_json(f.cid),before)
 def test_version_mixed_receipt_cannot_be_imported(self):
  f=self.f;r=self.run_ai();r['receipt']['schema_version']='multidoc-analysis/1.2'
  with self.assertRaises(old.MultiAIError):old.import_case_analysis(f.store,f.cid,r)
  self.assertFalse(f.store.get_case(f.cid).inferences)
 def test_budget_report_is_only_local_sdk_serialization(self):
  from tools.prepare_v13_b01 import report
  with patch('security.Settings.from_secrets',side_effect=AssertionError('no Secrets')),patch('security.QuotaStore',side_effect=AssertionError('no quota')):
   actual=report()
  expected=json.loads((Path(__file__).resolve().parents[1]/'docs/V13_B01_BUDGET.json').read_text())
  self.assertEqual(actual,expected);self.assertEqual(actual['real_model_calls'],0)
  for row in actual['rows']:
   self.assertLessEqual(row['budget']['request_bytes'],128000);self.assertIsNone(row['input_tokens'])
 def test_exact_duplicate_question_still_rejected(self):
  p=self.payload();p['pending_evidence']*=2;self.reject(p,'pending_duplicate_question')
 def test_illegal_dssad_still_rejected(self):
  p=self.payload();p['pending_evidence'][0]['reasoning']='待核实推断：DSSAD是否记录事故？';self.reject(p,'unsupported_data_term')
 def test_authorization_and_input_budget_remain_pre_call_guards(self):
  f=self.f
  with patch('multidoc_ai.invoke') as call,self.assertRaises(old.MultiAIError):
   self.m.analyze_case(f.store,f.cid,list(f.ids.values()),replace(f.settings,max_request_bytes=10),f.quota,f.settings.principal,
     authorized_batch=f.batch['batch_sha256'],coverage_acknowledged=f.batch['required_ack'])
  call.assert_not_called();self.assertEqual(f.quota.budget_snapshot(f.settings,f.settings.principal)['daily_calls_remaining'],20)
