"""审查探针：构造纯模拟输入验证现有校验边界，不调用模型，不修改业务代码。
在仓库根目录运行：python docs/audit/probes.py
断言描述的是审查基线5307554的行为；修复后应将其改写为正式回归测试。
"""
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from docx import Document
from core import extract, summary
from ai_analysis import Analysis, AIError, build_sources, validate_analysis


def record(*lines):
    doc=Document()
    doc.add_paragraph('【模拟数据：仅供代码审查，不是真实案件】')
    for line in lines:doc.add_paragraph(line)
    data=io.BytesIO();doc.save(data)
    return extract('模拟_审查.docx',data.getvalue())


def payload(section, item):
    result={'facts':[],'timeline':[],'issues':[],'pending_evidence':[]}
    result[section]=[item]
    return Analysis.model_validate(result)


def item(kind,text,refs,reasoning=''):
    return {'kind':kind,'text':text,'reasoning':reasoning,
            'sources':[{'source_id':source_id,'quote':quote} for source_id,quote in refs]}


def run():
    out=[]
    collision='模拟记录A：2026年11月1日08:30，车辆在封闭场地发生碰撞。'
    repair='模拟记录B：2026年11月2日09:00，车辆完成维修。'
    r=record(collision,repair)
    row=item('事实',collision,[('S002',collision),('S003',repair)])
    row['time_text']='2026年11月2日09:00'
    result=validate_analysis(payload('timeline',row),r,build_sources(r))
    assert result['sections']['timeline'][0]['time_text'] in repair
    out.append({'probe':'A_time_event_mismatch','observed':'accepted',
                'event':collision,'bound_time':row['time_text'],
                'meaning':'合法引文仍可拼出事件与时间错配；这是校验器构造输入，不是模型实测输出。'})

    r=record(collision)
    row=item('推断',collision,[('S002',collision)],'待核实推断：模拟驾驶人饮酒是否导致此次事故？')
    result=validate_analysis(payload('issues',row),r,build_sources(r))
    assert '饮酒' not in ''.join(u['text'] for u in r['units'])
    out.append({'probe':'B_unsupported_hypothesis','observed':'accepted',
                'reasoning':result['sections']['issues'][0]['reasoning'],
                'meaning':'引证存在并不能支撑生成问题中的新增假设。'})

    recollection='模拟调查笔录：驾驶人回忆车辆没有发出接管提示。'
    r=record(recollection)
    row=item('事实',recollection,[('S002',recollection)])
    result=validate_analysis(payload('facts',row),r,build_sources(r))
    assert result['sections']['facts'][0]['kind']=='事实'
    out.append({'probe':'C_claim_marker_miss','observed':'accepted_as_fact',
                'source':recollection,'meaning':'含个人回忆的陈述可能漏过关键词分类拦截。'})

    mixed=collision+'驾驶人主张未收到提示。'
    r=record(mixed)
    row=item('事实',collision,[('S002',collision)])
    try:validate_analysis(payload('facts',row),r,build_sources(r))
    except AIError:observed='rejected'
    else:raise AssertionError('基线行为发生变化')
    out.append({'probe':'D_claim_marker_overreject','observed':observed,
                'meaning':'引文本身只是记录摘录，同块其他主张字样也会使其被拒绝。'})

    r=record(*[f'模拟短段落{i}。' for i in range(81)])
    try:build_sources(r)
    except AIError:observed='rejected_at_source_limit'
    else:raise AssertionError('基线行为发生变化')
    out.append({'probe':'E_short_many_paragraphs','observed':observed,
                'characters':sum(len(u['text']) for u in r['units']),
                'meaning':'远小于24000字的多段材料仍可能触发80块上限；是安全拒绝，不是静默截断。'})

    phrase='辅助驾驶功能退出'
    r=record('甲'*995+phrase+'乙'*10)
    sources=build_sources(r)
    assert phrase in r['units'][1]['text'] and not any(phrase in s['text'] for s in sources)
    out.append({'probe':'F_chunk_boundary','observed':'contiguous_source_phrase_unquotable',
                'phrase':phrase,'meaning':'原文中的连续短语跨越无重叠分块后无法作为单条连续引文返回。'})

    r=record('原审法院为虚构甲市人民法院。','参考读物：《模拟辅助驾驶科普手册》。')
    values=summary(r)
    assert values['法院']=='原审法院为虚构甲市人民法院'
    assert values['法律依据']=='《模拟辅助驾驶科普手册》'
    out.append({'probe':'G_regex_candidates','observed':'prefix_and_book_as_candidates',
                'court':values['法院'],'legal_basis':values['法律依据'],
                'meaning':'字段只是待核验候选，不能当成规范法院名或权威法源。'})
    return out


if __name__=='__main__':
    print(json.dumps({'baseline':'53075548bcf7f0dd814b0d2e02d65ae170d7f2dd',
                      'paid_api_calls':0,'probe_count':7,'results':run()},ensure_ascii=False,indent=2))
