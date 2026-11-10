"""多文档1.2：一次请求、明确编号选择、确定性恢复、原验证链与显式导入。"""
from copy import deepcopy
import hashlib,json,re
from typing import Literal
from pydantic import Field,ValidationError
import multidoc_ai as old
from pending_catalog import build_pending_catalog,PendingSelection,CATALOG_VERSION,CatalogError
from timeline_candidates import build_event_catalog,CANDIDATE_VERSION
from validation_diagnostics import diagnostic,schema_diagnostic

SCHEMA_VERSION='multidoc-analysis/1.2'
PROMPT_VERSION='multidoc/pending-selection-v1'
_base=old.CANDIDATE_PROMPT.replace('输出独立multidoc-analysis/1.1 Schema，prompt_version必须为multidoc/candidates-v1',
                                    '输出独立multidoc-analysis/1.2 Schema，prompt_version必须为multidoc/pending-selection-v1')
# 删除旧pending自由摘录契约，避免同一请求中既要求quote/text又禁止这些字段。
_start=_base.index('pending_evidence为推断')
_end=_base.index('relations.reasoning也',_start)
_base=_base[:_start]+_base[_end:]
PROMPT=_base+'''
本请求改用multidoc-analysis/1.2及prompt_version=multidoc/pending-selection-v1，其他facts、timeline和relations规则仍有效。
pending_evidence替换旧自由摘录契约：只输出anchor_id、evidence_ids、reasoning；禁止text、quote、kind、哈希或坐标。
必须显式从pending_catalog.entries选择全部必要证据编号，anchor_id是主证据且必须包含在evidence_ids。最多4来源，不补来源、不丢来源过检。
程序从主证据恢复text并逐字恢复所有选中引文。核查问题仍用“待核实推断：”开头和问号结束。
标题只能作为明确选中的附加来源，不能证明技术功能或数据存在；EDR/DSSAD需由选中原文支持，不跨文件移植概念。
完整行可能包含多个命题或前文主体限定，候选不是事实认定；保留不确定性，区分企业主张、驾驶人自述和材料记载。
同一证据可支持不同核查问题，不重复输出相同来源的相同问题。合法编号不保证语义相关，结果全部待人工核验。
目录中的source_id指向sources里已经完整给出的原文；编号代表该完整原文，不需要复制引文。逐字回传pending_catalog_sha256；不得编造编号。'''

class Analysis12(old.CandidateAnalysis):
 schema_version: Literal['multidoc-analysis/1.2']
 prompt_version: Literal['multidoc/pending-selection-v1']
 pending_catalog_sha256: str=Field(pattern=r'^[a-f0-9]{64}$')
 pending_evidence: list[PendingSelection]=Field(max_length=12)

def prepare_case(store,cid,selected,settings):
 try:batch=old.prepare_case(store,cid,selected,settings)
 except (old.MultiAIError,old.AIError) as exc:
  rule='source_or_character_limit_exceeded' if str(exc)=='联合输入超过16000字符或96块，未发送。' else 'archive_or_input_limit_rejected'
  raise old.MultiAIError(diagnostic=diagnostic('preflight',rule,{},{})) from None
 batch['batch_sha256']=old.digest([batch['batch_sha256'],SCHEMA_VERSION,PROMPT_VERSION,
                       hashlib.sha256(PROMPT.encode()).hexdigest(),old.digest(Analysis12.model_json_schema()),CATALOG_VERSION])
 try:batch['pending_catalog']=build_pending_catalog(store,cid,batch)
 except (ValueError,KeyError):
  raise old.MultiAIError(diagnostic=diagnostic('pending_catalog','pending_catalog_invalid',{},batch)) from None
 # 任一超长行碎片均阻断1.2，不能静默失去潜在关键来源。
 if batch['pending_catalog']['excluded']:
  detail=diagnostic('pending_catalog','pending_catalog_incomplete',{'source_ids':[r['source_id'] for r in batch['pending_catalog']['excluded']]},batch)
  detail.update(excluded_count=len(batch['pending_catalog']['excluded']),omission_rules=['physical_line_split'])
  raise old.MultiAIError(diagnostic=detail)
 return batch

