"""只读离线调查：固定虚构B01，不推测真实case_id，不改变生产协议或调用服务商。"""
import argparse,hashlib,json,re,sys
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from openai import OpenAI
from case_store import CaseStore
from security import Settings
from model_runtime import call_sdk
import multidoc_v13 as m
import multidoc_ai as old

REPORTED_IDS=('PE_1c2855f9e9e11f2b97762e19','PE_8157e098231cf885924d2f61','PE_79f4a8f3177d8404e67f5baa')
ROOT=Path(__file__).resolve().parents[1]


def fixture(case_label):
 store=CaseStore();temporary=store.create_case('完全虚构 PE编号专项调查')
 case=store._cases.pop(temporary);cid='case_'+hashlib.sha256(case_label.encode()).hexdigest()[:32]
 case.case_id=cid;store._cases[cid]=case;ids=[];data=ROOT/'datasets/CASE-001/standard'
 for item in json.loads((data/'manifest.json').read_text())['documents']:
  if item['material_id'] in ('D01','D02','D03','D04'):
   p=data/item['path'];raw=p.read_bytes()
   assert hashlib.sha256(raw).hexdigest()==item['sha256']
   ids.append(store.attach_document(cid,p.name,raw))
 cfg=Settings(provider='deepseek',model='deepseek-flash')
 return store,cid,ids,cfg,m.prepare_case(store,cid,ids,cfg)


def investigate():
 store,cid,selected,cfg,batch=fixture('AutoLEX PE investigation fixture A /1')
 entries=batch['pending_catalog']['entries'];ids=[e['candidate_id'] for e in entries]
 _,_,_,_,other=fixture('AutoLEX PE investigation fixture B /1')
 repeated=m.prepare_case(store,cid,list(reversed(selected)),cfg)
 checks=[]
 def check(name,value):
  assert value,name
  checks.append({'check':name,'status':'passed'})
 check('same_case_snapshots_rebuild_identical_catalog',repeated['pending_catalog']==batch['pending_catalog'])
 check('same_originals_different_case_have_disjoint_pe_ids',not set(ids)&{e['candidate_id'] for e in other['pending_catalog']['entries']})
 request,budget=m.request_for(batch,cfg);payload=json.loads(request['input']);schema=request['text']['format']['schema']
 wire=[]
 unknown='PE_'+'f'*24
 assert unknown not in ids
 chosen=[ids[0],unknown,ids[-1]]
 # 仅构造人工反例：两条有效+一条无效；不是对三个真实回执编号的比较。
 raw={'schema_version':m.SCHEMA_VERSION,'prompt_version':m.PROMPT_VERSION,'case_id':cid,
      'batch_sha256':batch['batch_sha256'],'facts':[],'timeline':[],'relations':[],
      'pending_evidence':[{'anchor_id':chosen[0],'evidence_ids':chosen,'reasoning':'待核实推断：材料范围是否需要进一步核查？'}]}
 def handler(req):
  wire.append(json.loads(req.content))
  return httpx.Response(200,json={'id':'offline-research','object':'response','created_at':1,'status':'completed','model':'offline-mock',
    'output':[{'id':'msg','type':'message','role':'assistant','status':'completed','content':[
      {'type':'output_text','text':json.dumps(raw,ensure_ascii=False),'annotations':[]}]}]})
 def factory(**kw):
  assert kw['max_retries']==0
  return OpenAI(**kw,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
 response=call_sdk('offline-not-real',request,factory,provider='deepseek')
 check('sdk_only_one_local_http_mock_request',len(wire)==1 and response['provider_status']=='completed')
 props=wire[0]['text']['format']['schema']['$defs']['PendingSelection']['properties']
 sent_catalog=json.loads(wire[0]['input'])['pending_catalog']['entries']
 check('wire_catalog_anchor_enum_evidence_enum_equal',
       set(ids)=={e['candidate_id'] for e in sent_catalog}==set(props['anchor_id']['enum'])==set(props['evidence_ids']['items']['enum']))
 source_lookup={s['source_id']:s for s in payload['sources']}
 check('catalog_mapping_matches_source_document_and_quote_hash',all(
    row['source_id'] in source_lookup and row['document_id']==source_lookup[row['source_id']]['document_id']
    and row['quote_sha256']==hashlib.sha256(source_lookup[row['source_id']]['text'].encode()).hexdigest()
    for row in sent_catalog))
 check('deepseek_adaptation_keeps_enums_but_has_no_strict_flag','strict' not in wire[0]['text']['format'])
 parsed=m.Analysis13.model_validate_json(response['output_text'])
 check('static_pydantic_accepts_string_not_in_request_enum',parsed.pending_evidence[0].evidence_ids[1]==unknown and unknown not in props['evidence_ids']['items']['enum'])
 before=store.export_json(cid)
 try:m.validate_output(store,cid,batch,parsed)
 except old.MultiAIError as exc:
  diagnostic=exc.diagnostic
 else:raise AssertionError('未知编号未被拒绝')
 check('membership_rejects_unknown_without_writing_case',diagnostic['rule']=='pending_candidate_not_in_catalog' and store.export_json(cid)==before)
 check('diagnostic_lists_all_selected_ids_not_only_unknown',diagnostic['candidate_ids']==chosen)
 # 只比较编码字符，不实现短编号Schema或恢复器，也不声称模型/Token准确率。
 indices=list(range(len(ids)))
 pe_bytes=len(json.dumps(ids,separators=(',',':')).encode())
 index_bytes=len(json.dumps(indices,separators=(',',':')).encode())
 return {'declaration':'完全虚构，仅用于离线机制调查。非第六次真实响应重现；没有生产协议改动。',
  'baseline_commit':'b864800eda6c991c0e10b8cd6549c2cb93149258','real_model_calls':0,'http_mock_calls':1,
  'secrets_accessed':False,'quota_database_accessed':False,
  'actual_catalog_reconstruction':{'performed':False,'reason':'真实case_id、批次/目录SHA、实际文档快照上下文未提供；不使用假案件目录作成员判定',
     'reported_ids':[{'candidate_id':x,'well_formed_pe_24hex':bool(re.fullmatch(r'PE_[0-9a-f]{24}',x)),
                     'actual_membership':'not_determined'} for x in REPORTED_IDS]},
  'fictional_fixture':{'case_id':cid,'case_id_is_real_run':False,'batch_sha256':batch['batch_sha256'],
      'pending_catalog_sha256':batch['pending_catalog']['sha256'],'candidate_count':len(entries),
      'source_count':len(batch['sources']),'request_budget':budget},
  'self_checks':checks,
  'artificial_mixed_selection':{'label':'两条有效加一条无效的人工反例，不是用户三个编号的定位',
    'selected_ids':chosen,'known_id_count':2,'unknown_id_count':1,'safe_diagnostic':diagnostic},
  'identifier_array_encoding_only':{'entry_count':len(ids),'pe_string_array_utf8_bytes':pe_bytes,
      'zero_based_integer_array_utf8_bytes':index_bytes,'scope':'单数组编码长度，不是完整请求预算、Token数量、模型准确率或费用比较'}}


def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args(argv)
 result=investigate();text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
 if args.output:args.output.write_text(text)
 else:print(text,end='')
if __name__=='__main__':main()
