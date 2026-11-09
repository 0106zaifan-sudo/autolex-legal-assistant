"""只读的证据解释层。仅比较有限字面命题，不认证身份、真实性或实际时间。"""
from copy import deepcopy
from datetime import date,datetime
import hashlib
import re
from ai_analysis import DATE_TIME,_explicit_time,AIError
from document_parser import PARSER_VERSION
from case_schema import CaseBundle
from evidence import verify_span,make_span
from timeline_candidates import NEUTRAL_HEADERS
from workspace_bundle import validate_graph

REVIEW_VERSION='conflict-review/1'
MAX_RELATIONS=300
MAX_CONTEXT_CHARS=24000
ID=re.compile(r'事件编号[：:]\s*([A-Za-z0-9_-]+)')
PREFIX=re.compile(r'事件编号[：:]\s*([A-Za-z0-9_-]+)[；;]\s*')
UNSAFE=re.compile(r'可能|如果|假如|是否|未必|并非|不是|不能|尚未|未曾|没有|否认|转述|引述|据称|所谓|“|”|「|」|["\']')
CLOCK_DOUBT=re.compile(r'时区|时钟|UTC|GMT|北京时间|[+-]\d{2}:?\d{2}|\d{2}:\d{2}Z',re.I)
PREDICATES={
 '系统已发出接管提示':('system_emit','系统','接管提示',True),
 '系统未发出接管提示':('system_emit','系统','接管提示',False),
 '车辆已输出接管提示':('vehicle_output','车辆','接管提示',True),
 '车辆未输出接管提示':('vehicle_output','车辆','接管提示',False),
 '驾驶人已收到接管提示':('driver_receive','驾驶人','接管提示',True),
 '驾驶人未收到接管提示':('driver_receive','驾驶人','接管提示',False),
 '驾驶人已感知接管提示':('driver_perceive','驾驶人','接管提示',True),
 '驾驶人未感知接管提示':('driver_perceive','驾驶人','接管提示',False),
}
LIMITATIONS=[
 '仅比较原文文字及字面角色，不确认材料真实、现实主体身份、事件同一性或法律矛盾。',
 '时区和来源时钟未认证；字面差值不是实际时间间隔，不确定先后、因果或最终事故时间。',
 '有限闭集规则不解释复杂否定、引语或未支持措辞；信息缺失不等于证据不存在。',
]

class ConflictReviewError(ValueError):
    def __init__(self,code):
        self.code=code;super().__init__('审查未生成有效结论（'+code+'）；请核验来源，不自动修复原文。')


def require(condition,code):
    if not condition:raise ConflictReviewError(code)


def checked_case(store,cid):
    try:
        case=store.get_case(cid)
        # 只验证审查相关子图；不重放无关事实确认，不调用confirm_fact。
        projected=CaseBundle(schema_version=case.schema_version,case_id=cid,title=case.title,documents=case.documents,
                             evidence=case.evidence,relations=case.relations,relation_reviews=case.relation_reviews,
                             analysis_receipts=case.analysis_receipts)
        temp=type(store)();temp._cases[cid]=projected
        validate_graph(temp,cid)
        return case
    except Exception:raise ConflictReviewError('case_graph_invalid') from None


def remove_neutral_headers(text):
    lines=text.splitlines(keepends=True)
    while lines and lines[0].strip() in NEUTRAL_HEADERS:lines.pop(0)
    return ''.join(lines)