def request_for(batch,settings):
 catalog=batch['pending_catalog'];events=build_event_catalog(batch);schema=Analysis12.model_json_schema()
 props=schema['$defs']['PendingSelection']['properties'];ids=[c['candidate_id'] for c in catalog['entries']]
 if ids:
  props['anchor_id']['enum']=ids;props['evidence_ids']['items']['enum']=ids
 else:schema['properties']['pending_evidence']['maxItems']=0
 if events['candidates']:schema['$defs']['EventSelection']['properties']['candidate_id']['enum']=[c['candidate_id'] for c in events['candidates']]
 else:schema['properties']['timeline']['maxItems']=0
 payload={k:batch[k] for k in ('case_id','batch_sha256','documents','sources')}
 compact={'version':catalog['version'],'sha256':catalog['sha256'],
          'entries':[{k:e[k] for k in ('candidate_id','source_id','document_id','quote_sha256')} for e in catalog['entries']]}
 payload.update(event_catalog=events,pending_catalog=compact,pending_catalog_sha256=catalog['sha256'])
 request={'model':settings.model,'instructions':PROMPT,'input':json.dumps(payload,ensure_ascii=False),
  'text':{'format':{'type':'json_schema','name':'MultiAnalysis12','strict':True,'schema':schema}},
  'max_output_tokens':6000,'store':False,'truncation':'disabled'}
 request=old.adapt_request(request,settings.provider)
 chars=batch['input_chars']+sum(len(c['quote']) for c in events['candidates'])
 budget={'input_chars':chars,'request_bytes':len(json.dumps(request,ensure_ascii=False,separators=(',',':')).encode())+1024}
 if chars>16000 or budget['request_bytes']>settings.max_request_bytes:
  raise old.MultiAIError(diagnostic=diagnostic('budget','pending_request_budget_exceeded',{},batch))
 return request,budget

def _reject(batch,rule,index=None,ids=()):
 d=diagnostic('pending_selection',rule,{'section':'pending_evidence','item_index':index,'source_ids':[]},batch)
 d['candidate_ids']=[x if isinstance(x,str) and re.fullmatch(r'PE_[a-f0-9]{24}',x) else 'rejected_candidate_id' for x in ids][:4]
 raise old.MultiAIError(diagnostic=d)

def validate_output(store,cid,batch,raw):
 try:parsed=Analysis12.model_validate(raw)
 except ValidationError as exc:raise old.MultiAIError(diagnostic=schema_diagnostic(exc,{'stage':'format'},batch,raw)) from None
 if parsed.case_id!=cid or parsed.batch_sha256!=batch['batch_sha256']:_reject(batch,'case_or_batch_mismatch')
 try:catalog=build_pending_catalog(store,cid,batch)
 except (ValueError,KeyError):_reject(batch,'pending_catalog_invalid')
 if catalog!=batch['pending_catalog'] or parsed.pending_catalog_sha256!=catalog['sha256']:_reject(batch,'pending_catalog_mismatch')
 lookup={e['candidate_id']:e for e in catalog['entries']};restored=[];seen=set()
 for index,row in enumerate(parsed.pending_evidence):
  ids=row.evidence_ids
  if len(set(ids))!=len(ids):_reject(batch,'pending_duplicate_evidence',index,ids)
  if any(e not in lookup for e in ids):_reject(batch,'pending_candidate_not_in_catalog',index,ids)
  if row.anchor_id not in ids:_reject(batch,'pending_anchor_not_selected',index,[row.anchor_id])
  key=(tuple(sorted(ids)),row.reasoning)
  if key in seen:_reject(batch,'pending_duplicate_question',index,ids)
  seen.add(key)
  restored.append({'kind':'推断','text':lookup[row.anchor_id]['quote'],'reasoning':row.reasoning,
    'sources':[{'source_id':lookup[e]['source_id'],'quote':lookup[e]['quote']} for e in ids]})
 intermediate=parsed.model_dump();intermediate.pop('pending_catalog_sha256')
 intermediate.update(schema_version=old.CANDIDATE_SCHEMA_VERSION,prompt_version=old.CANDIDATE_PROMPT_VERSION,pending_evidence=restored)
 result=old.validate_candidate_output(store,cid,batch,intermediate)
 if len(result['pending_evidence'])!=len(restored):_reject(batch,'pending_restoration_count_mismatch')
 result.update(schema_version=SCHEMA_VERSION,prompt_version=PROMPT_VERSION,raw_output=parsed.model_dump(),
  candidate_selection={'catalog_version':CANDIDATE_VERSION,'catalog_sha256':build_event_catalog(batch)['sha256'],
                       'selection_ids':[c.candidate_id for c in parsed.timeline]},
  pending_selection={'catalog_version':CATALOG_VERSION,'catalog_sha256':catalog['sha256'],'catalog':catalog,
                     'raw_selection':[r.model_dump() for r in parsed.pending_evidence],
                     'restored_references':deepcopy(result['pending_evidence'])})
 return result

def receipt_fields(batch,parsed):
 return {'analysis_output_sha256':old.digest(parsed.model_dump()),'pending_catalog_version':CATALOG_VERSION,'pending_catalog_sha256':batch['pending_catalog']['sha256'],
  'pending_selection_ids':[{'anchor_id':r.anchor_id,'evidence_ids':r.evidence_ids,
                            'reasoning_sha256':hashlib.sha256(r.reasoning.encode()).hexdigest()} for r in parsed.pending_evidence]}

