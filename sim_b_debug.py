"""固定SIM_B的人工离线反例；不导入SDK调用、Secrets加载或案件写入接口。"""
import hashlib
import json
from ai_analysis import (AIError, Analysis, PROMPT, empty_analysis, build_sources, validate_analysis)
from sample_debug import fixed_record, capture_rejected_output, read_capture


def reproduction_cases():
    record = fixed_record('SIM_B')
    sources = build_sources(record)
    def item(index, kind, *, text=None, quote=None, reasoning=''):
        source = sources[index-1]
        quote = source['text'] if quote is None else quote
        return {'kind':kind,'text':quote if text is None else text,'reasoning':reasoning,
                'sources':[{'source_id':source['source_id'],'quote':quote}]}
    def payload(section, row):
        result = empty_analysis(record);result[section] = [row];return result
    full = empty_analysis(record)
    full['facts'] = [item(i,'主张' if i in (4,5) else '事实') for i in range(1,7)]
    return record, [
        ('s006_as_fact_index_5', full, '整句的未核实完整性被kind=事实承载，应拒绝；Schema没有“已确认事实”枚举。'),
        ('directory_excerpt_full_quote', payload('facts',item(6,'事实',text='仅列出检查摘要')),
         '客观目录半句候选，quote仍保留完整限定；当前同句保守规则拒绝，不等同模型认定日志完整。'),
        ('directory_excerpt_short_quote', payload('facts',item(6,'事实',quote='仅列出检查摘要')),
         '只引用客观半句仍被原文同句限定约束；不能通过缩短quote规避。'),
        ('log_completeness_pending', payload('pending_evidence',item(6,'推断',reasoning='待核实推断：原始车载日志是否完整？')),
         '完整原文作为待核实事项的依据，提问而不认定日志已完整或已缺失。'),
        ('driver_claim_as_fact', payload('facts',item(4,'事实')), '驾驶人的单方主张不能升级事实。'),
        ('company_claim_as_fact', payload('facts',item(5,'事实')), '企业的单方主张不能升级事实。'),
        ('driver_claim_kept', payload('facts',item(4,'主张')), 'facts列表承载主张，但kind必须保留主张。'),
        ('company_claim_kept', payload('facts',item(5,'主张')), '企业主张同样独立保留，不由程序确认其内容。'),
        ('objective_receipt_record', payload('facts',item(3,'事实')), '完整独立的客观接收记载应通过，仍待人工核验。'),
    ]


def evaluate(raw_output, record):
    try:
        parsed = Analysis.model_validate_json(raw_output)
    except ValueError:
        return {'schema_valid':False,'binding_valid':None,'validation_error_kind':'schema'}
    try:
        validate_analysis(parsed,record,build_sources(record))
    except AIError as exc:
        return {'schema_valid':True,'binding_valid':False,'validation_error_kind':'evidence_binding',
                'validation_diagnostic':exc.diagnostic}
    return {'schema_valid':True,'binding_valid':True,'verification':'待人工核验'}


def manual_report(*, save_rejected_samples=False):
    record,cases = reproduction_cases()
    rows = []
    for name,payload,interpretation in cases:
        raw = json.dumps(payload,ensure_ascii=False,indent=2)
        result = evaluate(raw,record)
        section = next(name for name in ('facts','timeline','issues','pending_evidence') if payload[name])
        target = payload[section][-1]
        row = {'case_id':name,'section':section,'item_index':len(payload[section])-1,
               'source_id':target['sources'][0]['source_id'],'quote':target['sources'][0]['quote'],
               'text':target['text'],'kind':target['kind'],'reasoning':target['reasoning'],
               'interpretation':interpretation,**result}
        if save_rejected_samples is True and result['binding_valid'] is False:
            row['debug_capture'] = capture_rejected_output(record,raw,enabled=True,execution_mode='manual_offline')
        rows.append(row)
    return {'execution_mode':'manual_offline','fixture_id':'SIM_B','actual_live_attempts':0,'accuracy':None,
            'prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest(),'cases':rows}


def replay_artifact(artifact_id):
    envelope = read_capture(artifact_id)
    record = fixed_record(envelope['fixture_id'])
    # 不在终端输出捕获的raw_output、text或quote；仅打印本地校验结果。
    return {'execution_mode':'offline_artifact_replay','actual_live_attempts':0,'accuracy':None,
            'fixture_id':envelope['fixture_id'],'origin_execution_mode':envelope['execution_mode'],
            'origin_prompt_sha256':envelope.get('prompt_sha256'),
            'current_prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest(),
            **evaluate(envelope['raw_output'],record)}