def side(case,eid):
    require(eid in case.evidence,'evidence_not_in_case')
    span=case.evidence[eid];require(span.document_id in case.documents,'document_not_in_case')
    doc=case.documents[span.document_id]
    require(doc.document_id==span.document_id and doc.parser_version==PARSER_VERSION,'source_identity_or_parser')
    try:verify_span(case.case_id,doc,span)
    except Exception:raise ConflictReviewError('evidence_binding_invalid') from None
    require(doc.parse_report.get('file_sha256')==doc.file_sha256 and doc.parse_report.get('parser_version')==doc.parser_version,'source_report_mismatch')
    unit=doc.units[span.unit_index]['text'];require(len(unit)<=MAX_CONTEXT_CHARS,'context_limit')
    prefix=remove_neutral_headers(unit[:span.start]).strip()
    before_ok=not prefix or PREFIX.fullmatch(prefix) is not None
    prior_units_ok=all(not u['text'].strip() or u['text'].strip() in NEUTRAL_HEADERS for u in doc.units[:span.unit_index])
    after=unit[span.end:].lstrip(' \t\r\n')
    continuation=bool(re.match(r'(?:上述|以上|前述|该|此|本记录|均|时区|时钟|时间基准|事故时间|时间记载)',after))
    before_boundary=span.start==0 or unit[:span.start].rstrip(' \t')[-1:] in '。！？!?；;\r\n'
    after_boundary=span.end==len(unit) or span.quote[-1:] in '。！？!?；;\r\n' or unit[span.end:].lstrip(' \t')[:1] in '。！？!?；;\r\n'
    scope_ok=before_ok and prior_units_ok and before_boundary and after_boundary and not continuation
    analyzed=remove_neutral_headers(span.quote).strip()
    matches=list(ID.finditer(prefix+'\n'+analyzed))
    event_id=matches[0].group(1) if scope_ok and len(matches)==1 else None
    body=analyzed
    metadata=PREFIX.match(body)
    if metadata:body=body[metadata.end():]
    identity_span=None
    if event_id:
        # ID可来自引文前中性元信息，但必须另外绑定到同一原始单元的准确范围。
        search_end=span.end
        candidates=[m for m in ID.finditer(unit[:search_end]) if m.group(1)==event_id]
        if len(candidates)==1:
            m=candidates[0];identity_span=make_span(case.case_id,doc,span.unit_index,m.start(),m.end(),m.group()).model_dump()
        else:event_id=None
    parse_ok=doc.parse_report.get('status')=='parsed' and not doc.parse_report.get('requires_acknowledgement')
    issues=doc.parse_report.get('issues',[])
    unit_read=any(item.get('unit_index')==span.unit_index and item.get('status')=='read' for item in doc.parse_report.get('items',[]))
    table_warning_only=(doc.file_name.lower().endswith('.pdf') and doc.parse_report.get('status')=='partial'
                        and bool(issues) and all(issue.get('code')=='pdf_table_coverage_unverified' for issue in issues))
    comparison_eligible=unit_read and (parse_ok or table_warning_only)
    # 提示只定位到当前已保存引文及同一记录行，避免把别的记录中的缺失归给本事件。
    line_start=unit.rfind('\n',0,span.start)+1
    effective_end=span.end
    while effective_end>span.start and unit[effective_end-1] in '\r\n':effective_end-=1
    line_end=unit.find('\n',effective_end)
    if line_end<0:line_end=len(unit)
    gaps=[]
    record_text=unit[line_start:line_end]
    gap_scope_ok=(scope_ok and comparison_eligible and not UNSAFE.search(record_text) and not re.search(r'主张|陈述|认为|称|表示|推测|待核实',record_text) and len(ID.findall(record_text))<=1)
    for m in re.finditer(r'原始日志未提供',record_text):
        before_gap=record_text[:m.start()].rstrip();after_gap=record_text[m.end():].strip()
        if not gap_scope_ok or (before_gap and before_gap[-1] not in '。；;\r\n') or after_gap not in ('','。'):continue
        a=line_start+m.start();b=line_start+m.end()
        gap=make_span(case.case_id,doc,span.unit_index,a,b,unit[a:b]).model_dump()
        gaps.append(gap)
    value={'evidence_id':eid,'document_id':doc.document_id,'file_name':doc.file_name,'file_sha256':doc.file_sha256,
           'parsed_text_sha256':doc.parsed_text_sha256,'parser_version':doc.parser_version,'unit_index':span.unit_index,
           'location':span.location,'start':span.start,'end':span.end,'quote':span.quote,'quote_sha256':hashlib.sha256(span.quote.encode()).hexdigest(),
           'context':unit,'scope_valid':scope_ok,'parse_complete':parse_ok,'text_comparison_eligible':comparison_eligible,
           'parse_issue_codes':[i.get('code') for i in issues],'event_id':event_id,'event_identity_source':identity_span,'gaps':gaps}
    value['predicate']=predicate(body,scope_ok and comparison_eligible)
    value['time']=time_record(body,scope_ok,comparison_eligible)
    if CLOCK_DOUBT.search(unit[line_start:line_end]):
        value['time']['rule']='clock_or_timezone_unconfirmed'
    return value


def predicate(body,scope_ok):
    result={'stage':None,'subject':None,'object':None,'polarity':None,'attribution':None,'rule':'unsupported_or_ambiguous_wording'}
    if not scope_ok or UNSAFE.search(body):return result
    text=body
    attribution=re.match(r'(企业说明|企业主张|驾驶人陈述|驾驶人主张)：',text)
    if attribution:result['attribution']=attribution.group(1);text=text[attribution.end():]
    if text.endswith('。'):text=text[:-1]
    if text not in PREDICATES:return result
    stage,subject,obj,polarity=PREDICATES[text]
    return {**result,'stage':stage,'subject':subject,'object':obj,'polarity':polarity,'rule':'closed_literal_predicate'}


def time_record(body,scope_ok,parse_ok):
    times=list(DATE_TIME.finditer(body))
    result={'time_text':None,'time_texts':[m.group() for m in times],'precision':'unknown','normalized':None,'rule':'unsupported_collision_statement'}
    if not scope_ok:return {**result,'rule':'context_scope_unproven'}
    if not parse_ok:return {**result,'rule':'parse_coverage_incomplete'}
    if CLOCK_DOUBT.search(body):return {**result,'rule':'clock_or_timezone_unconfirmed'}
    if len(times)!=1:return {**result,'rule':'time_missing_or_multiple'}
    match=times[0]
    try:precision,normalized,_=_explicit_time(match.group(),body)
    except AIError:return {**result,'rule':'time_unsupported_or_uncertain'}
    # 不按关键词判断事件；只接受完整碰撞记录语法及已知独立的日志未提供尾句。
    expected=re.fullmatch(r'(?:现场记录：|摘要：)?'+re.escape(match.group())+r'车辆发生碰撞。?(?:原始日志未提供。?)?',body)
    if expected is None:return result
    return {**result,'time_text':match.group(),'precision':precision,'normalized':normalized,'rule':'single_explicit_collision_record'}


