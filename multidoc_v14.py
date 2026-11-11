"""多文档1.4：稀疏短别名选择，原PE与证据身份由程序恢复；旧版本冻结。"""
from copy import deepcopy
import hashlib,json,re
from typing import Literal
from pending_aliases import AliasSelection,build_alias_map,ALIAS_VERSION,AliasError,safe_alias
from pydantic import Field,ValidationError
import multidoc_ai as old
from pending_catalog import build_pending_catalog,PendingSelection,CATALOG_VERSION,CatalogError
from timeline_candidates import build_event_catalog,CANDIDATE_VERSION
from validation_diagnostics import diagnostic,schema_diagnostic

SCHEMA_VERSION='multidoc-analysis/1.4'
PROMPT_VERSION='multidoc/pending-alias-v1'
_base=old.CANDIDATE_PROMPT.replace('输出独立multidoc-analysis/1.1 Schema，prompt_version必须为multidoc/candidates-v1',
                                    '输出独立multidoc-analysis/1.4 Schema，prompt_version必须为multidoc/pending-alias-v1')
# 删除旧pending自由摘录契约，避免同一请求中既要求quote/text又禁止这些字段。
_start=_base.index('pending_evidence为推断')
_end=_base.index('relations.reasoning也',_start)
_base=_base[:_start]+_base[_end:]
PROMPT=_base+'''
本请求改用multidoc-analysis/1.4及prompt_version=multidoc/pending-alias-v1，其他facts、timeline和relations规则仍有效。
pending_evidence替换旧自由摘录契约：只输出anchor_alias、evidence_aliases、reasoning；禁止text、quote、kind、哈希或坐标。
必须显式从sources的pending_alias选择全部必要证据编号，anchor_alias是主证据且必须包含在evidence_aliases。最多4来源，不补来源、不丢来源过检。
程序从主证据恢复text并逐字恢复所有选中引文。核查问题仍用“待核实推断：”开头和问号结束。
标题只能作为明确选中的附加来源，不能证明技术功能或数据存在；EDR/DSSAD需由选中原文支持，不跨文件移植概念。
完整行可能包含多个命题或前文主体限定，候选不是事实认定；保留不确定性，区分企业主张、驾驶人自述和材料记载。
同一证据可支持不同核查问题，不重复输出相同来源的相同问题。合法编号不保证语义相关，结果全部待人工核验。
sources中的pending_alias与对应完整原文并列；只复制该别名，不输出或猜测PE编号。证据目录哈希由程序管理，响应不得包含pending_catalog_sha256；不得编造编号。'''

class Analysis14(old.CandidateAnalysis):
 schema_version: Literal['multidoc-analysis/1.4']
 prompt_version: Literal['multidoc/pending-alias-v1']
 pending_evidence: list[AliasSelection]=Field(max_length=12)

def prepare_case(store,cid,selected,settings):
 base=old.prepare_case(store,cid,selected,settings)
 context=old.digest([base['batch_sha256'],SCHEMA_VERSION,PROMPT_VERSION,
  hashlib.sha256(PROMPT.encode()).hexdigest(),old.digest(Analysis14.model_json_schema()),CATALOG_VERSION,ALIAS_VERSION])
 base['batch_sha256']=context
 try:
  initial=build_pending_catalog(store,cid,base)
  if initial['excluded']:raise AliasError('pending_catalog_incomplete')
  mapping=build_alias_map(initial,context)
 except (ValueError,KeyError) as exc:
  rule=str(exc) if isinstance(exc,AliasError) else 'pending_alias_catalog_invalid'
  raise old.MultiAIError(diagnostic=diagnostic('pending_alias_map',rule,{},base)) from None
 base['batch_sha256']=old.digest([context,initial['sha256'],mapping['sha256']])
 base['pending_catalog']=build_pending_catalog(store,cid,base)
 base.update(alias_map=mapping,provider=settings.provider,requested_model=settings.model)
 return base

