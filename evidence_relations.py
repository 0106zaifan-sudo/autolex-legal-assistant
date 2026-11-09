"""有限字面比较，不作真实性或法律矛盾判断。仅对用户保存的锚点比较。"""
import re
from ai_analysis import DATE_TIME,_explicit_time,AIError


def compare_quotes(a,b):
    def event(t):
        m=re.search(r'事件编号[:：]\s*([A-Za-z0-9_-]+)',t)
        return m.group(1) if m else None
    ea,eb=event(a),event(b)
    topics=[t for t in ('碰撞','接管提示','原始日志') if t in a and t in b]
    if not topics or (ea and eb and ea!=eb):return None
    if not ea or not eb:return 'needs_verification','event_identity_missing','主题相同但缺少共同事件标识，不能判定支持或冲突'
    if any(t in a+b for t in ('未提供','待核实','不明','可能','是否','否认','并非','不是','如果','假如','转述','引述','“','”')):
        return 'needs_verification','uncertain_or_missing','仅说明当前材料范围的缺失或歧义，不代表证据不存在'
    def predicate(t):
        found=[]
        for role in ('系统已发出接管提示','系统未发出接管提示','驾驶人已收到接管提示','驾驶人未收到接管提示'):
            if role in t:found.append(role)
        return found[0] if len(found)==1 else None
    pa,pb=predicate(a),predicate(b)
    if pa and pb:
        rolea='emit' if '发出' in pa else 'receive';roleb='emit' if '发出' in pb else 'receive'
        if rolea!=roleb:return 'related','emit_is_not_receive','发出与收到是不同命题，不能直接认定矛盾'
        return ('support_candidate' if pa==pb else 'inconsistency_candidate','closed_predicate_comparison','同一事件标识的同一字面命题对照，仍需核对主体、语境和材料独立性')
    if '发生碰撞' in a and '发生碰撞' in b and not any(x in a+b for x in ('未发生','否认','如果')):
        times=[]
        for text in (a,b):
            m=DATE_TIME.search(text)
            if not m:return 'needs_verification','time_missing','碰撞时间未明确，不能补时间'
            try:times.append(_explicit_time(m.group(),text)[:2])
            except AIError:return 'needs_verification','time_ambiguous','时间不唯一或不受支持，需人工核对'
        if times[0][0]!=times[1][0]:return 'needs_verification','precision_mismatch','时间精度不同，不能当作冲突'
        return ('support_candidate' if times[0]==times[1] else 'inconsistency_candidate','event_time_comparison','字面时间相同或不同；时区、时钟校准、来源独立性均未确认')
    return 'related','shared_topic_only','仅主题关联，不能据关键词判定支持或法律矛盾'
