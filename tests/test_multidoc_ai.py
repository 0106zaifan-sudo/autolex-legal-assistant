"""联合分析闭环的离线规格；所有响应均人工构造。"""
import io,json,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch,Mock
from dataclasses import replace
from case_store import CaseStore,CaseError
from security import Settings,QuotaStore,SecurityError
from test_case_store import document

HASH='pbkdf2_sha256$200000$'+'ab'*16+'$'+'cd'*32

class MultiAI(unittest.TestCase):
 def setUp(self):
  import multidoc_ai as m
  self.m=m;self.store=CaseStore();self.cid=self.store.create_case('模拟联合')
  self.ids=[]
  self.texts=['事件编号：SIM-BATCH；2026年11月1日08:30车辆发生碰撞。','事件编号：SIM-BATCH；2026年11月1日08:31车辆发生碰撞。']
  for i,t in enumerate(self.texts):self.ids.append(self.store.attach_document(self.cid,f'模拟{i}.docx',document(t,title=str(i))))
  self.settings=Settings(api_key='offline-not-real',password_hash=HASH,mode='local',single_instance=True,cooldown=1,provider='deepseek')
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.q=QuotaStore(Path(self.tmp.name)/'quota.sqlite3')
  self.batch=m.prepare_case(self.store,self.cid,self.ids,self.settings)
 def ref(self,i=0):
  s=self.batch['sources'][i];return {'source_id':s['source_id'],'quote':s['text']}
 def row(self,i=0,kind='事实'):
  return {'kind':kind,'text':self.ref(i)['quote'],'reasoning':'' if kind!='推断' else '待核实推断：碰撞时间是否需要核对？','sources':[self.ref(i)]}
 def payload(self):
  return {'schema_version':'multidoc-analysis/1.0','prompt_version':'multidoc/v1','case_id':self.cid,'batch_sha256':self.batch['batch_sha256'],
          'facts':[self.row(0),self.row(1)],'timeline':[],'pending_evidence':[],
          'relations':[{'left':self.ref(0),'right':self.ref(1),'relation_type':'inconsistency_candidate','reasoning':'待核实推断：两份碰撞时间记录的差异是否需要核对？'}]}
 def run_ai(self,payload=None,**opts):
  p=self.payload() if payload is None else payload
  response={'provider_status':'completed','provider_model':'offline-mock','provider_response_id':'offline-id','call_status':'response_received','refused':False,
            'token_usage':{'input_tokens':99,'output_tokens':22,'total_tokens':121},'output_text':json.dumps(p,ensure_ascii=False)}
  with patch('multidoc_ai.invoke',return_value=response) as call:
   result=self.m.analyze_case(self.store,self.cid,self.ids,self.settings,self.q,self.settings.principal,
       authorized_batch=opts.pop('authorized_batch',self.batch['batch_sha256']),client_factory=Mock(),**opts)
  return result,call
 def test_global_unique_sources(self):
  self.assertEqual(len({s['source_id'] for s in self.batch['sources']}),2)
  self.assertTrue(all(s['case_id']==self.cid and s['document_id'] in self.ids for s in self.batch['sources']))
 def test_once_request_and_quota(self):
  result,call=self.run_ai();call.assert_called_once();self.assertEqual(result['receipt']['execution_mode'],'injected_test_client')
  self.assertEqual(self.q.budget_snapshot(self.settings,self.settings.principal)['daily_calls_remaining'],19)
  self.assertEqual(len(self.store.get_case(self.cid).relations),0)
 def test_requires_batch_authorization(self):
  with patch('multidoc_ai.invoke') as call,self.assertRaises(ValueError):self.run_ai(authorized_batch=None)
  call.assert_not_called()
 def test_partial_selection_cannot_reuse_consent(self):
  other=self.store.attach_document(self.cid,'模拟第三.docx',document('模拟额外材料'))
  with self.assertRaises(ValueError):self.m.analyze_case(self.store,self.cid,[*self.ids,other],self.settings,self.q,self.settings.principal,authorized_batch=self.batch['batch_sha256'])
 def test_cross_case_batch_rejected(self):
  p=self.payload();p['case_id']=self.store.create_case('模拟另一案')
  with self.assertRaises(ValueError):self.run_ai(p)
 def test_foreign_source_rejected(self):
  p=self.payload();p['facts'][0]['sources'][0]['source_id']='S001'
  with self.assertRaises(ValueError):self.run_ai(p)
 def test_document_hash_change_blocked_before_model(self):
  self.store._cases[self.cid].documents[self.ids[0]].file_sha256='a'*64
  with patch('multidoc_ai.invoke') as call,self.assertRaises(ValueError):self.m.prepare_case(self.store,self.cid,self.ids,self.settings)
  call.assert_not_called()
 def test_missing_references_rejected(self):
  p=self.payload();p['facts'][0]['sources']=[]
  with self.assertRaises(ValueError):self.run_ai(p)
 def test_fabricated_quote_rejected(self):
  p=self.payload();p['relations'][0]['left']['quote']='虚构引用'
  with self.assertRaises(ValueError):self.run_ai(p)
 def test_failure_does_not_pollute_case_and_usage_kept(self):
  before=self.store.export_json(self.cid);p=self.payload();p['relations'][0]['left']['quote']='虚构引用'
  with self.assertRaises(self.m.MultiAIError) as error:self.run_ai(p)
  self.assertEqual(self.store.export_json(self.cid),before)
  self.assertEqual(error.exception.receipt['token_usage']['total_tokens'],121)
 def test_selected_count_limits(self):
  for ids in ([self.ids[0]],self.ids*3):
   with self.assertRaises(ValueError):self.m.prepare_case(self.store,self.cid,ids,self.settings)
 def test_quota_exhausted_blocks(self):
  s=replace(self.settings,daily_limit=1);lease=self.q.reserve_ai(s,s.principal);self.q.release(lease)
  with patch('multidoc_ai.invoke') as call,self.assertRaises(SecurityError):
   self.m.analyze_case(self.store,self.cid,self.ids,s,self.q,s.principal,authorized_batch=self.batch['batch_sha256'])
  call.assert_not_called()
 def test_failed_parse_blocks(self):
  d=self.store.attach_document(self.cid,'模拟损坏.pdf',b'bad')
  with self.assertRaises(ValueError):self.m.prepare_case(self.store,self.cid,[self.ids[0],d],self.settings)
 def test_coverage_ack_per_document(self):
  doc=self.store._cases[self.cid].documents[self.ids[0]];doc.parse_report['requires_acknowledgement']=True
  b=self.m.prepare_case(self.store,self.cid,self.ids,self.settings)
  with self.assertRaises(ValueError):self.m.analyze_case(self.store,self.cid,self.ids,self.settings,self.q,self.settings.principal,authorized_batch=b['batch_sha256'])
 def test_timeline_preserves_distinct_times(self):
  p=self.payload()
  for i,time in enumerate(('2026年11月1日08:30','2026年11月1日08:31')):
   ref=self.ref(i);ref['quote']=ref['quote'].split('；')[-1];row=self.row(i);row['text']=ref['quote'];row['sources']=[deepcopy(ref)]
   from ai_analysis import DATE_TIME
   row.update(event_source=deepcopy(ref),time_source=deepcopy(ref),time_state='explicit',time_precision='minute',time_text=DATE_TIME.search(ref['quote']).group());p['timeline'].append(row)
  result,_=self.run_ai(p);self.assertEqual(len(result['timeline']),2)
  self.assertEqual({r['normalized_time'] for r in result['timeline']},{'2026-11-01T08:30','2026-11-01T08:31'})
 def test_borrowed_time_rejected(self):
  p=self.payload();row=self.row();row.update(event_source=self.ref(),time_source=self.ref(1),time_state='explicit',time_precision='minute',time_text='2026年11月1日08:31');p['timeline']=[row]
  with self.assertRaises(ValueError):self.run_ai(p)
 def test_atomic_explicit_import_and_review_preserved(self):
  result,_=self.run_ai();self.m.import_case_analysis(self.store,self.cid,result)
  case=self.store.get_case(self.cid);self.assertEqual(len(case.relations),1)
  r=case.relations[0];self.store.review_relation(self.cid,r.relation_id,'needs_review','needs_verification','模拟审阅人','待核对时钟')
  self.m.import_case_analysis(self.store,self.cid,result)
  self.assertEqual(len(self.store.get_case(self.cid).relations),1);self.assertEqual(len(self.store.get_case(self.cid).relation_reviews),1)
 def test_tampered_import_rejected(self):
  result,_=self.run_ai();result['relations'][0]['left']['start']+=1;before=self.store.export_json(self.cid)
  with self.assertRaises(ValueError):self.m.import_case_analysis(self.store,self.cid,result)
  self.assertEqual(self.store.export_json(self.cid),before)
 def test_same_text_different_documents(self):
  self.store=CaseStore();self.cid=self.store.create_case('模拟相同文字');self.ids=[]
  for i in range(2):self.ids.append(self.store.attach_document(self.cid,f'模拟{i}.docx',document('模拟原始日志未提供。',title=str(i))))
  b=self.m.prepare_case(self.store,self.cid,self.ids,self.settings)
  self.assertEqual(b['sources'][0]['text'],b['sources'][1]['text']);self.assertNotEqual(b['sources'][0]['source_id'],b['sources'][1]['source_id'])
 def test_emit_receive_strong_conflict_rejected(self):
  self.store=CaseStore();self.cid=self.store.create_case('模拟提示区分');self.ids=[]
  for i,t in enumerate(('事件编号：A；驾驶人未收到接管提示。','事件编号：A；系统已发出接管提示。')):
   self.ids.append(self.store.attach_document(self.cid,f'模拟{i}.docx',document(t,title=str(i))))
  self.batch=self.m.prepare_case(self.store,self.cid,self.ids,self.settings)
  p=self.payload();p['facts']=[self.row(0,'主张'),self.row(1,'主张')]
  with self.assertRaises(self.m.MultiAIError) as error:self.run_ai(p)
  self.assertEqual(error.exception.receipt['evidence_status'],'passed')
  self.assertEqual(error.exception.receipt['semantic_status'],'rejected_by_conservative_policy')
 def test_related_emit_receive_is_candidate(self):
  self.store=CaseStore();self.cid=self.store.create_case('模拟提示关联');self.ids=[]
  for i,t in enumerate(('事件编号：A；驾驶人未收到接管提示。','事件编号：A；系统已发出接管提示。')):
   self.ids.append(self.store.attach_document(self.cid,f'模拟{i}.docx',document(t,title=str(i))))
  self.batch=self.m.prepare_case(self.store,self.cid,self.ids,self.settings)
  p=self.payload();p['facts']=[self.row(0,'主张'),self.row(1,'主张')];p['relations'][0]['relation_type']='related'
  result,_=self.run_ai(p);self.assertEqual(result['relations'][0]['status'],'candidate')
 def test_missing_secret_or_login_blocks_before_request(self):
  for s,principal in ((replace(self.settings,api_key=''),self.settings.principal),(self.settings,None)):
   with patch('multidoc_ai.invoke') as call,self.assertRaises(ValueError):
    self.m.analyze_case(self.store,self.cid,self.ids,s,self.q,principal,authorized_batch=self.batch['batch_sha256'])
   call.assert_not_called()
 def test_provider_change_invalidates_batch_consent(self):
  s=replace(self.settings,provider='openai',model='gpt-4.1-mini')
  with self.assertRaises(ValueError):self.m.analyze_case(self.store,self.cid,self.ids,s,self.q,s.principal,authorized_batch=self.batch['batch_sha256'])
 def test_sources_do_not_expose_local_ids_to_model(self):
  request,_=self.m.request_for(self.batch,self.settings)
  sources=json.loads(request['input'])['sources']
  self.assertTrue(all(s['source_id'].startswith('MD_') and 'local_id' not in s for s in sources))
 def test_request_byte_limit_blocks(self):
  with self.assertRaises(ValueError):self.m.request_for(self.batch,replace(self.settings,max_request_bytes=10))
 def test_per_document_input_limit_blocks(self):
  d=self.store.attach_document(self.cid,'模拟超限.docx',document('甲'*8001))
  with self.assertRaises(ValueError):self.m.prepare_case(self.store,self.cid,[d,self.ids[0]],self.settings)
 def test_total_input_limit_blocks(self):
  ids=[self.store.attach_document(self.cid,f'模拟大{i}.docx',document('甲'*6000,title=str(i))) for i in range(3)]
  with self.assertRaises(ValueError):self.m.prepare_case(self.store,self.cid,ids,self.settings)
 def test_exact_duplicate_relations_not_imported_twice(self):
  p=self.payload();p['relations']*=2
  result,_=self.run_ai(p);self.m.import_case_analysis(self.store,self.cid,result)
  self.assertEqual(len(self.store.get_case(self.cid).relations),1)
 def test_overlapping_quotes_merge_only_same_question_preserving_origins(self):
  p=self.payload();second=deepcopy(p['relations'][0])
  for side in ('left','right'):second[side]['quote']=second[side]['quote'].rstrip('。')
  p['relations'].append(second);result,_=self.run_ai(p);self.m.import_case_analysis(self.store,self.cid,result)
  case=self.store.get_case(self.cid);self.assertEqual(len(case.relations),1);self.assertEqual(len(case.relations[0].ai_origins),2)
 def test_distinct_questions_not_merged(self):
  p=self.payload();second=deepcopy(p['relations'][0]);second['reasoning']='待核实推断：两份碰撞记录的事件编号是否对应同一事件？';p['relations'].append(second)
  result,_=self.run_ai(p);self.m.import_case_analysis(self.store,self.cid,result)
  self.assertEqual(len(self.store.get_case(self.cid).relations),2)
 def test_cross_document_unknown_time_kept_with_specific_question(self):
  self.store=CaseStore();self.cid=self.store.create_case('模拟未知');self.ids=[]
  for i,t in enumerate(('模拟现场记录：车辆发生碰撞，原文未记载日期和时刻。','模拟材料接收：2026年11月4日收到车辆检查材料。')):
   self.ids.append(self.store.attach_document(self.cid,f'模拟未知{i}.docx',document(t,title=str(i))))
  self.batch=self.m.prepare_case(self.store,self.cid,self.ids,self.settings)
  p=self.payload();p['relations']=[]
  index=next(i for i,s in enumerate(self.batch['sources']) if '发生碰撞' in s['text'])
  row=self.row(index);row.update(event_source=self.ref(index),time_source=None,time_state='unknown',time_precision='unknown',time_text='未知');p['timeline']=[row]
  question=self.row(index,'推断');question['reasoning']='待核实推断：碰撞具体时间有无其他材料记载？';p['pending_evidence']=[question]
  result,_=self.run_ai(p)
  self.assertEqual(result['timeline'][0]['time_source'],None)
  self.assertFalse(any(d['rule']=='unknown_event_time_question_missing' for v in result['completeness_diagnostics'].values() for d in v['diagnostics']))
 def test_cross_document_question_all_sources_must_validate(self):
  p=self.payload();question=self.row(0,'推断');question['sources'].append(self.ref(1));p['pending_evidence']=[question]
  result,_=self.run_ai(p);self.assertEqual(len(result['pending_evidence'][0]['sources']),2)
 def test_missing_edr_cannot_be_invented_in_question(self):
  p=self.payload();q=self.row(0,'推断');q['reasoning']='待核实推断：EDR是否记录车辆状态？';p['pending_evidence']=[q]
  with self.assertRaises(ValueError):self.run_ai(p)
 def test_unsupported_date_in_question_rejected(self):
  p=self.payload();q=self.row(0,'推断');q['reasoning']='待核实推断：2027年1月1日是否发生碰撞？';p['pending_evidence']=[q]
  with self.assertRaises(ValueError):self.run_ai(p)
 def test_precision_difference_not_asserted_conflict(self):
  self.store=CaseStore();self.cid=self.store.create_case('模拟精度');self.ids=[]
  for i,t in enumerate(('事件编号：A；2026年11月1日车辆发生碰撞。','事件编号：A；2026年11月1日08:30车辆发生碰撞。')):
   self.ids.append(self.store.attach_document(self.cid,f'模拟精度{i}.docx',document(t,title=str(i))))
  self.batch=self.m.prepare_case(self.store,self.cid,self.ids,self.settings)
  with self.assertRaises(ValueError):self.run_ai()
  p=self.payload();p['relations'][0]['relation_type']='needs_verification'
  import time
  with patch('security.time.time',return_value=time.time()+2):
   self.assertEqual(self.run_ai(p)[0]['semantic_status'],'pending_human_review')
 def test_stale_analysis_not_imported_after_document_change(self):
  result,_=self.run_ai();self.store._cases[self.cid].documents[self.ids[0]].units[0]['text']='模拟变化'
  with self.assertRaises(ValueError):self.m.import_case_analysis(self.store,self.cid,result)
 def test_facts_inference_not_silently_reclassified(self):
  p=self.payload();p['facts'][0]=self.row(0,'推断')
  with self.assertRaises(ValueError):self.run_ai(p)
 def test_four_archived_public_samples_one_batch(self):
  self.store=CaseStore();self.cid=self.store.create_case('模拟四文件')
  root=Path(__file__).resolve().parents[1]/'samples_multidoc'
  self.ids=[self.store.attach_document(self.cid,p.name,p.read_bytes()) for p in sorted(root.iterdir())]
  b=self.m.prepare_case(self.store,self.cid,self.ids,self.settings);self.batch=b
  p=self.payload();p.update(facts=[],relations=[])
  result,_=self.run_ai(p,coverage_acknowledged=b['required_ack'])
  self.assertEqual(len(result['documents']),4)
 def test_incomplete_provider_status_keeps_usage(self):
  response={'provider_status':'incomplete','token_usage':{'input_tokens':8},'call_status':'response_received'}
  with patch('multidoc_ai.invoke',return_value=response),self.assertRaises(self.m.MultiAIError) as error:
   self.m.analyze_case(self.store,self.cid,self.ids,self.settings,self.q,self.settings.principal,authorized_batch=self.batch['batch_sha256'],client_factory=Mock())
  self.assertEqual(error.exception.receipt['token_usage']['input_tokens'],8)
 def test_real_sdk_offline_http_both_providers(self):
  import httpx
  from openai import OpenAI
  for provider in ('openai','deepseek'):
   settings=replace(self.settings,provider=provider,model='offline-model')
   batch=self.m.prepare_case(self.store,self.cid,self.ids,settings);p=self.payload();p['batch_sha256']=batch['batch_sha256']
   calls=[]
   def handler(request):
    calls.append(request)
    return httpx.Response(200,json={'id':'offline-only','object':'response','created_at':1,'model':'offline-mock','status':'completed',
       'usage':{'input_tokens':100,'output_tokens':30,'total_tokens':130},'output':[{'id':'msg-offline','type':'message','role':'assistant','status':'completed',
       'content':[{'type':'output_text','text':json.dumps(p,ensure_ascii=False),'annotations':[]}]}]})
   def factory(**kwargs):return OpenAI(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
   q=QuotaStore(Path(self.tmp.name)/(provider+'.sqlite3'))
   result=self.m.analyze_case(self.store,self.cid,self.ids,settings,q,settings.principal,authorized_batch=batch['batch_sha256'],client_factory=factory)
   self.assertEqual(len(calls),1);self.assertEqual(calls[0].url.host,'api.openai.com' if provider=='openai' else 'api.deepseek.com')
   body=json.loads(calls[0].content);self.assertEqual(body['text']['format']['type'],'json_schema')
   self.assertEqual(result['receipt']['token_usage']['total_tokens'],130)
   self.assertNotIn(settings.api_key,json.dumps(result,ensure_ascii=False))
 def test_joint_import_schema_is_explicit_and_not_downgraded(self):
  result,_=self.run_ai();self.m.import_case_analysis(self.store,self.cid,result)
  self.assertEqual(self.store.get_case(self.cid).schema_version,'1.2')
  case=self.store.get_case(self.cid);r=case.relations[0]
  # 既有离线候选入口不能将新审计案件降回1.1。
  self.store.link_evidence(self.cid,r.left_id,r.right_id)
  self.assertEqual(self.store.get_case(self.cid).schema_version,'1.2')
 def test_legacy_relation_export_has_no_new_empty_fields(self):
  e=[]
  for did in self.ids:
   t=self.store.get_case(self.cid).documents[did].units[0]['text'];e.append(self.store.add_evidence(self.cid,did,0,0,len(t),t))
  self.store.link_evidence(self.cid,*e)
  value=json.loads(self.store.export_json(self.cid))
  self.assertEqual(value['schema_version'],'1.1');self.assertNotIn('ai_origins',value['relations'][0])
 def test_source_collision_rejected(self):
  batch=deepcopy(self.batch);batch['sources'][1]['source_id']=batch['sources'][0]['source_id']
  with self.assertRaises(ValueError):self.m.validate_case_output(self.store,self.cid,batch,self.payload())
 def test_transport_deadline_uses_original_bounded_runtime(self):
  from model_runtime import ModelRuntimeError
  with patch('multidoc_ai.invoke',side_effect=ModelRuntimeError('deadline_exceeded')) as invoke,self.assertRaises(self.m.MultiAIError) as err:
   self.m.analyze_case(self.store,self.cid,self.ids,self.settings,self.q,self.settings.principal,authorized_batch=self.batch['batch_sha256'])
  self.assertEqual(invoke.call_args.args[2],45);self.assertIsNone(invoke.call_args.args[3])
  self.assertEqual(err.exception.receipt['error_code'],'deadline_exceeded')
  self.assertEqual(self.q.budget_snapshot(self.settings,self.settings.principal)['daily_calls_remaining'],19)
 def test_http_error_code_kept_without_provider_body(self):
  with patch('multidoc_ai.invoke',return_value={'error_code':'authentication_failed','http_status':401,'call_status':'http_error'}),self.assertRaises(self.m.MultiAIError) as err:
   self.m.analyze_case(self.store,self.cid,self.ids,self.settings,self.q,self.settings.principal,authorized_batch=self.batch['batch_sha256'])
  self.assertEqual(err.exception.receipt['error_code'],'authentication_failed')
  self.assertEqual(err.exception.receipt['http_status'],401);self.assertIsNone(err.exception.receipt['billing']['amount'])
 def test_partial_document_acknowledged_allows_only_that_batch(self):
  self.store._cases[self.cid].documents[self.ids[0]].parse_report['requires_acknowledgement']=True
  self.batch=self.m.prepare_case(self.store,self.cid,self.ids,self.settings)
  result,_=self.run_ai(coverage_acknowledged=[self.ids[0]])
  self.assertEqual(result['receipt']['evidence_status'],'passed')
 def test_import_fail_late_is_atomic(self):
  result,_=self.run_ai();before=self.store.export_json(self.cid)
  with patch.object(CaseStore,'import_analysis',side_effect=[None,ValueError('simulated failure')]),self.assertRaises(ValueError):
   self.m.import_case_analysis(self.store,self.cid,result)
  self.assertEqual(self.store.export_json(self.cid),before)
 def test_import_export_no_original_bytes_or_credentials(self):
  result,_=self.run_ai();self.m.import_case_analysis(self.store,self.cid,result)
  exported=json.loads(self.store.export_json(self.cid))
  self.assertTrue(all('original_bytes' not in doc for doc in exported['documents'].values()))
  self.assertNotIn(self.settings.api_key,json.dumps(exported,ensure_ascii=False))
  self.assertTrue(exported['relations'][0]['ai_origins'])
 def test_source_collision_blocks_before_model_reservation(self):
  with patch('multidoc_ai.digest',return_value='a'*64),patch('multidoc_ai.invoke') as call,self.assertRaises(ValueError):
   self.m.prepare_case(self.store,self.cid,self.ids,self.settings)
  call.assert_not_called()
 def test_receipt_export_allowlist_and_idempotent_import(self):
  result,_=self.run_ai();result['receipt']['Authorization']='FAKE_AUTH_NOT_FOR_EXPORT'
  self.m.import_case_analysis(self.store,self.cid,result);self.m.import_case_analysis(self.store,self.cid,result)
  value=json.loads(self.store.export_json(self.cid))
  self.assertEqual(len(value['analysis_receipts']),1)
  self.assertEqual(value['analysis_receipts'][0]['token_usage']['total_tokens'],121)
  self.assertNotIn('FAKE_AUTH_NOT_FOR_EXPORT',json.dumps(value))
 def test_exposed_fact_sources_are_global(self):
  result,_=self.run_ai();ids={s['source_id'] for s in result['source_manifest']}
  self.assertTrue(all(ref['source_id'] in ids for row in result['facts'] for ref in row['sources']))
 def test_different_times_have_non_authoritative_cross_document_warning(self):
  p=self.payload();p['relations']=[]
  from ai_analysis import DATE_TIME
  for i in range(2):
   ref=self.ref(i);ref['quote']=ref['quote'].split('；')[-1]
   row=self.row(i);row.update(text=ref['quote'],sources=[deepcopy(ref)],event_source=deepcopy(ref),time_source=deepcopy(ref),
         time_state='explicit',time_precision='minute',time_text=DATE_TIME.search(ref['quote']).group());p['timeline'].append(row)
  result,_=self.run_ai(p)
  self.assertEqual(len(result['timeline']),2);self.assertEqual(len(result['cross_document_diagnostics']),1)
  self.assertEqual(result['cross_document_diagnostics'][0]['status'],'needs_review')
 def test_document_id_mismatch_rejected_preflight(self):
  self.store._cases[self.cid].documents[self.ids[0]].document_id='foreign-document-id'
  with self.assertRaises(ValueError):self.m.prepare_case(self.store,self.cid,self.ids,self.settings)
