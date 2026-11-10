"""固定规则映射。永不序列化异常正文、Pydantic input、quote或完整loc。"""
import re,json

SECTIONS=('facts','timeline','pending_evidence','relations')
RULES={
 '事件引文没有唯一、明确且完整的时间，请拆分事件或标记未知；禁止借用其他事件日期。':'time_not_uniquely_supported',
 '原文包含尚未支持的毫秒或时区，请标记未知，不能截掉额外精度。':'time_precision_unsupported',
 '原文日期或时刻无法解析，请标记未知并人工核验。':'time_unparseable',
 '时间线必须使用单一事件原文引文；不能拼接其他事件证据或推断成事件。':'timeline_primary_reference_required',
 '事件正文必须完整等于主引文，不能用大段材料支撑另一事件结论。':'timeline_text_not_primary_quote',
 '事件引文跨句或跨行，请拆为独立原文事件；不能合并多个事件的时间。':'timeline_multi_sentence',
 '事件引文不是完整原文句段，可能截掉主张、否定或时间限定，结果已拒绝。':'timeline_incomplete_sentence',
 '未知时间必须明确标为未知，不能附带具体日期、时间来源或伪造精度。':'unknown_time_fields_invalid',
 '时间来源必须绑定本事件的同一主引文，不能借用维修或其他段落日期。':'time_reference_not_event',
 '时间精度与完整原文不一致，禁止自行补充或丢弃时分秒。':'time_precision_mismatch',
 '模型引证未通过原文校验（来源不存在、引文不一致或位置有歧义），结果已拒绝。':'document_reference_invalid',
 '原文定位校验失败，结果已拒绝。':'document_span_invalid',
 '模型补写了非原文事实摘要，结果已拒绝。':'text_not_in_quote',
 '模型把含主张或待核实标记的材料标成事实，结果已拒绝。':'claim_or_uncertainty_as_fact',
 '争议焦点和待核实证据必须标为推断，结果已拒绝。':'inference_kind_required',
 '推断缺少待核实标识，结果已拒绝。':'inference_prefix_missing',
 '推断必须以待核实问题呈现，结果已拒绝。':'inference_question_required',
 '推断包含法律或案例引用，结果已拒绝。':'inference_authority_forbidden',
 '事实或主张不允许附加未经核验的生成说明，结果已拒绝。':'non_inference_reasoning_forbidden',
 'AI 模块不输出法律或案例引用，请使用原文规则提取并人工核验。':'authority_forbidden',
 '同一原文事件被重复输出，请人工核验，不自动合并或选取。':'timeline_duplicate_event',
 '旧版或未知分析Schema不兼容，请按2.0重新分析；不能静默复用旧证据绑定。':'document_schema_version_mismatch',
 '分析绑定的文件、解析快照或版本不匹配，请重新分析；禁止跨文件复用出处。':'document_context_mismatch',
 '来源块不是当前文件/解析快照的完整来源清单，结果已拒绝。':'document_source_manifest_mismatch',
 '解析版本已变更或未记录，请重新读取原文件，不能复用旧解析快照。':'parser_version_mismatch',
 '正文超过 AI 输入上限（24000 字符或80块），请拆分文件后分析；未发送任何内容。':'document_input_limit',
 '没有可分析的正文，请先检查扫描件或空文件。':'document_text_missing',
 '输出问题存在重复疑问表达，未自动重写，结果需重新核查。':'repeated_question_phrase',
 '待核实条目超过兼容上限，结果已拒绝，未截断或丢弃问题。':'pending_capacity_exceeded',
}

def diagnostic(stage,rule,context,batch):
    known={s['source_id']:s for s in batch.get('sources',[])}
    ids=[]
    for value in context.get('source_ids',[]):
        safe=value if value in known or re.fullmatch(r'MD_[a-f0-9]{24}',value or '') else 'rejected_source_id'
        if safe not in ids:ids.append(safe)
    section=context.get('section')
    index=context.get('item_index')
    trigger=context.get('trigger_source_id')
    trigger=trigger if trigger in known or (isinstance(trigger,str) and re.fullmatch(r'MD_[a-f0-9]{24}',trigger)) else ('rejected_source_id' if trigger else None)
    return {'version':'multidoc-diagnostic/v1','stage':stage,'rule':rule,
            'section':section if section in SECTIONS else None,
            'item_index':index if type(index) is int and index>=0 else None,'item_index_base':0,
            'source_ids':ids,'trigger_source_id':trigger,'document_ids':sorted({known[s]['document_id'] for s in ids if s in known})}

