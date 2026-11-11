"""1.4专项：官方SDK仅本地Mock，固定虚构完整B01。"""
from copy import deepcopy
from dataclasses import replace
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from openai import OpenAI
from pydantic import ValidationError
from case_store import CaseStore
from security import QuotaStore
import multidoc_ai as old
import test_v2e_integration as fixtures

class Alias14(unittest.TestCase):
 def setUp(self):
  import multidoc_v14 as m
  import pending_aliases as a
  self.m=m;self.a=a;self.f=fixtures.V2E();self.f.setUp();self.addCleanup(self.f.tmp.cleanup)
  self.f.m=m;self.f.batch=m.prepare_case(self.f.store,self.f.cid,list(self.f.ids.values()),self.f.settings)
 def payload(self):
  f=self.f;p=f.payload();p.pop('pending_catalog_sha256')
  lookup={r['candidate_id']:r['alias'] for r in f.batch['alias_map']['entries']}
  for row in p['pending_evidence']:
   row['anchor_alias']=lookup[row.pop('anchor_id')];row['evidence_aliases']=[lookup[x] for x in row.pop('evidence_ids')]
  return p
 def run_ai(self,p=None):return self.f.run_ai(self.payload() if p is None else p)
 def rejected(self,p,rule):
  f=self.f;before=f.store.export_json(f.cid)
  with self.assertRaises(old.MultiAIError) as e:self.run_ai(p)
  r=e.exception.receipt;self.assertEqual(r['validation_diagnostic']['rule'],rule)
  self.assertEqual(r['token_usage']['total_tokens'],120);self.assertEqual(f.store.export_json(f.cid),before)
  return r
 def test_schema_only_alias_choice_and_reasoning(self):
  request,budget=self.m.request_for(self.f.batch,self.f.settings)
  props=request['text']['format']['schema']['$defs']['AliasSelection']['properties']
  self.assertEqual(set(props),{'anchor_alias','evidence_aliases','reasoning'})
  aliases={x['alias'] for x in self.f.batch['alias_map']['entries']}
  self.assertEqual(set(props['anchor_alias']['enum']),aliases)
  self.assertEqual(set(props['evidence_aliases']['items']['enum']),aliases)
 def test_aliases_deterministic_and_not_sequential(self):
  f=self.f;b=self.m.prepare_case(f.store,f.cid,list(reversed(f.ids.values())),f.settings)
  self.assertEqual(b,f.batch)
  aliases=[r['alias'] for r in b['alias_map']['entries']]
  self.assertEqual(len(aliases),62);self.assertEqual(len(set(aliases)),62)
  self.assertTrue(all(self.a.ALIAS_PATTERN.fullmatch(x) for x in aliases))
 def test_every_single_character_substitution_is_not_another_valid_alias(self):
  aliases={r['alias'] for r in self.f.batch['alias_map']['entries']}
  for alias in aliases:
   for pos in range(2,6):
    for c in self.a.ALPHABET:
     if c!=alias[pos]:self.assertNotIn(alias[:pos]+c+alias[pos+1:],aliases)
 def test_alias_capacity_refuses_without_truncation(self):
  catalog=deepcopy(self.f.batch['pending_catalog'])
  with patch('pending_aliases.MAX_ALIASES',1),self.assertRaises(self.a.AliasError):self.a.build_alias_map(catalog,'fixture-context')
 def test_full_four_sections_one_request_no_auto_import(self):
  r=self.run_ai();self.assertEqual(r['schema_version'],'multidoc-analysis/1.4')
  for key in ('facts','timeline','relations','pending_evidence'):self.assertTrue(r[key])
  self.assertFalse(self.f.store.get_case(self.f.cid).inferences)
  self.assertEqual(self.f.quota.budget_snapshot(self.f.settings,self.f.settings.principal)['daily_calls_remaining'],19)
 def test_source_text_and_pe_are_restored(self):
  r=self.run_ai();row=r['pending_evidence'][0]
  self.assertEqual(row['text'],self.f.entry(fixtures.SITE)['quote']);self.assertEqual(len(row['sources']),2)
  self.assertTrue(r['receipt']['pending_selection_ids'][0]['anchor_id'].startswith('PE_'))
  self.assertEqual(r['raw_output'],self.payload())
 def bad_alias(self):
  value=self.payload()['pending_evidence'][0]['anchor_alias']
  c=next(c for c in self.a.ALPHABET if c!=value[2]);return value[:2]+c+value[3:]
 def test_typo_selected_vs_unknown_exact_subset(self):
  p=self.payload();bad=self.bad_alias();p['pending_evidence'][0]['evidence_aliases'][1]=bad
  r=self.rejected(p,'pending_alias_not_in_catalog');d=r['validation_diagnostic']
  self.assertEqual(d['selected_aliases'],p['pending_evidence'][0]['evidence_aliases'])
  self.assertEqual(d['unknown_aliases'],[bad]);self.assertEqual(d['item_index'],0)
 def test_native_pydantic_context_enum_rejects_unknown(self):
  p=self.payload();p['pending_evidence'][0]['evidence_aliases'][1]=self.bad_alias()
  allowed={r['alias'] for r in self.f.batch['alias_map']['entries']}
  with self.assertRaises(ValidationError):self.m.Analysis14.model_validate(p,context={'allowed_aliases':allowed})
 def test_legal_but_irrelevant_alias_remains_unreviewed(self):
  p=self.payload();p['pending_evidence'][0]['reasoning']='待核实推断：驾驶人未制动是否造成事故并应承担责任？'
  r=self.run_ai(p);self.assertEqual(r['receipt']['semantic_status'],'pending_human_review')
  self.assertFalse(self.f.store.get_case(self.f.cid).facts)
 def test_anchor_not_selected(self):
  p=self.payload();selected=set(p['pending_evidence'][0]['evidence_aliases'])
  p['pending_evidence'][0]['anchor_alias']=next(r['alias'] for r in self.f.batch['alias_map']['entries'] if r['alias'] not in selected)
  self.rejected(p,'pending_anchor_not_selected')
 def test_duplicate_aliases_rejected(self):
  p=self.payload();p['pending_evidence'][0]['evidence_aliases']*=2;self.rejected(p,'pending_duplicate_evidence')
 def test_duplicate_questions_rejected(self):
  p=self.payload();p['pending_evidence']*=2;self.rejected(p,'pending_duplicate_question')
 def test_different_questions_preserved(self):
  p=self.payload();row=deepcopy(p['pending_evidence'][0]);row['reasoning']='待核实推断：不同来源是否具有独立性？';p['pending_evidence'].append(row)
  self.assertEqual(len(self.run_ai(p)['pending_evidence']),2)
 def test_no_lowercase_correction(self):
  p=self.payload();p['pending_evidence'][0]['anchor_alias']=p['pending_evidence'][0]['anchor_alias'].lower();self.rejected(p,'schema_rejected')
 def test_unknown_arbitrary_content_is_not_in_receipt(self):
  p=self.payload();p['pending_evidence'][0]['evidence_aliases'][1]='虚构隐私原文不可记录'
  r=self.rejected(p,'schema_rejected');self.assertNotIn('虚构隐私原文不可记录',json.dumps(r,ensure_ascii=False))
 def test_map_tampering_rejected(self):
  f=self.f;p=self.payload();b=deepcopy(f.batch);b['alias_map']['entries'][0]['alias']='P_AAAA'
  with self.assertRaises(old.MultiAIError):self.m.validate_output(f.store,f.cid,b,p)
 def test_directory_reordering_changes_map_and_context(self):
  f=self.f;b=deepcopy(f.batch);b['pending_catalog']['entries'].reverse()
  value={k:v for k,v in b['pending_catalog'].items() if k!='sha256'};b['pending_catalog']['sha256']=old.digest(value)
  other=self.a.build_alias_map(b['pending_catalog'],'fixture-context')
  self.assertNotEqual(other['sha256'],f.batch['alias_map']['sha256'])
  with self.assertRaises(old.MultiAIError):self.m.validate_output(f.store,f.cid,b,self.payload())
 def test_foreign_response_context_rejected(self):
  p=self.payload();p['case_id']='case_'+'f'*32;self.rejected(p,'case_or_batch_mismatch')
 def test_foreign_alias_not_in_current_map_rejected(self):
  f=self.f;cid=f.store.create_case('另一个虚构案件');ids=[f.store.attach_document(cid,d.file_name,d.original_bytes) for d in f.store.get_case(f.cid).documents.values()]
  other=self.m.prepare_case(f.store,cid,ids,f.settings);current={e['alias'] for e in f.batch['alias_map']['entries']}
  bad=next(e['alias'] for e in other['alias_map']['entries'] if e['alias'] not in current)
  p=self.payload();p['pending_evidence'][0]['evidence_aliases'][1]=bad;self.rejected(p,'pending_alias_not_in_catalog')
 def test_snapshot_change_invalidates_before_import(self):
  r=self.run_ai();self.f.store._cases[self.f.cid].documents[self.f.ids['D04']].original_bytes+=b'bad'
  with self.assertRaises(old.MultiAIError):old.import_case_analysis(self.f.store,self.f.cid,r)
  self.assertFalse(self.f.store.get_case(self.f.cid).inferences)
 def test_stale_batch_rejected(self):
  p=self.payload();p['batch_sha256']='0'*64;self.rejected(p,'case_or_batch_mismatch')
 def test_mixed_old_fields_rejected(self):
  p=self.payload();p['pending_evidence'][0]['anchor_id']='PE_'+'f'*24;self.rejected(p,'schema_rejected')
 def test_zip_with_and_without_analysis_preserves_alias_audit(self):
  import workspace_bundle as w
  f=self.f;r=self.run_ai();old.import_case_analysis(f.store,f.cid,r)
  for attachment in (None,r):
   target=CaseStore();out=w.restore_workspace(target,w.export_workspace(f.store,f.cid,analysis=attachment))
   self.assertEqual(target.get_case(f.cid).analysis_receipts,f.store.get_case(f.cid).analysis_receipts)
   if attachment:self.assertEqual(out['analysis']['pending_selection'],r['pending_selection'])
 def test_zip_alias_audit_tamper_rejected(self):
  import workspace_bundle as w
  f=self.f;r=self.run_ai();old.import_case_analysis(f.store,f.cid,r)
  f.store._cases[f.cid].analysis_receipts[0]['pending_alias_selection'][0]['anchor_alias']=self.bad_alias()
  with self.assertRaises(w.WorkspaceError):w.export_workspace(f.store,f.cid)
 def test_mixed_receipt_version_not_upgraded(self):
  f=self.f;r=self.run_ai();r['receipt']['schema_version']='multidoc-analysis/1.3'
  with self.assertRaises(old.MultiAIError):old.import_case_analysis(f.store,f.cid,r)
 def test_sdk_local_mock_both_providers_enum_and_source_alias(self):
  f=self.f
  for provider in ('deepseek','openai'):
   cfg=replace(f.settings,provider=provider,model='offline-model');f.batch=self.m.prepare_case(f.store,f.cid,list(f.ids.values()),cfg)
   raw=self.payload();calls=[]
   def handler(req):
    calls.append(json.loads(req.content));return httpx.Response(200,json={'id':'mock14','object':'response','created_at':1,'status':'completed','model':'offline',
      'usage':{'total_tokens':120},'output':[{'id':'msg','type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':json.dumps(raw,ensure_ascii=False),'annotations':[]}]}]})
   def factory(**kw):
    self.assertEqual(kw['max_retries'],0);return OpenAI(**kw,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
   quota=QuotaStore(Path(f.tmp.name)/(provider+'14.sqlite3'))
   r=self.m.analyze_case(f.store,f.cid,list(f.ids.values()),cfg,quota,cfg.principal,
     authorized_batch=f.batch['batch_sha256'],coverage_acknowledged=f.batch['required_ack'],client_factory=factory)
   self.assertEqual(len(calls),1);payload=json.loads(calls[0]['input'])
   aliases={s['pending_alias'] for s in payload['sources']}
   props=calls[0]['text']['format']['schema']['$defs']['AliasSelection']['properties']
   self.assertEqual(aliases,set(props['anchor_alias']['enum']));self.assertEqual(aliases,set(props['evidence_aliases']['items']['enum']))
   self.assertEqual(r['receipt']['schema_version'],'multidoc-analysis/1.4')
 def test_unknown_anchor_is_reported_separately(self):
  p=self.payload();bad=self.bad_alias();p['pending_evidence'][0]['anchor_alias']=bad
  d=self.rejected(p,'pending_alias_not_in_catalog')['validation_diagnostic']
  self.assertEqual(d['anchor_alias'],bad);self.assertEqual(d['unknown_aliases'],[bad])
  self.assertEqual(d['selected_aliases'],p['pending_evidence'][0]['evidence_aliases'])
 def test_booleans_numbers_and_old_pe_not_coerced(self):
  for value in (True,1,1.0,'PE_'+'f'*24):
   p=self.payload();p['pending_evidence'][0]['anchor_alias']=value
   with self.subTest(value=value),self.assertRaises(ValidationError):self.m.Analysis14.model_validate(p)
 def test_map_change_during_call_refuses(self):
  f=self.f;original=self.m.prepare_case;calls=[]
  def change(*args,**kw):
   result=original(*args,**kw);calls.append(1)
   if len(calls)>1:result['alias_map']['sha256']='0'*64
   return result
  with patch('multidoc_v14.prepare_case',side_effect=change):self.rejected(self.payload(),'pending_alias_map_changed_during_call')
 def test_unauthorized_call_cannot_reserve_or_invoke(self):
  f=self.f
  with patch('multidoc_ai.invoke') as call,self.assertRaises(old.MultiAIError):
   self.m.analyze_case(f.store,f.cid,list(f.ids.values()),f.settings,f.quota,f.settings.principal,
      authorized_batch=None,coverage_acknowledged=f.batch['required_ack'])
  call.assert_not_called();self.assertEqual(f.quota.budget_snapshot(f.settings,f.settings.principal)['daily_calls_remaining'],20)
 def test_low_request_budget_no_charge(self):
  f=self.f
  with patch('multidoc_ai.invoke') as call,self.assertRaises(old.MultiAIError):
   self.m.analyze_case(f.store,f.cid,list(f.ids.values()),replace(f.settings,max_request_bytes=10),f.quota,f.settings.principal,
    authorized_batch=f.batch['batch_sha256'],coverage_acknowledged=f.batch['required_ack'])
  call.assert_not_called();self.assertEqual(f.quota.budget_snapshot(f.settings,f.settings.principal)['daily_calls_remaining'],20)
 def test_missing_coverage_ack_no_call(self):
  f=self.f
  with patch('multidoc_ai.invoke') as call,self.assertRaises(old.MultiAIError):
   self.m.analyze_case(f.store,f.cid,list(f.ids.values()),f.settings,f.quota,f.settings.principal,
      authorized_batch=f.batch['batch_sha256'],coverage_acknowledged=[])
  call.assert_not_called()
 def test_exhausted_quota_blocks_second_call(self):
  from security import SecurityError
  f=self.f;f.settings=replace(f.settings,daily_limit=1,cooldown=0);self.run_ai()
  with patch('multidoc_ai.invoke') as call,self.assertRaises(SecurityError):
   self.m.analyze_case(f.store,f.cid,list(f.ids.values()),f.settings,f.quota,f.settings.principal,
     authorized_batch=f.batch['batch_sha256'],coverage_acknowledged=f.batch['required_ack'])
  call.assert_not_called()
 def test_legacy_receipt_may_not_carry_alias_fields(self):
  import workspace_bundle as w
  f=self.f;r=self.run_ai();old.import_case_analysis(f.store,f.cid,r)
  f.store._cases[f.cid].analysis_receipts[0]['schema_version']='multidoc-analysis/1.3'
  with self.assertRaises(w.WorkspaceError):w.export_workspace(f.store,f.cid)
 def test_import_is_idempotent_and_keeps_review(self):
  f=self.f;r=self.run_ai();old.import_case_analysis(f.store,f.cid,r)
  case=f.store.get_case(f.cid);f.store.confirm_fact(f.cid,case.facts[0].statement_id,'虚构复核员','仅模拟测试')
  before=f.store.export_json(f.cid);old.import_case_analysis(f.store,f.cid,r);self.assertEqual(f.store.export_json(f.cid),before)
 def test_zip_map_hash_tamper_refuses_atomically_after_manifest_rehash(self):
  import workspace_bundle as w
  import io,zipfile
  f=self.f;r=self.run_ai();old.import_case_analysis(f.store,f.cid,r)
  with zipfile.ZipFile(io.BytesIO(w.export_workspace(f.store,f.cid))) as z:members={n:z.read(n) for n in z.namelist()}
  data=json.loads(members['case.json']);data['analysis_receipts'][0]['pending_alias_map_sha256']='0'*64
  members['case.json']=w.encoded(data);manifest=json.loads(members['manifest.json'])
  for item in manifest['members']:
   if item['path']=='case.json':item.update(size=len(members['case.json']),sha256=hashlib.sha256(members['case.json']).hexdigest())
  members['manifest.json']=w.encoded(manifest);out=io.BytesIO()
  with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
   for name,value in members.items():z.writestr(name,value)
  target=CaseStore();cid=target.create_case('保留其他虚构案件');before=target.export_json(cid)
  with self.assertRaises(w.WorkspaceError):w.restore_workspace(target,out.getvalue())
  self.assertEqual(target.export_json(cid),before);self.assertNotIn(f.cid,target.list_cases())
 def test_b01_budget_artifact_is_reproducible(self):
  from tools.prepare_v14_b01 import report
  expected=json.loads((Path(__file__).resolve().parents[1]/'docs/V14_B01_BUDGET.json').read_text())
  self.assertEqual(report(),expected)
 def test_title_supported_edr_question_preserves_two_sources(self):
  p=self.payload();lookup={r['candidate_id']:r['alias'] for r in self.f.batch['alias_map']['entries']}
  item=self.f.item((fixtures.BODY,fixtures.TITLE),'待核实推断：EDR摘要原始数据是否需要核查？')
  p['pending_evidence']=[{'anchor_alias':lookup[item['anchor_id']],'evidence_aliases':[lookup[x] for x in item['evidence_ids']], 'reasoning':item['reasoning']}]
  self.assertEqual(len(self.run_ai(p)['pending_evidence'][0]['sources']),2)
 def test_unsupported_dssad_still_rejected(self):
  p=self.payload();p['pending_evidence'][0]['reasoning']='待核实推断：DSSAD是否记录事故？'
  self.rejected(p,'unsupported_data_term')