def request_for(batch,settings):
 catalog=batch['pending_catalog'];events=build_event_catalog(batch);schema=Analysis14.model_json_schema()
 mapping=batch['alias_map'];props=schema['$defs']['AliasSelection']['properties']
 aliases=[r['alias'] for r in mapping['entries']]
 if aliases:
  props['anchor_alias']['enum']=aliases;props['evidence_aliases']['items']['enum']=aliases
 else:schema['properties']['pending_evidence']['maxItems']=0
 if events['candidates']:schema['$defs']['EventSelection']['properties']['candidate_id']['enum']=[c['candidate_id'] for c in events['candidates']]
 else:schema['properties']['timeline']['maxItems']=0
 by_pe={e['candidate_id']:e for e in catalog['entries']}
 by_source={by_pe[r['candidate_id']]['source_id']:r['alias'] for r in mapping['entries']}
 payload={k:batch[k] for k in ('case_id','batch_sha256','documents')}
 payload.update(sources=[{**source,'pending_alias':by_source[source['source_id']]} for source in batch['sources']],
                event_catalog=events,pending_alias_version=ALIAS_VERSION)
 request={'model':settings.model,'instructions':PROMPT,'input':json.dumps(payload,ensure_ascii=False),
  'text':{'format':{'type':'json_schema','name':'MultiAnalysis14','strict':True,'schema':schema}},
  'max_output_tokens':6000,'store':False,'truncation':'disabled'}
 request=old.adapt_request(request,settings.provider)
 budget={'input_chars':batch['input_chars']+sum(len(c['quote']) for c in events['candidates']),
  'request_bytes':len(json.dumps(request,ensure_ascii=False,separators=(',',':')).encode())+1024}
 if budget['input_chars']>16000 or budget['request_bytes']>settings.max_request_bytes:
  raise old.MultiAIError(diagnostic=diagnostic('budget','pending_request_budget_exceeded',{},batch))
 return request,budget

def _reject(batch,rule,index=None,selected=(),unknown=(),anchor=None):
 d=diagnostic('pending_selection',rule,{'section':'pending_evidence','item_index':index,'source_ids':[]},batch)
 d.update(selected_aliases=[safe_alias(x) for x in selected][:4],unknown_aliases=[safe_alias(x) for x in unknown][:5])
 if anchor is not None:d['anchor_alias']=safe_alias(anchor)
 raise old.MultiAIError(diagnostic=d)

