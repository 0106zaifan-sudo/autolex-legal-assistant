"""调用前的保守句段清单；选择不是事实认定，不修改原文或放宽绑定。"""
from copy import deepcopy
import hashlib
import json
import re
from ai_analysis import (SENTENCE_END, CLAIM_MARKERS, DATE_TIME, AIError, build_sources,
                         empty_analysis, validate_analysis, _explicit_time)

CANDIDATE_VERSION = 'event-candidates/1'
MAX_CANDIDATES = 64
NEUTRAL_HEADERS = frozenset({'【模拟材料：完全虚构，不是真实案件；来源及真实性未核验】'})
IDENTIFIER = re.compile(r'事件编号[：:]\s*[A-Za-z0-9_-]+[；;]?')
EVENT_WORD = re.compile(r'碰撞|事故|接管|提示|停车|维修|接收|交付|制动|启动|关闭|开启|行驶')
SPEAKER = re.compile(r'^(?:驾驶人|驾驶员|企业|公司)(?:主张|称|陈述|表示|认为|否认|未|已)')


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def build_event_catalog(batch):
    candidates=[];excluded=[]
    for did,record in sorted(batch['records'].items()):
        sources=[s for s in batch['sources'] if s['document_id']==did]
        local=build_sources(record)
        inherited_scope=False
        for ui,unit in enumerate(record['units']):
            # 跨句/行语义范围不能由标点证明独立；只有中性元信息之前缀可跳过。
            substantive_before=inherited_scope
            cursor=0
            for line in unit['text'].splitlines(keepends=True):
                body=line.rstrip('\r\n')
                if body.strip(' \t') in NEUTRAL_HEADERS:
                    cursor+=len(line);continue
                begin=0
                boundaries=list(SENTENCE_END.finditer(body))
                endpoints=[m.end() for m in boundaries]
                if not endpoints or endpoints[-1]!=len(body):endpoints.append(len(body))
                for end in endpoints:
                    a,b=begin,end;begin=end
                    while a<b and body[a] in ' \t':a+=1
                    while b>a and body[b-1] in ' \t':b-=1
                    quote=body[a:b]
                    if not quote:continue
                    if not substantive_before and IDENTIFIER.fullmatch(quote):continue
                    start,stop=cursor+a,cursor+b
                    match=[s for s in sources if s['unit_index']==ui and s['start']<=start and stop<=s['end']
                           and s['text'][start-s['start']:stop-s['start']]==quote]
                    reason=None
                    if substantive_before:reason='context_dependency_not_proven'
                    elif not EVENT_WORD.search(quote):reason='not_event_segment'
                    elif len(match)!=1 or match[0]['text'].count(quote)!=1:reason='not_unique_in_source'
                    substantive_before=True
                    if reason:
                        excluded.append({'document_id':did,'unit_index':ui,'start':start,'end':stop,'rule':reason});continue
                    source=match[0]
                    ref={'source_id':batch['local_ids'][source['source_id']],'quote':quote}
                    kind='主张' if CLAIM_MARKERS.search(quote) or SPEAKER.search(quote) else '事实'
                    row={'kind':kind,'text':quote,'reasoning':'','sources':[deepcopy(ref)],'event_source':deepcopy(ref),
                         'time_state':'unknown','time_precision':'unknown','time_text':'未知','time_source':None}
                    times=list(DATE_TIME.finditer(quote))
                    if len(times)==1:
                        try:
                            precision,_,_=_explicit_time(times[0].group(),quote)
                            row.update(time_state='explicit',time_precision=precision,time_text=times[0].group(),time_source=deepcopy(ref))
                        except AIError:pass  # 保留未知，不删时间、不猜精度。
                    raw=empty_analysis(record);raw['timeline']=[row]
                    try:validate_analysis(raw,record,local)
                    except AIError:
                        excluded.append({'document_id':did,'unit_index':ui,'start':start,'end':stop,'rule':'legacy_binding_rejected'});continue
                    item={k:source[k] for k in ('case_id','document_id','file_sha256','parsed_text_sha256','parser_version','source_id','unit_index','location')}
                    item.update(start=start,end=stop,quote=quote,quote_sha256=hashlib.sha256(quote.encode()).hexdigest(),
                                allowed_kinds=['主张'] if kind=='主张' else ['事实','主张'],
                                time_state=row['time_state'],time_precision=row['time_precision'],time_text=row['time_text'])
                    item['candidate_id']='CE_'+digest([CANDIDATE_VERSION,item])[:24]
                    candidates.append(item)
                    if len(candidates)>MAX_CANDIDATES:raise ValueError('候选句段超过64项，未发送；不静默截断。')
                cursor+=len(line)
            # 声明/主张/否定或引出语不能因解析单元切换而失去作用域。
            unit_text=unit['text'].strip()
            if unit_text not in NEUTRAL_HEADERS and (CLAIM_MARKERS.search(unit_text) or SPEAKER.search(unit_text)
                    or re.search(r'以下|如下|不成立|并非|[:：]\s*$',unit_text)):
                inherited_scope=True
    if len({c['candidate_id'] for c in candidates})!=len(candidates):raise ValueError('候选编号冲突，未发送。')
    value={'version':CANDIDATE_VERSION,'candidates':candidates,'excluded':excluded}
    return {**value,'sha256':digest(value)}