def compare_sides(left,right):
    same=left['event_id'] is not None and left['event_id']==right['event_id']
    different=left['event_id'] is not None and right['event_id'] is not None and not same
    identity={'status':'same_candidate_event' if same else ('different_event' if different else 'unproven'),
              'event_id':left['event_id'] if same else None,'basis':'仅相同原文事件编号；不是现实事件同一性认证'}
    time={'literal_delta_seconds':None,'literal_delta_days':None,'display':None,'reliable_comparison':False,
          'actual_delta_seconds':None,'selected_time':None,'rule':'event_identity_unproven',
          'clock_status':'未确认时区与时钟基准；无法可靠比较实际时刻，不校准时钟'}
    p={'rule':'unsupported_or_ambiguous_wording','same_proposition':False}
    assessment=None if different else 'needs_verification'
    if same:
        a,b=left['predicate'],right['predicate']
        if a['stage'] and b['stage']:
            if (a['stage'],a['subject'],a['object'])!=(b['stage'],b['subject'],b['object']):
                p['rule']='different_behavior_stages';assessment='related'
            else:
                p['same_proposition']=True
                if a['polarity']==b['polarity']:p['rule']='same_proposition_same_polarity';assessment='support_candidate'
                else:p['rule']='same_proposition_opposite_polarity';assessment='inconsistency_candidate'
        a,b=left['time'],right['time']
        if a['rule']=='single_explicit_collision_record' and b['rule']=='single_explicit_collision_record':
            if a['precision']!=b['precision']:time['rule']='precision_mismatch'
            else:
                if a['precision']=='date':
                    delta=(date.fromisoformat(b['normalized'])-date.fromisoformat(a['normalized'])).days
                    time.update(literal_delta_days=delta,display=f'{abs(delta)}天（日期文本差）')
                else:
                    delta=int((datetime.fromisoformat(b['normalized'])-datetime.fromisoformat(a['normalized'])).total_seconds())
                    time.update(literal_delta_seconds=delta,display=f'{abs(delta)//60}分钟（{abs(delta)}秒字面差）' if abs(delta)%60==0 else f'{abs(delta)}秒字面差')
                time['rule']='literal_difference_only_unverified_clocks';assessment='inconsistency_candidate' if delta else 'support_candidate'
        else:time['rule']='time_not_comparable'
    suggestions=[]
    if time['literal_delta_seconds'] is not None or time['literal_delta_days'] is not None:
        suggestions.append('检查建议：核查各来源时钟基准、时区、时间精度及原始记录；字面差异不能决定哪个时间正确。')
    elif left['time']['time_texts'] or right['time']['time_texts']:
        suggestions.append('检查建议：先核对事件标识、完整日期、时间精度及解析覆盖；当前无法可靠比较，不自动补全时间。')
    if left['predicate']['stage'] or right['predicate']['stage']:
        suggestions.append('检查建议：分别核查提示发出、车辆输出、驾驶人接收与感知环节的相应证据；不假定任何日志必然存在。')
    if p['same_proposition']:
        suggestions.append('检查建议：核对字面主体是否确为同一实体、同一时段与同一事件；不一致候选仍不是事实或法律认定。')
    if left['gaps'] or right['gaps']:
        suggestions.append('检查建议：材料明确记载原始日志未提供，仅表示当前材料范围的缺口，不代表现实中不存在该日志；核查是否另有原始记录。')
    if not same:suggestions.append('检查建议：事件身份尚未一致确认或编号不同，不凭相同关键词合并材料。')
    return {'identity':identity,'time':time,'predicate':p,'assessment_type':assessment,'suggestions':suggestions}


def _review_pair(case,left_id,right_id):
    left,right=side(case,left_id),side(case,right_id)
    require(left['document_id']!=right['document_id'] and left['file_sha256']!=right['file_sha256'],'sources_not_independent')
    return {'version':REVIEW_VERSION,'case_id':case.case_id,'left':left,'right':right,**compare_sides(left,right),
            'verification':'待人工核验','limitations':list(LIMITATIONS)}


def review_pair(store,cid,left_id,right_id):
    try:return _review_pair(checked_case(store,cid),left_id,right_id)
    except ConflictReviewError:raise
    except Exception:raise ConflictReviewError('review_binding_failed') from None


def build_workbench(store,cid):
    case=checked_case(store,cid);require(len(case.relations)<=MAX_RELATIONS,'relation_limit')
    result=[]
    try:
        for relation in case.relations:
            row=_review_pair(case,relation.left_id,relation.right_id)
            history=[r.model_dump() for r in case.relation_reviews if r.relation_id==relation.relation_id]
            row.update(relation_id=relation.relation_id,original_candidate=relation.model_dump(),history=history,
                       latest_review=deepcopy(history[-1]) if history else None)
            result.append(row)
        return result
    except ConflictReviewError:raise
    except Exception:raise ConflictReviewError('review_binding_failed') from None
