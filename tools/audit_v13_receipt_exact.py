"""第六次回执与用户原案件工作包的只读精确核对；不接受测试目录替代。"""
import argparse,hashlib,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from case_store import CaseStore
from security import Settings
from evidence import snapshot_hash
from workspace_bundle import load_json,restore_workspace,MAX_ZIP_BYTES
import multidoc_v13 as m

ROOT=Path(__file__).resolve().parents[1]
REPORTED_IDS=('PE_1c2855f9e9e11f2b97762e19','PE_8157e098231cf885924d2f61','PE_79f4a8f3177d8404e67f5baa')
CHECKS=('receipt_available','receipt_valid','workspace_available','workspace_valid','case_id',
        'four_b01_snapshots','original_and_parsed_bytes','protocol','prompt_hash','batch_sha256','pending_catalog_sha256')

class StopAudit(Exception):pass


def blank(expected_ids):
 return {'status':'blocked','comparison_performed':False,'real_model_calls':0,'secrets_accessed':False,
         'checks':{k:'not_checked' for k in CHECKS},'stop_reason':None,
         'membership':[{'candidate_id':s,'status':'not_compared'} for s in expected_ids]}


def gate(report,name,condition,code=None):
 report['checks'][name]='matched' if condition else ('unavailable' if name in ('receipt_available','workspace_available') else 'mismatch')
 if not condition:
  report['stop_reason']=code or name+'_mismatch'
  raise StopAudit()


def _verify(report,receipt,store,expected_ids):
 diag=receipt.get('validation_diagnostic',{})
 shape=(isinstance(diag,dict) and diag.get('stage')=='pending_selection' and
  diag.get('rule')=='pending_candidate_not_in_catalog' and diag.get('section')=='pending_evidence' and
  type(diag.get('item_index')) is int and diag.get('item_index')==8 and diag.get('candidate_ids')==list(expected_ids))
 gate(report,'receipt_valid',shape and receipt.get('provider_status')=='completed' and
      receipt.get('call_status')=='response_received' and receipt.get('format_status')=='passed' and receipt.get('evidence_status')=='failed',
      'receipt_target_or_status_mismatch')
 gate(report,'case_id',receipt.get('case_id') in store.list_cases())
 cid=receipt['case_id'];case=store.get_case(cid);snapshots=receipt.get('document_snapshots')
 keys={'document_id','file_sha256','parsed_text_sha256','parser_version'}
 try:
  manifest=load_json((ROOT/'datasets/CASE-001/standard/manifest.json').read_bytes())
  b01_hashes={d['sha256'] for d in manifest['documents'] if d['material_id'] in ('D01','D02','D03','D04')}
  matches=(isinstance(snapshots,list) and len(snapshots)==4 and all(isinstance(s,dict) and set(s)==keys for s in snapshots)
   and len({s['document_id'] for s in snapshots})==4 and {s['file_sha256'] for s in snapshots}==b01_hashes
   and all(s['document_id'] in case.documents and all(getattr(case.documents[s['document_id']],k)==v for k,v in s.items()) for s in snapshots))
 except (KeyError,TypeError,AttributeError):matches=False
 gate(report,'four_b01_snapshots',matches)
 selected=[s['document_id'] for s in snapshots]
 gate(report,'original_and_parsed_bytes',all(
      hashlib.sha256(case.documents[d].original_bytes).hexdigest()==case.documents[d].file_sha256
      and snapshot_hash(case.documents[d].units)==case.documents[d].parsed_text_sha256 for d in selected))
 gate(report,'protocol',receipt.get('schema_version')==m.SCHEMA_VERSION and receipt.get('prompt_version')==m.PROMPT_VERSION
      and receipt.get('protocol')=='responses' and receipt.get('provider')=='deepseek'
      and receipt.get('pending_catalog_version')==m.CATALOG_VERSION
      and isinstance(receipt.get('requested_model'),str) and 0<len(receipt['requested_model'])<=100)
 gate(report,'prompt_hash',receipt.get('prompt_sha256')==hashlib.sha256(m.PROMPT.encode()).hexdigest())
 try:batch=m.prepare_case(store,cid,selected,Settings(provider=receipt['provider'],model=receipt['requested_model']))
 except Exception:
  report['stop_reason']='current_archive_rebuild_failed';raise StopAudit() from None
 gate(report,'batch_sha256',receipt.get('batch_sha256')==batch['batch_sha256'])
 gate(report,'pending_catalog_sha256',receipt.get('pending_catalog_sha256')==batch['pending_catalog']['sha256'])
 # 全部门禁通过后才作精确集合成员比较，不读模型原稿，不作近似匹配。
 lookup={e['candidate_id'] for e in batch['pending_catalog']['entries']}
 report['membership']=[{'candidate_id':s,'status':'in_catalog' if s in lookup else 'not_in_catalog'} for s in expected_ids]
 report.update(status='verified_context',comparison_performed=True,stop_reason=None,catalog_count=len(lookup))


