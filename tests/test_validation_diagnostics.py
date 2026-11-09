"""只用人工模拟响应定位失败；不读取真实失败输出。"""
import json
from copy import deepcopy
from unittest.mock import patch,Mock
import test_multidoc_ai as fixtures

# 仅复用初始化/人工数据帮助方法，不继承其测试，以免重复统计。
import unittest
class DiagnosticTests(unittest.TestCase):
 def setUp(self):
  self.base=fixtures.MultiAI();self.base.setUp();self.addCleanup(self.base.tmp.cleanup)
 def diagnostic(self,payload):
  b=self.base;before=b.store.export_json(b.cid)
  with self.assertRaises(b.m.MultiAIError) as error:b.run_ai(payload)
  self.assertEqual(b.store.export_json(b.cid),before)
  receipt=error.exception.receipt
  self.assertEqual(receipt['token_usage']['total_tokens'],121)
  self.assertNotIn('车辆发生碰撞',json.dumps(receipt,ensure_ascii=False))
  return receipt['validation_diagnostic']
 def test_unknown_source(self):
  p=self.base.payload();p['facts'][1]['sources'][0]['source_id']='S001'
  d=self.diagnostic(p);self.assertEqual((d['section'],d['item_index'],d['rule']),('facts',1,'source_not_in_batch'))
 def test_invalid_quote(self):
  p=self.base.payload();p['relations'][0]['right']['quote']='秘密原文不能被记录'
  d=self.diagnostic(p);self.assertEqual((d['section'],d['item_index'],d['rule']),('relations',0,'quote_not_found'))
  self.assertNotIn('秘密',json.dumps(d,ensure_ascii=False))
 def test_semicolon_timeline(self):
  b=self.base;p=b.payload();row=b.row(1);ref=b.ref(1)
  row.update(event_source=ref,time_source=None,time_state='unknown',time_precision='unknown',time_text='未知');p['timeline']=[row]
  d=self.diagnostic(p);self.assertEqual((d['section'],d['item_index'],d['rule']),('timeline',0,'timeline_multi_sentence'))
 def test_cross_document_time_reference(self):
  b=self.base;p=b.payload();row=b.row();row.update(event_source=b.ref(),time_source=b.ref(1),time_state='explicit',time_precision='minute',time_text='2026年11月1日08:30');p['timeline']=[row]
  self.assertEqual(self.diagnostic(p)['rule'],'reference_crosses_document')
 def test_pending_question_prefix(self):
  b=self.base;p=b.payload();q=b.row(0,'推断');q['reasoning']='问题未标识？';p['pending_evidence']=[q]
  d=self.diagnostic(p);self.assertEqual((d['section'],d['item_index'],d['rule']),('pending_evidence',0,'inference_prefix_missing'))
 def test_unsupported_edr(self):
  b=self.base;p=b.payload();q=b.row(0,'推断');q['reasoning']='待核实推断：EDR是否存在？';p['pending_evidence']=[q]
  d=self.diagnostic(p);self.assertEqual(d['rule'],'unsupported_data_term')
 def test_unsupported_date(self):
  b=self.base;p=b.payload();p['relations'][0]['reasoning']='待核实推断：2027年1月1日是否有记录？'
  d=self.diagnostic(p);self.assertEqual(d['section'],'relations');self.assertEqual(d['rule'],'unsupported_reasoning_time')
 def test_repeated_question(self):
  b=self.base;p=b.payload();q=b.row(0,'推断');q['reasoning']='待核实推断：是否完整是否尚未核实？';p['pending_evidence']=[q]
  d=self.diagnostic(p);self.assertEqual(d['stage'],'output_quality');self.assertEqual(d['rule'],'repeated_question_phrase')
 def test_format_loc(self):
  p=self.base.payload();p['facts'][1]['sources']=[]
  d=self.diagnostic(p);self.assertEqual((d['stage'],d['section'],d['item_index']),('format','facts',1))
 def test_case_context(self):
  p=self.base.payload();p['case_id']='another-case'
  d=self.diagnostic(p);self.assertEqual(d['rule'],'case_or_batch_mismatch');self.assertIsNone(d['item_index'])
 def event(self,i=0):
  from ai_analysis import DATE_TIME
  b=self.base;ref=b.ref(i);ref['quote']=ref['quote'].split('；')[-1].rstrip('\r\n')
  row=b.row(i);row.update(text=ref['quote'],sources=[deepcopy(ref)],event_source=deepcopy(ref),time_source=deepcopy(ref),
      time_state='explicit',time_precision='minute',time_text=DATE_TIME.search(ref['quote']).group())
  return row
 def test_precision_mismatch(self):
  p=self.base.payload();row=self.event();row['time_precision']='date';p['timeline']=[row]
  self.assertEqual(self.diagnostic(p)['rule'],'time_precision_mismatch')
 def test_unknown_fields_invalid(self):
  p=self.base.payload();row=self.event();row['time_state']='unknown';p['timeline']=[row]
  self.assertEqual(self.diagnostic(p)['rule'],'unknown_time_fields_invalid')
 def test_time_reference_not_event(self):
  from ai_analysis import DATE_TIME
  p=self.base.payload();row=self.event();row['time_source']['quote']=DATE_TIME.search(row['text']).group();p['timeline']=[row]
  self.assertEqual(self.diagnostic(p)['rule'],'time_reference_not_event')
 def test_time_text_unsupported(self):
  p=self.base.payload();row=self.event();row['time_text']='2099年1月1日';p['timeline']=[row]
  self.assertEqual(self.diagnostic(p)['rule'],'time_not_uniquely_supported')
 def test_event_text_differs_from_primary_quote(self):
  p=self.base.payload();row=self.event();row['text']='车辆发生碰撞';p['timeline']=[row]
  self.assertEqual(self.diagnostic(p)['rule'],'timeline_text_not_primary_quote')
 def test_incomplete_sentence(self):
  p=self.base.payload();row=self.event();ref=self.base.ref();ref['quote']='车辆发生碰撞。'
  row.update(text=ref['quote'],sources=[ref],event_source=ref,time_source=None,time_state='unknown',time_precision='unknown',time_text='未知');p['timeline']=[row]
  self.assertEqual(self.diagnostic(p)['rule'],'timeline_incomplete_sentence')
 def test_duplicate_event_global_index(self):
  p=self.base.payload();event=self.event();p['timeline']=[event,deepcopy(event)]
  d=self.diagnostic(p);self.assertEqual((d['rule'],d['item_index']),('timeline_duplicate_event',1))
 def test_grouped_document_index_maps_back_to_joint_index(self):
  p=self.base.payload();bad=self.event(0);bad['time_precision']='date'
  p['timeline']=[self.event(0),self.event(1),bad]
  d=self.diagnostic(p);self.assertEqual((d['section'],d['item_index']),('timeline',2))
 def test_claim_as_fact_is_specific(self):
  from test_case_store import document
  b=self.base;did=b.store.attach_document(b.cid,'模拟主张.docx',document('驾驶人主张：车辆发生碰撞。'))
  b.ids=[b.ids[0],did];b.batch=b.m.prepare_case(b.store,b.cid,b.ids,b.settings)
  p=b.payload()
  d=self.diagnostic(p);self.assertEqual(d['rule'],'claim_or_uncertainty_as_fact');self.assertEqual(d['section'],'facts')
 def test_text_not_quote(self):
  p=self.base.payload();p['facts'][0]['text']='不在原文的秘密文字'
  d=self.diagnostic(p);self.assertEqual(d['rule'],'text_not_in_quote')
 def test_relation_same_document(self):
  p=self.base.payload();p['relations'][0]['right']=deepcopy(p['relations'][0]['left'])
  self.assertEqual(self.diagnostic(p)['rule'],'relation_requires_independent_documents')
 def test_cross_document_fact_refs_not_silently_joined(self):
  p=self.base.payload();p['facts'][0]['sources'].append(self.base.ref(1))
  self.assertEqual(self.diagnostic(p)['rule'],'reference_crosses_document')
 def test_source_id_with_private_text_is_masked(self):
  p=self.base.payload();p['relations'][0]['left']['source_id']='私密标识不可打印'
  d=self.diagnostic(p);self.assertNotIn('私密',json.dumps(d,ensure_ascii=False));self.assertEqual(d['trigger_source_id'],'rejected_source_id')
 def test_success_receipt_and_result_unchanged(self):
  result,_=self.base.run_ai();self.assertEqual(result['receipt']['evidence_status'],'passed')
  self.assertFalse(result['receipt'].get('validation_diagnostic'))
 def test_format_can_locate_known_source_without_echoing_input(self):
  p=self.base.payload();p['facts'][0]['kind']='私密非法标签'
  d=self.diagnostic(p);self.assertEqual(d['source_ids'],[self.base.ref(0)['source_id']]);self.assertNotIn('私密',json.dumps(d,ensure_ascii=False))
 def test_four_sample_full_source_semicolon_and_valid_narrow_event(self):
  from pathlib import Path
  b=self.base;root=Path(__file__).resolve().parents[1]/'samples_multidoc'
  b.ids=[b.store.attach_document(b.cid,f.name,f.read_bytes()) for f in sorted(root.iterdir())]
  b.batch=b.m.prepare_case(b.store,b.cid,b.ids,b.settings)
  i=next(i for i,s in enumerate(b.batch['sources']) if '现场记录：' in s['text'])
  row=b.row(i);ref=b.ref(i);row.update(event_source=ref,time_source=None,time_state='unknown',time_precision='unknown',time_text='未知')
  p=b.payload();p.update(facts=[],relations=[],timeline=[row])
  with self.assertRaises(b.m.MultiAIError) as err:b.run_ai(p,coverage_acknowledged=b.batch['required_ack'])
  self.assertEqual(err.exception.receipt['validation_diagnostic']['rule'],'timeline_multi_sentence')
  from ai_analysis import DATE_TIME
  quote=ref['quote'].split('；')[-1].rstrip('\r\n');ref['quote']=quote
  row.update(text=quote,sources=[deepcopy(ref)],event_source=deepcopy(ref),time_source=deepcopy(ref),time_state='explicit',time_precision='minute',time_text=DATE_TIME.search(quote).group())
  import time
  with patch('security.time.time',return_value=time.time()+2):result,_=b.run_ai(p,coverage_acknowledged=b.batch['required_ack'])
  self.assertEqual(len(result['timeline']),1)
 def test_all_current_static_legacy_validation_messages_have_fixed_rules(self):
  import ast
  from pathlib import Path
  import ai_analysis
  from validation_diagnostics import RULES
  tree=ast.parse(Path(ai_analysis.__file__).read_text())
  functions={'analysis_context','build_sources','_explicit_time','_timeline_binding','validate_analysis','_apply_output_quality'}
  messages=set()
  for func in tree.body:
   if isinstance(func,ast.FunctionDef) and func.name in functions:
    for node in ast.walk(func):
     if isinstance(node,ast.Raise) and isinstance(node.exc,ast.Call) and isinstance(node.exc.func,ast.Name) and node.exc.func.id=='AIError':
      if node.exc.args and isinstance(node.exc.args[0],ast.Constant):messages.add(node.exc.args[0].value)
  self.assertFalse(messages-set(RULES))
 def test_unknown_legacy_message_never_echoed(self):
  from ai_analysis import AIError
  b=self.base
  with patch('multidoc_ai.validate_analysis',side_effect=AIError('未知异常附带秘密正文')):
   d=self.diagnostic(b.payload())
  self.assertEqual(d['rule'],'document_validation_rejected');self.assertNotIn('秘密',json.dumps(d,ensure_ascii=False))
 def test_ambiguous_quote(self):
  from test_case_store import document
  b=self.base;did=b.store.attach_document(b.cid,'模拟重复词.docx',document('车辆发生碰撞。车辆发生碰撞。'))
  b.ids=[did,b.ids[0]];b.batch=b.m.prepare_case(b.store,b.cid,b.ids,b.settings)
  i=next(i for i,s in enumerate(b.batch['sources']) if s['document_id']==did)
  p=b.payload();p['facts']=[b.row(i)];p['facts'][0]['sources'][0]['quote']='车辆发生碰撞。'
  self.assertEqual(self.diagnostic(p)['rule'],'quote_ambiguous')
 def test_semantic_policy_has_own_stage_and_original_relation_index(self):
  p=self.base.payload();p['relations'][0]['relation_type']='support_candidate'
  d=self.diagnostic(p);self.assertEqual((d['stage'],d['section'],d['item_index'],d['rule']),('semantic_policy','relations',0,'strong_relation_not_supported'))
 def test_declared_existence_rejected_without_echo(self):
  p=self.base.payload();p['relations'][0]['reasoning']='待核实推断：日志已经缺失，是否有记录？'
  self.assertEqual(self.diagnostic(p)['rule'],'asserted_data_existence')
 def test_schema_extra_secret_field_is_not_in_diagnostic(self):
  p=self.base.payload();p['秘密自定义字段']='私密内容'
  d=self.diagnostic(p);self.assertEqual(d['rule'],'schema_rejected');self.assertNotIn('私密',json.dumps(d,ensure_ascii=False));self.assertNotIn('秘密',json.dumps(d,ensure_ascii=False))
 def test_primary_source_constraint(self):
  p=self.base.payload();row=self.event();row['sources']*=2;p['timeline']=[row]
  self.assertEqual(self.diagnostic(p)['rule'],'timeline_primary_reference_required')
 def test_question_must_end_with_question_mark(self):
  p=self.base.payload();q=self.base.row(0,'推断');q['reasoning']='待核实推断：原始资料需要检查。';p['pending_evidence']=[q]
  self.assertEqual(self.diagnostic(p)['rule'],'inference_question_required')
 def test_actual_failing_time_reference_is_recorded(self):
  p=self.base.payload();row=self.event();row['time_source']=self.base.ref(1);p['timeline']=[row]
  d=self.diagnostic(p);self.assertEqual(d['trigger_source_id'],self.base.ref(1)['source_id'])