def validate_output(store,cid,batch,raw):
 try:parsed=Analysis14.model_validate(raw)
 except ValidationError as exc:raise old.MultiAIError(diagnostic=schema_diagnostic(exc,{'stage':'format'},batch,raw)) from None
 if parsed.case_id!=cid or parsed.batch_sha256!=batch['batch_sha256']:_reject(batch,'case_or_batch_mismatch')
 from security import Settings
 current=prepare_case(store,cid,[d['document_id'] for d in batch['documents']],
                      Settings(provider=batch['provider'],model=batch['requested_model']))
 if current!=batch:_reject(batch,'pending_alias_context_mismatch')
 lookup={r['alias']:r['candidate_id'] for r in batch['alias_map']['entries']}
 try:Analysis14.model_validate(parsed.model_dump(),context={'allowed_aliases':frozenset(lookup)})
 except ValidationError:
  for index,row in enumerate(parsed.pending_evidence):
   unknown=list(dict.fromkeys(x for x in [row.anchor_alias,*row.evidence_aliases] if x not in lookup))
   if unknown:_reject(batch,'pending_alias_not_in_catalog',index,row.evidence_aliases,unknown,row.anchor_alias)
  _reject(batch,'pending_alias_context_validation_failed')
 by_pe={e['candidate_id']:e for e in batch['pending_catalog']['entries']}
 restored=[];seen=set();pe_selections=[]
 for index,row in enumerate(parsed.pending_evidence):
  aliases=row.evidence_aliases
  if len(set(aliases))!=len(aliases):_reject(batch,'pending_duplicate_evidence',index,aliases,anchor=row.anchor_alias)
  if row.anchor_alias not in aliases:_reject(batch,'pending_anchor_not_selected',index,aliases,anchor=row.anchor_alias)
  key=(tuple(sorted(aliases)),row.reasoning)
  if key in seen:_reject(batch,'pending_duplicate_question',index,aliases,anchor=row.anchor_alias)
  seen.add(key);ids=[lookup[x] for x in aliases];anchor=lookup[row.anchor_alias]
  pe_selections.append({'anchor_id':anchor,'evidence_ids':ids,'reasoning':row.reasoning})
  restored.append({'kind':'推断','text':by_pe[anchor]['quote'],'reasoning':row.reasoning,
     'sources':[{'source_id':by_pe[x]['source_id'],'quote':by_pe[x]['quote']} for x in ids]})
 intermediate=parsed.model_dump()
 intermediate.update(schema_version=old.CANDIDATE_SCHEMA_VERSION,prompt_version=old.CANDIDATE_PROMPT_VERSION,pending_evidence=restored)
 result=old.validate_candidate_output(store,cid,batch,intermediate)
 if len(result['pending_evidence'])!=len(restored):_reject(batch,'pending_restoration_count_mismatch')
 result.update(schema_version=SCHEMA_VERSION,prompt_version=PROMPT_VERSION,raw_output=parsed.model_dump(),
  candidate_selection={'catalog_version':CANDIDATE_VERSION,'catalog_sha256':build_event_catalog(batch)['sha256'],
                       'selection_ids':[c.candidate_id for c in parsed.timeline]},
  pending_selection={'catalog_version':CATALOG_VERSION,'catalog_sha256':batch['pending_catalog']['sha256'],
   'catalog':batch['pending_catalog'],'alias_map':batch['alias_map'],
   'raw_selection':[r.model_dump() for r in parsed.pending_evidence],'restored_pe_selection':pe_selections,
   'restored_references':deepcopy(result['pending_evidence'])})
 return result

def receipt_fields(batch,parsed):
 lookup={r['alias']:r['candidate_id'] for r in batch['alias_map']['entries']}
 return {'analysis_output_sha256':old.digest(parsed.model_dump()),'pending_catalog_version':CATALOG_VERSION,
  'pending_catalog_sha256':batch['pending_catalog']['sha256'],'pending_alias_version':ALIAS_VERSION,
  'pending_alias_map_sha256':batch['alias_map']['sha256'],
  'pending_alias_selection':[{'anchor_alias':r.anchor_alias,'evidence_aliases':r.evidence_aliases,
    'reasoning_sha256':hashlib.sha256(r.reasoning.encode()).hexdigest()} for r in parsed.pending_evidence],
  'pending_selection_ids':[{'anchor_id':lookup[r.anchor_alias],'evidence_ids':[lookup[x] for x in r.evidence_aliases],
    'reasoning_sha256':hashlib.sha256(r.reasoning.encode()).hexdigest()} for r in parsed.pending_evidence]}

def analyze_case(*args,**kwargs):return old.analyze_case(*args,**kwargs,_pending_protocol='1.4')

def validate_receipt_result(receipt,batch,result):
 parsed=Analysis14.model_validate(result['raw_output']);expected=receipt_fields(batch,parsed)
 expected.update(schema_version=SCHEMA_VERSION,prompt_version=PROMPT_VERSION,prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),
  batch_sha256=batch['batch_sha256'],case_id=batch['case_id'],candidate_version=CANDIDATE_VERSION,
  candidate_catalog_sha256=build_event_catalog(batch)['sha256'],candidate_selection_ids=[r.candidate_id for r in parsed.timeline],
  format_status='passed',evidence_status='passed',semantic_status='pending_human_review',provider_status='completed',call_status='response_received')
 if any(receipt.get(k)!=v for k,v in expected.items()):_reject(batch,'pending_receipt_mismatch')