# 只公开Schema已知字段名和数组序号；未知字段名也可能是模型原文，不能照抄loc。
SCHEMA_ERROR_TYPES=frozenset(('json_invalid','json_type','missing','literal_error','extra_forbidden',
 'model_type','model_attributes_type','string_type','list_type','dict_type','int_type','float_type','bool_type',
 'none_required','string_pattern_mismatch','string_too_short','string_too_long','too_short','too_long',
 'greater_than','greater_than_equal','less_than','less_than_equal','value_error','assertion_error'))
_SCHEMA_REF={'source_id':{},'quote':{}}
_SCHEMA_ITEM={'kind':{},'text':{},'reasoning':{},'sources':{'[]':_SCHEMA_REF}}
_SCHEMA_TIMELINE={**_SCHEMA_ITEM,'event_source':_SCHEMA_REF,'time_source':_SCHEMA_REF,
 'time_state':{},'time_precision':{},'time_text':{},'candidate_id':{}}
_SCHEMA_PENDING={**_SCHEMA_ITEM,'anchor_id':{},'evidence_ids':{'[]':{}}}
_SCHEMA_PATHS={k:{} for k in ('schema_version','prompt_version','parser_version','document_sha256',
 'parsed_text_sha256','case_id','batch_sha256','pending_catalog_sha256')}
_SCHEMA_PATHS.update(facts={'[]':_SCHEMA_ITEM},timeline={'[]':_SCHEMA_TIMELINE},
 pending_evidence={'[]':_SCHEMA_PENDING},issues={'[]':_SCHEMA_ITEM},
 relations={'[]':{'left':_SCHEMA_REF,'right':_SCHEMA_REF,'relation_type':{},'reasoning':{}}})
MAX_SCHEMA_ERRORS=20
MAX_SCHEMA_PATH_DEPTH=8
MAX_SCHEMA_INDEX=1000


def _schema_path(loc):
    node=_SCHEMA_PATHS;path=[];redacted=False
    for component in loc:
        if len(path)>=MAX_SCHEMA_PATH_DEPTH-1:
            path.append('<redacted>');redacted=True;break
        if type(component) is int and '[]' in node and 0<=component<=MAX_SCHEMA_INDEX:
            path.append(component);node=node['[]']
        elif isinstance(component,str) and component!='[]' and component in node:
            path.append(component);node=node[component]
        else:
            path.append('<redacted>');redacted=True;break
    return path,redacted


def _schema_category(kind,path):
    if kind=='json_invalid':return 'json_parse'
    if kind=='missing':return 'missing_field'
    if kind=='literal_error':return 'version_mismatch' if path in (['schema_version'],['prompt_version'],['parser_version']) else 'literal_value'
    if kind=='extra_forbidden':return 'extra_field'
    if kind in ('json_type','model_type','model_attributes_type','string_type','list_type','dict_type','int_type','float_type','bool_type','none_required'):return 'field_type'
    if kind in ('string_pattern_mismatch','string_too_short','string_too_long','too_short','too_long','greater_than','greater_than_equal','less_than','less_than_equal'):return 'value_constraint'
    return 'other_schema_error'


def _schema_summary(problems,total):
    counts={};details=[]
    for problem in problems:
        kind=problem.get('type')
        kind=kind if kind in SCHEMA_ERROR_TYPES else 'other_validation_error'
        counts[kind]=counts.get(kind,0)+1
        if len(details)<MAX_SCHEMA_ERRORS:
            path,redacted=_schema_path(problem.get('loc',()))
            details.append({'type':kind,'category':_schema_category(kind,path),'path':path,'path_redacted':redacted})
    return {'schema_error_version':'schema-errors/v1','schema_error_count':total,
            'schema_errors':details,'schema_errors_truncated':total>len(details),
            'schema_error_type_counts':counts}


def schema_diagnostic(error,context,batch,raw=None):
    context=dict(context)
    problems=error.errors(include_input=False,include_context=False,include_url=False)
    for problem in problems:
        loc=problem.get('loc',())
        if loc and loc[0] in SECTIONS and context.get('section') is None:
            context['section']=loc[0]
            if len(loc)>1 and type(loc[1]) is int:context['item_index']=loc[1]
            break
    index=context.get('item_index')
    if type(index) is not int or not 0<=index<=MAX_SCHEMA_INDEX:
        context['item_index']=None
    if not context.get('source_ids') and context.get('section') and type(context.get('item_index')) is int:
        try:
            payload=json.loads(raw) if isinstance(raw,str) else raw
            row=payload[context['section']][context['item_index']]
            refs=row.get('sources',[]) if context['section']!='relations' else [row.get('left',{}),row.get('right',{})]
            context['source_ids']=[r['source_id'] for r in refs if isinstance(r,dict) and isinstance(r.get('source_id'),str)]
        except (ValueError,KeyError,IndexError,TypeError,AttributeError):pass
    result=diagnostic('format' if context.get('stage')=='format' else 'document_format','schema_rejected',context,batch)
    result.update(_schema_summary(problems,error.error_count()))
    return result
