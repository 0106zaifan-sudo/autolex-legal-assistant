"""所有样本为合成回执/固定虚构工作包，不代表用户第六次真实核验。"""
from copy import deepcopy
import contextlib,hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from case_store import CaseStore
from security import Settings
import multidoc_v13 as m
import workspace_bundle as w
from tools.audit_v13_receipt_exact import verify_store,verify_files,main

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'datasets/CASE-001/standard'

class ExactAudit(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.store=CaseStore();self.cid=self.store.create_case('完全虚构精确核对测试');self.ids=[]
  for d in json.loads((DATA/'manifest.json').read_text())['documents']:
   if d['material_id'] in ('D01','D02','D03','D04'):
    p=DATA/d['path'];self.ids.append(self.store.attach_document(self.cid,p.name,p.read_bytes()))
  b=m.prepare_case(self.store,self.cid,self.ids,Settings(provider='deepseek'));self.batch=b
  self.chosen=(b['pending_catalog']['entries'][0]['candidate_id'],'PE_'+'f'*24,b['pending_catalog']['entries'][-1]['candidate_id'])
  self.receipt={'case_id':self.cid,'protocol':'responses','provider':'deepseek','requested_model':'deepseek-flash',
    'schema_version':m.SCHEMA_VERSION,'prompt_version':m.PROMPT_VERSION,'prompt_sha256':hashlib.sha256(m.PROMPT.encode()).hexdigest(),
    'pending_catalog_version':m.CATALOG_VERSION,'batch_sha256':b['batch_sha256'],'pending_catalog_sha256':b['pending_catalog']['sha256'],
    'document_snapshots':[{k:d[k] for k in ('document_id','file_sha256','parsed_text_sha256','parser_version')} for d in b['documents']],
    'provider_status':'completed','call_status':'response_received','format_status':'passed','evidence_status':'failed',
    'validation_diagnostic':{'stage':'pending_selection','rule':'pending_candidate_not_in_catalog','section':'pending_evidence','item_index':8,'candidate_ids':list(self.chosen)}}
 def run_audit(self,r=None):return verify_store(self.receipt if r is None else r,self.store,expected_ids=self.chosen)
 def blocked(self,r,check):
  result=self.run_audit(r);self.assertFalse(result['comparison_performed']);self.assertEqual(result['checks'][check],'mismatch')
  self.assertTrue(all(x['status']=='not_compared' for x in result['membership']));return result
 def test_all_gates_match_before_exact_mixed_membership(self):
  before=self.store.export_json(self.cid);result=self.run_audit()
  self.assertTrue(result['comparison_performed']);self.assertEqual([x['status'] for x in result['membership']],['in_catalog','not_in_catalog','in_catalog'])
  self.assertEqual(self.store.export_json(self.cid),before)
 def test_case_id_mismatch_stops(self):
  r=deepcopy(self.receipt);r['case_id']='case_'+'0'*32;self.blocked(r,'case_id')
 def test_file_sha_mismatch_stops(self):
  r=deepcopy(self.receipt);r['document_snapshots'][0]['file_sha256']='0'*64;self.blocked(r,'four_b01_snapshots')
 def test_parsed_sha_mismatch_stops(self):
  r=deepcopy(self.receipt);r['document_snapshots'][0]['parsed_text_sha256']='0'*64;self.blocked(r,'four_b01_snapshots')
 def test_parser_version_mismatch_stops(self):
  r=deepcopy(self.receipt);r['document_snapshots'][0]['parser_version']='unknown';self.blocked(r,'four_b01_snapshots')
 def test_original_bytes_corrupt_stops(self):
  self.store._cases[self.cid].documents[self.ids[0]].original_bytes+=b'bad';self.blocked(self.receipt,'original_and_parsed_bytes')
 def test_protocol_version_mismatch_stops(self):
  r=deepcopy(self.receipt);r['schema_version']='multidoc-analysis/1.2';self.blocked(r,'protocol')
 def test_prompt_hash_mismatch_stops_before_prepare(self):
  r=deepcopy(self.receipt);r['prompt_sha256']='0'*64
  with patch('multidoc_v13.prepare_case',side_effect=AssertionError('must stop')):self.blocked(r,'prompt_hash')
 def test_batch_sha_mismatch_stops(self):
  r=deepcopy(self.receipt);r['batch_sha256']='0'*64;self.blocked(r,'batch_sha256')
 def test_catalog_sha_mismatch_stops(self):
  r=deepcopy(self.receipt);r['pending_catalog_sha256']='0'*64;self.blocked(r,'pending_catalog_sha256')
 def test_wrong_receipt_target_stops(self):
  r=deepcopy(self.receipt);r['validation_diagnostic']['item_index']=0;self.blocked(r,'receipt_valid')
 def test_missing_receipt_never_restores_or_creates_fixture_case(self):
  with patch('tools.audit_v13_receipt_exact.restore_workspace',side_effect=AssertionError('do not read archive')):
   result=verify_files(Path(self.tmp.name)/'missing.json',Path(self.tmp.name)/'missing.zip')
  self.assertEqual(result['stop_reason'],'receipt_unavailable');self.assertFalse(result['comparison_performed'])
 def write_inputs(self):
  r=Path(self.tmp.name)/'synthetic-receipt.json';z=Path(self.tmp.name)/'synthetic-workspace.zip'
  r.write_text(json.dumps(self.receipt,ensure_ascii=False));z.write_bytes(w.export_workspace(self.store,self.cid))
  return r,z
 def test_user_archive_path_reads_only_no_sdk_secrets_or_quota(self):
  r,z=self.write_inputs();before=(r.read_bytes(),z.read_bytes())
  with patch('multidoc_ai.invoke',side_effect=AssertionError('no model')),patch('security.QuotaStore',side_effect=AssertionError('no quota')),patch('security.Settings.from_secrets',side_effect=AssertionError('no Secrets')):
   result=verify_files(r,z,expected_ids=self.chosen)
  self.assertTrue(result['comparison_performed']);self.assertEqual((r.read_bytes(),z.read_bytes()),before)
  output=json.dumps(result,ensure_ascii=False)
  for sensitive in ('事故时间栏目','原始二进制',self.cid,self.receipt['batch_sha256']):self.assertNotIn(sensitive,output)
 def test_corrupt_zip_never_compares(self):
  r,z=self.write_inputs();z.write_bytes(b'not a ZIP')
  result=verify_files(r,z,expected_ids=self.chosen);self.assertEqual(result['stop_reason'],'workspace_validation_failed');self.assertFalse(result['comparison_performed'])
 def test_duplicate_json_key_rejected(self):
  r,z=self.write_inputs();r.write_text('{"case_id":"a","case_id":"b"}')
  result=verify_files(r,z,expected_ids=self.chosen);self.assertEqual(result['stop_reason'],'receipt_invalid')
 def test_output_cannot_overwrite_input(self):
  r,z=self.write_inputs();before=r.read_bytes()
  with contextlib.redirect_stdout(io.StringIO()):code=main(['--receipt',str(r),'--workspace',str(z),'--output',str(r)])
  self.assertEqual(code,2);self.assertEqual(r.read_bytes(),before)
 def test_unrelated_fourth_material_missing_refuses(self):
  r=deepcopy(self.receipt);r['document_snapshots']=r['document_snapshots'][:3];self.blocked(r,'four_b01_snapshots')
 def test_existing_output_is_not_overwritten(self):
  r,z=self.write_inputs();report=Path(self.tmp.name)/'keep.json';report.write_text('keep existing data')
  with contextlib.redirect_stdout(io.StringIO()):code=main(['--receipt',str(r),'--workspace',str(z),'--output',str(report)])
  self.assertEqual(code,2);self.assertEqual(report.read_text(),'keep existing data')
 def test_other_cases_in_same_store_are_not_used_or_modified(self):
  other=self.store.create_case('其他虚构案件');before=self.store.export_json(other)
  result=self.run_audit();self.assertTrue(result['comparison_performed'])
  self.assertEqual(self.store.export_json(other),before)
