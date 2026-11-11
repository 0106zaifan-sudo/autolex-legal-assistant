"""固定虚构B01协议1.4离线预算。官方SDK仅使用本地HTTP Mock，不能发起真实请求。"""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from openai import OpenAI
from case_store import CaseStore
from security import Settings
from multidoc_v14 import prepare_case,request_for,SCHEMA_VERSION,PROMPT_VERSION,PROMPT


def report():
 root=Path(__file__).resolve().parents[1]/'datasets/CASE-001/standard'
 store=CaseStore();tmp=store.create_case('完全虚构 B01预算');case=store._cases.pop(tmp)
 cid='case_'+hashlib.sha256(b'AutoLEX 1.4 B01 offline budget/1').hexdigest()[:32]
 case.case_id=cid;store._cases[cid]=case;ids=[]
 for d in json.loads((root/'manifest.json').read_text())['documents']:
  if d['material_id'] in ('D01','D02','D03','D04'):
   p=root/d['path'];raw=p.read_bytes()
   if hashlib.sha256(raw).hexdigest()!=d['sha256']:raise ValueError('固定模拟原件哈希不符')
   ids.append(store.attach_document(cid,p.name,raw))
 rows=[]
 for provider in ('deepseek','openai'):
  settings=Settings(provider=provider);batch=prepare_case(store,cid,ids,settings);request,budget=request_for(batch,settings)
  wire=[]
  def handler(req):
   wire.append(len(req.content))
   return httpx.Response(200,json={'id':'offline-serialization-only','object':'response','created_at':1,'status':'completed','model':'offline','output':[]})
  with OpenAI(api_key='offline-not-real',base_url=settings.provider_spec.base_url,max_retries=0,
              http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
   client.responses.create(**request)
  assert len(wire)==1 and wire[0]<=budget['request_bytes']<=settings.max_request_bytes
  rows.append({'provider':provider,'model':settings.model,'schema_version':SCHEMA_VERSION,'prompt_version':PROMPT_VERSION,
   'prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest(),'batch_sha256':batch['batch_sha256'],
   'documents':[{'file_name':d['file_name'],'document_id':d['document_id'],'file_sha256':d['file_sha256']} for d in batch['documents']],
   'pending_catalog_version':batch['pending_catalog']['version'],'pending_catalog_sha256':batch['pending_catalog']['sha256'],
   'pending_alias_version':batch['alias_map']['version'],'pending_alias_map_sha256':batch['alias_map']['sha256'],
   'alias_count':len(batch['alias_map']['entries']),'min_symbol_distance':batch['alias_map']['min_symbol_distance'],
   'source_count':len(batch['sources']),'pending_candidate_count':len(batch['pending_catalog']['entries']),
   'required_coverage_acknowledgements':batch['required_ack'],'budget':budget,'sdk_http_mock_wire_bytes':wire[0],
   'max_request_bytes':settings.max_request_bytes,'max_output_tokens':request['max_output_tokens'],
   'reasoning_configuration':request.get('reasoning'),'input_tokens':None,'output_tokens':None,
   'token_measurement_status':'not_measured_no_real_model','automatic_retries':0})
 return {'declaration':'完全虚构，仅用于软件测试；SDK本地HTTP Mock序列化，不是真实模型验收',
         'schema_version':SCHEMA_VERSION,'real_model_calls':0,'quota_database_accessed':False,
         'rows':rows,'authorization':'本报告不授予任何调用许可，不代表实际剩余额度充足'}


def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args(argv)
 text=json.dumps(report(),ensure_ascii=False,indent=2)+'\n'
 if args.output:args.output.write_text(text)
 else:print(text,end='')
if __name__=='__main__':main()
