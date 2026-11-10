"""1.2格式失败安全定位；官方SDK+本地HTTP Mock，均非真实失败响应。"""
from copy import deepcopy
import json,unittest
from unittest.mock import patch
import httpx
from openai import OpenAI
from pydantic import BaseModel,field_validator,ValidationError
from pydantic_core import PydanticCustomError
import multidoc_ai as old
from validation_diagnostics import schema_diagnostic
import test_v2e_integration as fixtures

SENSITIVE='虚构隐私原文-不能输出到回执'

class SchemaDiagnostics12(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.V2E();self.f.setUp();self.addCleanup(self.f.tmp.cleanup)
 def run_invalid(self,output,*,blocks=None,expected='schema_rejected'):
  f=self.f;calls=[]
  text=json.dumps(output,ensure_ascii=False) if not isinstance(output,str) else output
  if blocks is None:blocks=[text]
  def handler(req):
   calls.append(json.loads(req.content))
   return httpx.Response(200,json={'id':'mock-format','object':'response','created_at':1,'model':'offline-format','status':'completed',
    'usage':{'input_tokens':100,'output_tokens':30,'total_tokens':130},'output':[{'id':'msg','type':'message','role':'assistant','status':'completed',
    'content':[{'type':'output_text','text':s,'annotations':[]} for s in blocks]}]})
  def factory(**kw):
   self.assertEqual(kw['max_retries'],0);return OpenAI(**kw,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
  before=f.store.export_json(f.cid)
  with self.assertRaises(old.MultiAIError) as caught:
   f.m.analyze_case(f.store,f.cid,list(f.ids.values()),f.settings,f.quota,f.settings.principal,
    authorized_batch=f.batch['batch_sha256'],coverage_acknowledged=f.batch['required_ack'],client_factory=factory)
  receipt=caught.exception.receipt;d=receipt['validation_diagnostic']
  self.assertEqual(d['rule'],expected);self.assertEqual(d['stage'],'format')
  self.assertEqual(receipt['format_status'],'failed_or_unavailable');self.assertEqual(receipt['evidence_status'],'not_run')
  self.assertEqual(receipt['provider_status'],'completed');self.assertEqual(receipt['token_usage']['total_tokens'],130)
  self.assertEqual(len(calls),1);self.assertEqual(f.store.export_json(f.cid),before)
  self.assertEqual(f.quota.budget_snapshot(f.settings,f.settings.principal)['daily_calls_remaining'],19)
  self.assertNotIn(SENSITIVE,json.dumps(receipt,ensure_ascii=False))
  return d
 def error(self,d,kind,path):
  matches=[e for e in d['schema_errors'] if e['type']==kind and e['path']==path]
  self.assertTrue(matches,(kind,path,d));return matches[0]
 def test_invalid_json(self):
  d=self.run_invalid('{"private":"'+SENSITIVE+'",')
  self.assertEqual(self.error(d,'json_invalid',[])['category'],'json_parse')
  self.assertEqual(d['schema_error_count'],1);self.assertIsNone(d['section'])
 def test_empty_sdk_text(self):
  d=self.run_invalid('',blocks=[]);self.error(d,'json_invalid',[])
 def test_markdown_fence_is_not_stripped(self):
  d=self.run_invalid('```json\n'+json.dumps(self.f.payload())+'\n```');self.error(d,'json_invalid',[])
 def test_json_array_root(self):
  d=self.run_invalid([]);self.error(d,'model_type',[])
 def test_json_null_root(self):
  d=self.run_invalid(None);self.error(d,'model_type',[])
 def test_missing_pending_catalog_hash_is_located(self):
  p=self.f.payload();p.pop('pending_catalog_sha256');d=self.run_invalid(p)
  self.assertEqual(self.error(d,'missing',['pending_catalog_sha256'])['category'],'missing_field')
  self.assertIsNone(d['section'])
 def test_missing_root_case_id(self):
  p=self.f.payload();p.pop('case_id');d=self.run_invalid(p);self.error(d,'missing',['case_id'])
 def test_wrong_schema_version(self):
  p=self.f.payload();p['schema_version']=SENSITIVE;d=self.run_invalid(p)
  self.assertEqual(self.error(d,'literal_error',['schema_version'])['category'],'version_mismatch')
 def test_wrong_prompt_version(self):
  p=self.f.payload();p['prompt_version']='multidoc/candidates-v1';d=self.run_invalid(p)
  self.assertEqual(self.error(d,'literal_error',['prompt_version'])['category'],'version_mismatch')
 def test_wrong_root_list_type(self):
  p=self.f.payload();p['facts']={'private':SENSITIVE};d=self.run_invalid(p)
  self.assertEqual(self.error(d,'list_type',['facts'])['category'],'field_type')
 def test_wrong_anchor_field_type(self):
  p=self.f.payload();p['pending_evidence'][0]['anchor_id']=123;d=self.run_invalid(p)
  self.error(d,'string_type',['pending_evidence',0,'anchor_id'])
  self.assertEqual((d['section'],d['item_index']),('pending_evidence',0))
 def test_missing_nested_reasoning(self):
  p=self.f.payload();p['pending_evidence'][0].pop('reasoning');d=self.run_invalid(p)
  self.error(d,'missing',['pending_evidence',0,'reasoning'])
 def test_version_mismatch_is_not_used_for_wrong_kind(self):
  p=self.f.payload();p['facts'][0]['kind']=SENSITIVE;d=self.run_invalid(p)
  self.assertEqual(self.error(d,'literal_error',['facts',0,'kind'])['category'],'literal_value')
 def test_hash_pattern_constraint(self):
  p=self.f.payload();p['pending_catalog_sha256']=SENSITIVE;d=self.run_invalid(p)
  self.assertEqual(self.error(d,'string_pattern_mismatch',['pending_catalog_sha256'])['category'],'value_constraint')
 def test_free_pending_text_is_extra_field(self):
  p=self.f.payload();p['pending_evidence'][0]['text']=SENSITIVE;d=self.run_invalid(p)
  self.assertEqual(self.error(d,'extra_forbidden',['pending_evidence',0,'text'])['category'],'extra_field')
 def test_unknown_root_key_is_redacted(self):
  p=self.f.payload();p[SENSITIVE]=SENSITIVE;d=self.run_invalid(p)
  self.assertTrue(self.error(d,'extra_forbidden',['<redacted>'])['path_redacted'])
 def test_unknown_nested_reference_key_is_redacted(self):
  p=self.f.payload();p['facts'][0]['sources'][0][SENSITIVE]=SENSITIVE;d=self.run_invalid(p)
  self.error(d,'extra_forbidden',['facts',0,'sources',0,'<redacted>'])
 def test_known_word_in_wrong_root_position_is_redacted(self):
  p=self.f.payload();p['quote']=SENSITIVE;d=self.run_invalid(p)
  self.error(d,'extra_forbidden',['<redacted>'])
 def test_multiple_errors_have_total_and_summary(self):
  p=self.f.payload();p.pop('pending_catalog_sha256');p['schema_version']='invalid';p['facts']='invalid'
  d=self.run_invalid(p)
  self.assertEqual(d['schema_error_count'],3)
  self.assertEqual(d['schema_error_type_counts'],{'missing':1,'literal_error':1,'list_type':1})
  self.assertFalse(d['schema_errors_truncated'])
 def test_many_errors_are_bounded_but_total_is_not_hidden(self):
  p=self.f.payload()
  for i in range(60):p[SENSITIVE+str(i)]='value'
  d=self.run_invalid(p);self.assertEqual(d['schema_error_count'],60)
  self.assertEqual(len(d['schema_errors']),20);self.assertTrue(d['schema_errors_truncated'])
  self.assertEqual(d['schema_error_type_counts'],{'extra_forbidden':60})
 def test_nested_error_index_and_path(self):
  p=self.f.payload();p['pending_evidence'][0]['evidence_ids'][0]=None
  d=self.run_invalid(p);self.error(d,'string_type',['pending_evidence',0,'evidence_ids',0])
 def test_multiple_complete_text_objects_not_auto_selected(self):
  t=json.dumps(self.f.payload(),ensure_ascii=False);d=self.run_invalid('',blocks=[t,t])
  self.error(d,'json_invalid',[])
 def test_fragmented_single_json_is_preserved_by_sdk(self):
  f=self.f;text=json.dumps(f.payload(),ensure_ascii=False);parts=[text[:len(text)//2],text[len(text)//2:]];calls=[]
  def handler(req):
   calls.append(req)
   return httpx.Response(200,json={'id':'mock-fragments','object':'response','created_at':1,'model':'offline','status':'completed',
    'usage':{'total_tokens':130},'output':[{'id':'msg','type':'message','role':'assistant','status':'completed',
    'content':[{'type':'output_text','text':t,'annotations':[]} for t in parts]}]})
  def factory(**kw):return OpenAI(**kw,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
  result=f.m.analyze_case(f.store,f.cid,list(f.ids.values()),f.settings,f.quota,f.settings.principal,
    authorized_batch=f.batch['batch_sha256'],coverage_acknowledged=f.batch['required_ack'],client_factory=factory)
  self.assertEqual(len(calls),1);self.assertEqual(result['receipt']['evidence_status'],'passed')
  self.assertFalse(f.store.get_case(f.cid).inferences)
 def test_no_error_message_or_context_is_serialized(self):
  p=self.f.payload();p['facts'][0]['reasoning']=SENSITIVE;d=self.run_invalid(p)
  self.error(d,'string_too_long',['facts',0,'reasoning'])
  for row in d['schema_errors']:
   self.assertEqual(set(row),{'type','category','path','path_redacted'})
 def test_unknown_custom_error_type_is_redacted(self):
  class Custom(BaseModel):
   case_id:str
   @field_validator('case_id')
   @classmethod
   def reject(cls,value):raise PydanticCustomError(SENSITIVE,'秘密消息 {value}',{'value':value})
  try:Custom(case_id=SENSITIVE)
  except ValidationError as error:d=schema_diagnostic(error,{'stage':'format'},{})
  self.assertEqual(d['schema_errors'][0]['type'],'other_validation_error')
  self.assertNotIn(SENSITIVE,json.dumps(d,ensure_ascii=False))
 def test_unknown_path_suffix_stops_at_first_redaction(self):
  # 人工Pydantic异常用于验证策略，不是某次模型响应。
  error=ValidationError.from_exception_data('Test',[{'type':'missing','loc':('pending_evidence',0,SENSITIVE,'quote'),'input':SENSITIVE}])
  d=schema_diagnostic(error,{'stage':'format'},{})
  self.error(d,'missing',['pending_evidence',0,'<redacted>'])
 def test_oversized_index_is_not_echoed(self):
  error=ValidationError.from_exception_data('Test',[{'type':'missing','loc':('facts',12345678901,'reasoning'),'input':SENSITIVE}])
  d=schema_diagnostic(error,{'stage':'format'},{})
  self.assertNotIn('12345678901',json.dumps(d));self.assertTrue(d['schema_errors'][0]['path_redacted'])
 def test_diagnostic_schema_has_independent_version(self):
  f=self.f;p=f.payload();p.pop('case_id')
  d=self.run_invalid(p);self.assertEqual(d['schema_error_version'],'schema-errors/v1')
 def test_legacy_10_missing_root_field_keeps_original_rule(self):
  p=self.f.payload();p.pop('case_id');p.pop('pending_catalog_sha256');p['schema_version']='multidoc-analysis/1.0';p['prompt_version']='multidoc/v1'
  p['pending_evidence']=[];p['timeline']=[]
  try:old.MultiAnalysis.model_validate(p)
  except ValidationError as error:d=schema_diagnostic(error,{'stage':'format'},self.f.batch,p)
  self.assertEqual(d['rule'],'schema_rejected');self.error(d,'missing',['case_id'])
 def test_document_parser_version_is_classified_as_version_mismatch(self):
  from ai_analysis import Analysis
  record=next(iter(self.f.batch['records'].values()));raw=old.empty_analysis(record);raw['parser_version']='unsupported'
  try:Analysis.model_validate(raw)
  except ValidationError as error:d=schema_diagnostic(error,{'stage':'document_binding'},{})
  self.assertEqual(self.error(d,'literal_error',['parser_version'])['category'],'version_mismatch')
  self.assertEqual(d['stage'],'document_format')