def validate_saved_receipt(case,receipt,*,require_statements=True):
 """仅对1.4分派；从归档重建目录，核验选择与案件中的待核查记录，不新增确认。"""
 from case_store import CaseStore
 from security import Settings
 temp=CaseStore();temp._cases[case.case_id]=case
 selected=[d['document_id'] for d in receipt['document_snapshots']]
 batch=prepare_case(temp,case.case_id,selected,Settings(provider=receipt['provider'],model=receipt.get('requested_model','')))
 catalog=batch['pending_catalog'];alias_lookup={r['alias']:r['candidate_id'] for r in batch['alias_map']['entries']};lookup={e['candidate_id']:e for e in catalog['entries']}
 expected={'schema_version':SCHEMA_VERSION,'prompt_version':PROMPT_VERSION,'prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest(),
  'batch_sha256':batch['batch_sha256'],'pending_catalog_version':CATALOG_VERSION,'pending_catalog_sha256':catalog['sha256'],
  'candidate_version':CANDIDATE_VERSION,'candidate_catalog_sha256':build_event_catalog(batch)['sha256'],
  'pending_alias_version':ALIAS_VERSION,'pending_alias_map_sha256':batch['alias_map']['sha256']}
 if any(receipt.get(k)!=v for k,v in expected.items()):_reject(batch,'pending_receipt_mismatch')
 if not isinstance(receipt.get('analysis_output_sha256'),str) or not re.fullmatch(r'[a-f0-9]{64}',receipt['analysis_output_sha256']):_reject(batch,'pending_receipt_mismatch')
 event_ids=receipt.get('candidate_selection_ids');valid_events={c['candidate_id'] for c in build_event_catalog(batch)['candidates']}
 if not isinstance(event_ids,list) or len(event_ids)>24 or len(event_ids)!=len(set(event_ids)) or not set(event_ids)<=valid_events:_reject(batch,'pending_receipt_mismatch')
 selections=receipt.get('pending_selection_ids')
 if not isinstance(selections,list) or len(selections)>12:_reject(batch,'pending_receipt_mismatch')
 aliases=receipt.get('pending_alias_selection')
 if not isinstance(aliases,list) or len(aliases)!=len(selections):_reject(batch,'pending_receipt_mismatch')
 statements=receipt.get('pending_statement_ids')
 if require_statements and (not isinstance(statements,list) or len(statements)!=len(selections)):_reject(batch,'pending_receipt_mismatch')
 byid={r.statement_id:r for r in case.inferences};rows=[];seen=set()
 for i,item in enumerate(selections):
  if not isinstance(item,dict) or set(item)!={'anchor_id','evidence_ids','reasoning_sha256'}:_reject(batch,'pending_receipt_mismatch',i)
  ids=item['evidence_ids'];anchor=item['anchor_id']
  a=aliases[i]
  if not isinstance(a,dict) or set(a)!={'anchor_alias','evidence_aliases','reasoning_sha256'}:_reject(batch,'pending_receipt_mismatch',i)
  selected_aliases=a['evidence_aliases']
  if not isinstance(selected_aliases,list) or not 1<=len(selected_aliases)<=4 or any(x not in alias_lookup for x in selected_aliases) or a['anchor_alias'] not in alias_lookup:_reject(batch,'pending_receipt_mismatch',i)
  if a['anchor_alias'] not in selected_aliases or len(selected_aliases)!=len(set(selected_aliases)):_reject(batch,'pending_receipt_mismatch',i)
  if alias_lookup[a['anchor_alias']]!=anchor or [alias_lookup[x] for x in selected_aliases]!=ids or a['reasoning_sha256']!=item['reasoning_sha256']:_reject(batch,'pending_receipt_mismatch',i)
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