def analyze_case(*args,**kwargs):return old.analyze_case(*args,**kwargs,_pending_protocol=True)

def validate_receipt_result(receipt,batch,result):
 parsed=Analysis12.model_validate(result['raw_output']);expected=receipt_fields(batch,parsed)
 expected.update(schema_version=SCHEMA_VERSION,prompt_version=PROMPT_VERSION,prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),
  batch_sha256=batch['batch_sha256'],case_id=batch['case_id'],candidate_version=CANDIDATE_VERSION,
  candidate_catalog_sha256=build_event_catalog(batch)['sha256'],candidate_selection_ids=[r.candidate_id for r in parsed.timeline],
  format_status='passed',evidence_status='passed',semantic_status='pending_human_review',provider_status='completed',call_status='response_received')
 if any(receipt.get(k)!=v for k,v in expected.items()):_reject(batch,'pending_receipt_mismatch')

def validate_saved_receipt(case,receipt,*,require_statements=True):
 """仅对1.2分派；从归档重建目录，核验选择与案件中的待核查记录，不新增确认。"""
 from case_store import CaseStore
 from security import Settings
 temp=CaseStore();temp._cases[case.case_id]=case
 selected=[d['document_id'] for d in receipt['document_snapshots']]
 batch=prepare_case(temp,case.case_id,selected,Settings(provider=receipt['provider'],model=receipt.get('requested_model','')))
 catalog=batch['pending_catalog'];lookup={e['candidate_id']:e for e in catalog['entries']}
 expected={'schema_version':SCHEMA_VERSION,'prompt_version':PROMPT_VERSION,'prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest(),
  'batch_sha256':batch['batch_sha256'],'pending_catalog_version':CATALOG_VERSION,'pending_catalog_sha256':catalog['sha256'],
  'candidate_version':CANDIDATE_VERSION,'candidate_catalog_sha256':build_event_catalog(batch)['sha256']}
 if any(receipt.get(k)!=v for k,v in expected.items()):_reject(batch,'pending_receipt_mismatch')
 if not isinstance(receipt.get('analysis_output_sha256'),str) or not re.fullmatch(r'[a-f0-9]{64}',receipt['analysis_output_sha256']):_reject(batch,'pending_receipt_mismatch')
 event_ids=receipt.get('candidate_selection_ids');valid_events={c['candidate_id'] for c in build_event_catalog(batch)['candidates']}
 if not isinstance(event_ids,list) or len(event_ids)>24 or len(event_ids)!=len(set(event_ids)) or not set(event_ids)<=valid_events:_reject(batch,'pending_receipt_mismatch')
 selections=receipt.get('pending_selection_ids')
 if not isinstance(selections,list) or len(selections)>12:_reject(batch,'pending_receipt_mismatch')
 statements=receipt.get('pending_statement_ids')
 if require_statements and (not isinstance(statements,list) or len(statements)!=len(selections)):_reject(batch,'pending_receipt_mismatch')
 byid={r.statement_id:r for r in case.inferences};rows=[];seen=set()
 for i,item in enumerate(selections):
  if not isinstance(item,dict) or set(item)!={'anchor_id','evidence_ids','reasoning_sha256'}:_reject(batch,'pending_receipt_mismatch',i)
  ids=item['evidence_ids'];anchor=item['anchor_id']
  if not isinstance(ids,list) or not 1<=len(ids)<=4 or len(set(ids))!=len(ids) or any(x not in lookup for x in ids) or anchor not in ids:_reject(batch,'pending_receipt_mismatch',i)
  if not isinstance(item['reasoning_sha256'],str) or not re.fullmatch(r'[a-f0-9]{64}',item['reasoning_sha256']):_reject(batch,'pending_receipt_mismatch',i)
  key=(tuple(sorted(ids)),item['reasoning_sha256'])
  if key in seen:_reject(batch,'pending_receipt_mismatch',i)
  seen.add(key)
  if require_statements:
   row=byid.get(statements[i]);bound=[lookup[x]['evidence_span_id'] for x in ids]
   if row is None or sorted(row.evidence_ids)!=sorted(bound) or hashlib.sha256(row.text.encode()).hexdigest()!=item['reasoning_sha256']:_reject(batch,'pending_receipt_mismatch',i)
   rows.append({'kind':'推断','text':lookup[anchor]['quote'],'reasoning':row.text,
                'sources':[{'source_id':lookup[x]['source_id'],'quote':lookup[x]['quote']} for x in ids]})
 if require_statements:
  raw={'schema_version':old.SCHEMA_VERSION,'prompt_version':old.PROMPT_VERSION,'case_id':case.case_id,'batch_sha256':batch['batch_sha256'],
       'facts':[],'timeline':[],'relations':[],'pending_evidence':rows}
  old.validate_case_output(temp,case.case_id,batch,raw)
