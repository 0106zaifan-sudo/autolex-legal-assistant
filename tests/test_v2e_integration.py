"""V2E完整B01；所有响应人工构造或官方SDK+本地HTTP Mock，无真实API。"""
from copy import deepcopy
from dataclasses import replace
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from openai import OpenAI
from case_store import CaseStore
from security import Settings,QuotaStore
import multidoc_ai as legacy
from test_case_store import document

DATA=Path(__file__).resolve().parents[1]/'datasets/CASE-001/standard'
SITE='事故时间栏目08:30来自P01口述，仅按分钟填写，未作时钟校核。'
EDR='EDR只提供相对触发锚点t=0的测试摘要，未提供可信绝对日期。'
BODY='原始二进制数据及提取过程镜像未提供，摘要为二次转写。'
TITLE='模拟材料：EDR摘要'
COMPANY='原始二进制日志、设备镜像和完整性签名未随本说明提供。'
HASH='pbkdf2_sha256$200000$'+'ab'*16+'$'+'cd'*32

class V2E(unittest.TestCase):
 def setUp(self):
  import multidoc_v12 as m
  self.m=m;self.store=CaseStore();self.cid=self.store.create_case('完全虚构 CASE-001 B01 V2E');self.ids={}
  for d in json.loads((DATA/'manifest.json').read_text())['documents']:
   if d['material_id'] in ('D01','D02','D03','D04'):
    path=DATA/d['path'];self.ids[d['material_id']]=self.store.attach_document(self.cid,path.name,path.read_bytes())
  self.settings=Settings(api_key='offline-not-real',password_hash=HASH,mode='local',single_instance=True,provider='deepseek')
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.quota=QuotaStore(Path(self.tmp.name)/'test-only.sqlite3')
  self.batch=m.prepare_case(self.store,self.cid,list(self.ids.values()),self.settings)
 def entry(self,q):return next(e for e in self.batch['pending_catalog']['entries'] if e['quote'].rstrip('\r\n')==q)
 def item(self,quotes=(SITE,EDR),reason='待核实推断：D01口述分钟与D04的EDR相对锚点是否有可核对基准？'):
  ids=[self.entry(q)['candidate_id'] for q in quotes]
  return {'anchor_id':ids[0],'evidence_ids':ids,'reasoning':reason}
 def payload(self):
  from timeline_candidates import build_event_catalog
  events=build_event_catalog(self.batch)['candidates']
  e=self.entry(SITE)
  return {'schema_version':self.m.SCHEMA_VERSION,'prompt_version':self.m.PROMPT_VERSION,'case_id':self.cid,
   'batch_sha256':self.batch['batch_sha256'],'pending_catalog_sha256':self.batch['pending_catalog']['sha256'],
   'facts':[{'kind':'事实','text':SITE,'reasoning':'','sources':[{'source_id':e['source_id'],'quote':SITE}]}],
   'timeline':[{'candidate_id':c['candidate_id'],'kind':c['allowed_kinds'][0]} for c in events],
   'pending_evidence':[self.item()], 'relations':[{'left':{'source_id':self.entry(SITE)['source_id'],'quote':SITE},
      'right':{'source_id':self.entry(EDR)['source_id'],'quote':EDR},'relation_type':'needs_verification',
      'reasoning':'待核实推断：口述分钟与相对锚点的来源是否需要核对？'}]}
 def run_ai(self,p=None,**kw):
  p=self.payload() if p is None else p
  response={'provider_status':'completed','call_status':'response_received','provider_model':'offline-mock',
    'token_usage':{'input_tokens':100,'output_tokens':20,'total_tokens':120},'output_text':json.dumps(p,ensure_ascii=False)}
  with patch('multidoc_ai.invoke',return_value=response) as call:
   result=self.m.analyze_case(self.store,self.cid,list(self.ids.values()),self.settings,self.quota,self.settings.principal,
    authorized_batch=kw.pop('authorized_batch',self.batch['batch_sha256']),coverage_acknowledged=kw.pop('coverage_acknowledged',self.batch['required_ack']),client_factory=lambda **x:None,**kw)
  call.assert_called_once();return result
 def rejected(self,p,rule):
  before=self.store.export_json(self.cid)
  with self.assertRaises(legacy.MultiAIError) as caught:self.run_ai(p)
  r=caught.exception.receipt;self.assertEqual(r['validation_diagnostic']['rule'],rule)
  self.assertEqual(r['token_usage']['total_tokens'],120);self.assertEqual(self.store.export_json(self.cid),before)
  self.assertEqual(r['schema_version'],'multidoc-analysis/1.2');return r
 def test_four_sections_single_request_and_no_auto_import(self):
  r=self.run_ai()
  for key in ('facts','timeline','relations','pending_evidence'):self.assertTrue(r[key],key)
  self.assertEqual(r['schema_version'],'multidoc-analysis/1.2');self.assertEqual(r['receipt']['evidence_status'],'passed')
  self.assertEqual(r['receipt']['semantic_status'],'pending_human_review');self.assertFalse(self.store.get_case(self.cid).inferences)
  self.assertEqual(self.quota.budget_snapshot(self.settings,self.settings.principal)['daily_calls_remaining'],19)
 def test_deterministic_text_d01_d04(self):
  r=self.run_ai();row=r['pending_evidence'][0]
  self.assertEqual(row['text'],self.entry(SITE)['quote']);self.assertEqual(len(row['sources']),2)
 def test_deterministic_text_d01_d03(self):
  p=self.payload();p['pending_evidence']=[self.item((SITE,COMPANY),'待核实推断：D01时间来源和D03原始日志是否需要分别核查？')]
  r=self.run_ai(p);self.assertEqual(len(r['pending_evidence'][0]['sources']),2)
 def test_title_support(self):
  p=self.payload();p['pending_evidence']=[self.item((BODY,TITLE),'待核实推断：D04的EDR摘要原始数据是否需要核查？')]
  self.assertEqual(len(self.run_ai(p)['pending_evidence'][0]['sources']),2)
 def test_missing_title_still_rejected(self):
  p=self.payload();p['pending_evidence']=[self.item((BODY,),'待核实推断：EDR原始数据是否需要核查？')]
  self.rejected(p,'unsupported_data_term')
 def test_illegal_data_term_still_rejected(self):
  p=self.payload();p['pending_evidence'][0]['reasoning']='待核实推断：DSSAD是否记录事故？';self.rejected(p,'unsupported_data_term')
 def test_unknown_candidate_and_safe_diagnostic(self):
  p=self.payload();p['pending_evidence'][0]['evidence_ids'][1]='PE_'+'f'*24
  r=self.rejected(p,'pending_candidate_not_in_catalog');d=r['validation_diagnostic']
  self.assertEqual((d['section'],d['item_index'],d['stage']),('pending_evidence',0,'pending_selection'))
  self.assertNotIn(SITE,json.dumps(r,ensure_ascii=False))
 def test_extra_free_text_not_accepted(self):
  p=self.payload();p['pending_evidence'][0]['text']='改写摘要';self.rejected(p,'schema_rejected')
 def test_anchor_not_selected(self):
  p=self.payload();p['pending_evidence'][0]['anchor_id']=self.entry(BODY)['candidate_id'];self.rejected(p,'pending_anchor_not_selected')
 def test_duplicate_ids_and_questions_rejected(self):
  p=self.payload();p['pending_evidence'][0]['evidence_ids']*=2;self.rejected(p,'pending_duplicate_evidence')
 def test_distinct_questions_preserved(self):
  p=self.payload();x=deepcopy(p['pending_evidence'][0]);x['reasoning']='待核实推断：两份材料的来源独立性是否需要核对？';p['pending_evidence'].append(x)
  self.assertEqual(len(self.run_ai(p)['pending_evidence']),2)
 def test_duplicate_questions_rejected(self):
  p=self.payload();p['pending_evidence']*=2;self.rejected(p,'pending_duplicate_question')
 def test_catalog_tampering_rejected(self):
  p=self.payload();p['pending_catalog_sha256']='0'*64;self.rejected(p,'pending_catalog_mismatch')
 def test_foreign_case_id_rejected(self):
  p=self.payload();p['case_id']='case_'+'0'*32;self.rejected(p,'case_or_batch_mismatch')
 def test_wrong_subject_remains_human_review(self):
  p=self.payload();p['pending_evidence'][0]['reasoning']='待核实推断：驾驶人自述已收到提示是否需要核查？'
  self.assertEqual(self.run_ai(p)['receipt']['semantic_status'],'pending_human_review')
 def test_auth_coverage_budget_and_quota_block_before_call(self):
  for args in ({'authorized_batch':None},{'coverage_acknowledged':[]}):
   with patch('multidoc_ai.invoke') as call,self.assertRaises(legacy.MultiAIError):
    self.m.analyze_case(self.store,self.cid,list(self.ids.values()),self.settings,self.quota,self.settings.principal,
      authorized_batch=args.get('authorized_batch',self.batch['batch_sha256']),coverage_acknowledged=args.get('coverage_acknowledged',self.batch['required_ack']))
   call.assert_not_called()
 def test_import_and_workspace_roundtrip_preserve_audit(self):
  import workspace_bundle as w
  r=self.run_ai();legacy.import_case_analysis(self.store,self.cid,r)
  case=self.store.get_case(self.cid);self.assertTrue(case.analysis_receipts[0]['pending_selection_ids'])
  data=w.export_workspace(self.store,self.cid,analysis=r);restored=CaseStore();out=w.restore_workspace(restored,data)
  self.assertEqual(out['analysis']['pending_selection'],r['pending_selection'])
  self.assertEqual(restored.get_case(self.cid).analysis_receipts,case.analysis_receipts)
  before=restored.export_json(self.cid);legacy.import_case_analysis(restored,self.cid,r);self.assertEqual(restored.export_json(self.cid),before)
 def test_workspace_tampered_selection_audit_rejected(self):
  import workspace_bundle as w
  r=self.run_ai();legacy.import_case_analysis(self.store,self.cid,r)
  self.store._cases[self.cid].analysis_receipts[0]['pending_selection_ids'][0]['anchor_id']='PE_'+'f'*24
  with self.assertRaises(w.WorkspaceError):w.export_workspace(self.store,self.cid)
 def test_import_rejects_tampered_restore_and_no_partial_write(self):
  r=self.run_ai();before=self.store.export_json(self.cid);r['pending_evidence'][0]['text']='伪造'
  with self.assertRaises(legacy.MultiAIError):legacy.import_case_analysis(self.store,self.cid,r)
  self.assertEqual(self.store.export_json(self.cid),before)
 def test_sdk_serialization_both_providers(self):
  for provider in ('deepseek','openai'):
   settings=replace(self.settings,provider=provider,model='offline-model');self.batch=self.m.prepare_case(self.store,self.cid,list(self.ids.values()),settings)
   p=self.payload();calls=[]
   def handler(req):
    calls.append(json.loads(req.content))
    return httpx.Response(200,json={'id':'mock','object':'response','created_at':1,'model':'offline','status':'completed',
     'usage':{'input_tokens':100,'output_tokens':20,'total_tokens':120},'output':[{'id':'msg','type':'message','role':'assistant','status':'completed',
      'content':[{'type':'output_text','text':json.dumps(p,ensure_ascii=False),'annotations':[]}]}]})
   def factory(**kw):
    self.assertEqual(kw['max_retries'],0);return OpenAI(**kw,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
   quota=QuotaStore(Path(self.tmp.name)/(provider+'.sqlite3'))
   r=self.m.analyze_case(self.store,self.cid,list(self.ids.values()),settings,quota,settings.principal,
     authorized_batch=self.batch['batch_sha256'],coverage_acknowledged=self.batch['required_ack'],client_factory=factory)
   self.assertEqual(len(calls),1);self.assertEqual(r['receipt']['schema_version'],'multidoc-analysis/1.2')
   schema=calls[0]['text']['format']['schema'];fields=schema['$defs']['PendingSelection']['properties']
   self.assertEqual(set(fields),{'anchor_id','evidence_ids','reasoning'});self.assertIn('enum',fields['anchor_id'])
 def test_real_foreign_case_candidate_is_not_accepted(self):
  cid=self.store.create_case('另一个完全虚构案件')
  ids=[self.store.attach_document(cid,d.file_name,d.original_bytes) for d in self.store.get_case(self.cid).documents.values()]
  foreign=self.m.prepare_case(self.store,cid,ids,self.settings);p=self.payload()
  p['pending_evidence'][0]['evidence_ids'][1]=foreign['pending_catalog']['entries'][0]['candidate_id']
  self.rejected(p,'pending_candidate_not_in_catalog')
 def test_trusted_catalog_copy_tamper_detected(self):
  p=self.payload();bad=deepcopy(self.batch);bad['pending_catalog']['entries'][0]['quote']='篡改'
  with self.assertRaises(legacy.MultiAIError) as e:self.m.validate_output(self.store,self.cid,bad,p)
  self.assertEqual(e.exception.diagnostic['rule'],'pending_catalog_mismatch')
 def test_long_physical_line_is_blocked_with_omission_diagnostic(self):
  store=CaseStore();cid=store.create_case('完全虚构长行')
  ids=[store.attach_document(cid,'模拟长行.docx',document('企业主张：'+'甲'*1005+'；未收到提示。')),
       store.attach_document(cid,'模拟正常.docx',document('车辆发生碰撞。'))]
  with self.assertRaises(legacy.MultiAIError) as e:self.m.prepare_case(store,cid,ids,self.settings)
  self.assertEqual(e.exception.diagnostic['rule'],'pending_catalog_incomplete')
  self.assertGreater(e.exception.diagnostic['excluded_count'],0)
 def test_too_many_sources_is_explicitly_blocked(self):
  store=CaseStore();cid=store.create_case('完全虚构过量目录')
  ids=[store.attach_document(cid,f'模拟{i}.docx',document(*[f'模拟第{j}行。' for j in range(50)],title=str(i))) for i in range(2)]
  with self.assertRaises(legacy.MultiAIError) as e:self.m.prepare_case(store,cid,ids,self.settings)
  self.assertEqual(e.exception.diagnostic['rule'],'source_or_character_limit_exceeded')
 def test_request_budget_failure_does_not_charge_quota(self):
  with patch('multidoc_ai.invoke') as call,self.assertRaises(legacy.MultiAIError):
   self.m.analyze_case(self.store,self.cid,list(self.ids.values()),replace(self.settings,max_request_bytes=10),self.quota,self.settings.principal,
    authorized_batch=self.batch['batch_sha256'],coverage_acknowledged=self.batch['required_ack'])
  call.assert_not_called();self.assertEqual(self.quota.budget_snapshot(self.settings,self.settings.principal)['daily_calls_remaining'],20)
 def test_exhausted_quota_no_second_request(self):
  from security import SecurityError
  self.settings=replace(self.settings,daily_limit=1,cooldown=0)
  self.run_ai()
  with patch('multidoc_ai.invoke') as call,self.assertRaises(SecurityError):
   self.m.analyze_case(self.store,self.cid,list(self.ids.values()),self.settings,self.quota,self.settings.principal,
    authorized_batch=self.batch['batch_sha256'],coverage_acknowledged=self.batch['required_ack'])
  call.assert_not_called()
 def test_saved_question_hash_and_statement_link_tamper_rejected(self):
  import workspace_bundle as w
  r=self.run_ai();legacy.import_case_analysis(self.store,self.cid,r)
  original=deepcopy(self.store._cases[self.cid])
  for key,value in (('pending_statement_ids',['statement_'+'f'*24]),('pending_catalog_sha256','0'*64)):
   self.store._cases[self.cid]=original.model_copy(deep=True);self.store._cases[self.cid].analysis_receipts[0][key]=value
   with self.assertRaises(w.WorkspaceError):w.export_workspace(self.store,self.cid)
 def test_workspace_without_analysis_still_retains_selection_history(self):
  import workspace_bundle as w
  r=self.run_ai();legacy.import_case_analysis(self.store,self.cid,r)
  archive=w.export_workspace(self.store,self.cid);restored=CaseStore();out=w.restore_workspace(restored,archive)
  self.assertIsNone(out['analysis']);self.assertEqual(restored.get_case(self.cid).analysis_receipts,self.store.get_case(self.cid).analysis_receipts)
 def test_prior_fact_review_history_is_not_lost(self):
  r=self.run_ai();legacy.import_case_analysis(self.store,self.cid,r)
  case=self.store.get_case(self.cid);fact=case.facts[0]
  self.store.confirm_fact(self.cid,fact.statement_id,'虚构复核员','仅用于离线测试')
  before=self.store.get_case(self.cid).reviews
  legacy.import_case_analysis(self.store,self.cid,r)
  self.assertEqual(self.store.get_case(self.cid).reviews,before)
 def test_failure_preserves_schema_status_and_sanitizes_bad_identifier(self):
  p=self.payload();p['pending_evidence'][0]['evidence_ids'][1]='恶意隐私文字'
  r=self.rejected(p,'pending_candidate_not_in_catalog')
  self.assertEqual(r['format_status'],'passed');self.assertEqual(r['evidence_status'],'failed')
  self.assertNotIn('恶意隐私文字',json.dumps(r,ensure_ascii=False))
 def test_sdk_schema_strict_required_and_actual_adapted_budget(self):
  request,budget=self.m.request_for(self.batch,self.settings)
  schema=request['text']['format']['schema']
  def walk(node):
   if isinstance(node,dict):
    if node.get('type')=='object':
     self.assertFalse(node['additionalProperties']);self.assertEqual(set(node['required']),set(node['properties']))
    for v in node.values():walk(v)
   elif isinstance(node,list):
    for v in node:walk(v)
  walk(schema)
  self.assertEqual(budget['request_bytes'],len(json.dumps(request,ensure_ascii=False,separators=(',',':')).encode())+1024)
  self.assertEqual(len(json.loads(request['input'])['documents']),4)
  self.assertLessEqual(budget['request_bytes'],128000)
 def test_schema_does_not_allow_claim_reasoning_or_free_pending_quote(self):
  p=self.payload();p['facts'][0]['reasoning']='附加说明';self.rejected(p,'schema_rejected')
 def test_model_callback_archive_change_is_not_imported(self):
  p=self.payload();before=self.store.export_json(self.cid)
  def callback(*a,**kw):
   self.store._cases[self.cid].documents[self.ids['D04']].original_bytes+=b'bad'
   return {'provider_status':'completed','call_status':'response_received','token_usage':{'total_tokens':120},'output_text':json.dumps(p,ensure_ascii=False)}
  with patch('multidoc_ai.invoke',side_effect=callback),self.assertRaises(legacy.MultiAIError):
   self.m.analyze_case(self.store,self.cid,list(self.ids.values()),self.settings,self.quota,self.settings.principal,
      authorized_batch=self.batch['batch_sha256'],coverage_acknowledged=self.batch['required_ack'])
  self.assertFalse(self.store.get_case(self.cid).inferences)
 def test_same_run_id_cannot_silently_replace_another_analysis(self):
  r=self.run_ai();legacy.import_case_analysis(self.store,self.cid,r);before=self.store.export_json(self.cid)
  self.settings=replace(self.settings,cooldown=0)
  p=self.payload();p['pending_evidence'][0]['reasoning']='待核实推断：原始记录的时钟基准是否需要分别核查？'
  newer=self.run_ai(p);newer['receipt']['run_id']=r['receipt']['run_id']
  with self.assertRaises(legacy.MultiAIError) as e:legacy.import_case_analysis(self.store,self.cid,newer)
  self.assertEqual(e.exception.diagnostic['rule'],'run_id_conflict');self.assertEqual(self.store.export_json(self.cid),before)
 def test_receipt_output_hash_tamper_is_rejected(self):
  r=self.run_ai();r['receipt']['analysis_output_sha256']='0'*64
  with self.assertRaises(legacy.MultiAIError):legacy.import_case_analysis(self.store,self.cid,r)
  self.assertFalse(self.store.get_case(self.cid).inferences)
 def test_budget_report_is_reproducible_without_secrets_or_quota(self):
  from tools.prepare_v2e_b01 import report
  with patch('security.QuotaStore',side_effect=AssertionError('no quota')),patch('security.Settings.from_secrets',side_effect=AssertionError('no Secrets')):
   actual=report()
  saved=json.loads((Path(__file__).resolve().parents[1]/'docs/V2E_B01_BUDGET.json').read_text())
  self.assertEqual(actual,saved);self.assertEqual(actual['real_model_calls'],0)
  self.assertTrue(all(row['input_tokens'] is None for row in actual['rows']))
 def test_whole_line_scope_is_preserved_not_split_into_fake_facts(self):
  title=self.entry(BODY);self.assertEqual(title['quote'],BODY+'\n')
  p=self.payload();p['pending_evidence']=[self.item((BODY,TITLE),'待核实推断：EDR摘要的二次转写与原始数据是否需要核对？')]
  r=self.run_ai(p);self.assertEqual(r['pending_evidence'][0]['text'],BODY+'\n')
  self.assertEqual(r['pending_evidence'][0]['kind'],'推断')
 def test_prompt_has_one_pending_contract_without_legacy_copy_instructions(self):
  self.assertNotIn('输出独立multidoc-analysis/1.1 Schema',self.m.PROMPT)
  self.assertNotIn('pending_evidence为推断，text必须',self.m.PROMPT)
  self.assertIn('只输出anchor_id、evidence_ids、reasoning',self.m.PROMPT)
 def test_v12_tampered_zip_restore_is_atomic_even_with_recomputed_manifest(self):
  import workspace_bundle as w
  import io,zipfile,hashlib
  r=self.run_ai();legacy.import_case_analysis(self.store,self.cid,r)
  raw=w.export_workspace(self.store,self.cid)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:members={n:z.read(n) for n in z.namelist()}
  payload=json.loads(members['case.json']);payload['analysis_receipts'][0]['pending_selection_ids'][0]['anchor_id']='PE_'+'f'*24
  members['case.json']=w.encoded(payload);manifest=json.loads(members['manifest.json'])
  for item in manifest['members']:
   if item['path']=='case.json':item.update(size=len(members['case.json']),sha256=hashlib.sha256(members['case.json']).hexdigest())
  members['manifest.json']=w.encoded(manifest);output=io.BytesIO()
  with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
   for name,data in members.items():z.writestr(name,data)
  target=CaseStore();other=target.create_case('保留当前虚构案件');before=target.export_json(other)
  with self.assertRaises(w.WorkspaceError):w.restore_workspace(target,output.getvalue())
  self.assertEqual(target.export_json(other),before);self.assertNotIn(self.cid,target.list_cases())
 def test_matching_existing_manual_inference_keeps_origin_and_zip_valid(self):
  import workspace_bundle as w
  r=self.run_ai();row=r['pending_evidence'][0];ids=[]
  for ref in row['sources']:ids.append(self.store.add_evidence(self.cid,ref['document_id'],ref['unit_index'],ref['start'],ref['end'],ref['quote']))
  case=self.store._cases[self.cid]
  sid=self.store._append_statement(case,row['reasoning'],'ai_inference',ids,origin='manual')
  legacy.import_case_analysis(self.store,self.cid,r)
  stored=next(x for x in self.store.get_case(self.cid).inferences if x.statement_id==sid)
  self.assertEqual(stored.origin,'manual');self.assertEqual(stored.verification,'unverified')
  archive=w.export_workspace(self.store,self.cid);restored=CaseStore();w.restore_workspace(restored,archive)
  self.assertEqual(next(x.origin for x in restored.get_case(self.cid).inferences if x.statement_id==sid),'manual')