def verify_store(receipt,store,*,expected_ids=REPORTED_IDS):
 """可在用户原Codespaces会话中传入原CaseStore；不修改该对象。"""
 report=blank(expected_ids)
 report['input_mode']='in_memory_case_store'
 report['checks']['workspace_available']='not_applicable'
 report['checks']['workspace_valid']='not_applicable'
 try:
  gate(report,'receipt_available',isinstance(receipt,dict))
  _verify(report,receipt,store,expected_ids)
 except StopAudit:pass
 except Exception:report['stop_reason']='verification_failed_closed'
 return report


def _sensitive_path(path):
 p=Path(path)
 return (any(x.lower() in ('.streamlit','.git','.autolex_runtime','.aws','.ssh','.codex') for x in p.resolve().parts)
         or p.name.lower() in ('secrets.json','credentials.json','secrets.toml','.env'))


def _read(path,limit,extension):
 p=Path(path)
 if p.suffix.lower()!=extension or p.is_symlink() or _sensitive_path(p):raise ValueError()
 if not p.is_file() or p.stat().st_size>limit:raise ValueError()
 data=p.read_bytes()
 if len(data)>limit:raise ValueError()
 return data


def verify_files(receipt_path,workspace_path,*,expected_ids=REPORTED_IDS):
 report=blank(expected_ids)
 report['input_mode']='user_workspace_zip'
 try:
  try:raw=_read(receipt_path,256*1024,'.json')
  except Exception:gate(report,'receipt_available',False,'receipt_unavailable')
  gate(report,'receipt_available',True)
  try:receipt=load_json(raw,256*1024)
  except Exception:gate(report,'receipt_valid',False,'receipt_invalid')
  try:data=_read(workspace_path,MAX_ZIP_BYTES,'.zip')
  except Exception:gate(report,'workspace_available',False,'workspace_unavailable')
  gate(report,'workspace_available',True)
  store=CaseStore()
  try:restore_workspace(store,data)
  except Exception:gate(report,'workspace_valid',False,'workspace_validation_failed')
  gate(report,'workspace_valid',True)
  _verify(report,receipt,store,expected_ids)
 except StopAudit:pass
 except Exception:report['stop_reason']='verification_failed_closed'
 return report


def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--receipt',required=True,type=Path);parser.add_argument('--workspace',required=True,type=Path)
 parser.add_argument('--output',type=Path)
 args=parser.parse_args(argv)
 # 不允许报告覆盖输入；不在普通日志输出路径、异常文本、原文或请求。
 if args.output and (args.output.suffix.lower()!='.json' or args.output.is_symlink() or _sensitive_path(args.output)
                     or args.output.resolve() in (args.receipt.resolve(),args.workspace.resolve())):
  print(json.dumps({'status':'blocked','stop_reason':'output_cannot_overwrite_input'},ensure_ascii=False));return 2
 report=verify_files(args.receipt,args.workspace);text=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
 if args.output:
  try:
   with args.output.open('x',encoding='utf-8') as stream:stream.write(text)
  except OSError:
   print(json.dumps({'status':'blocked','stop_reason':'report_write_failed'}));return 2
 else:print(text,end='')
 return 0 if report['comparison_performed'] else 2
if __name__=='__main__':raise SystemExit(main())
