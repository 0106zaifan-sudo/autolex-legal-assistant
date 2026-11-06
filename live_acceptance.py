"""安全配置前只准备；真实验收只接受固定两份模拟材料，不接受任意上传文件。"""
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import hashlib
import json
import time
import uuid
from ai_analysis import AIError, analyze_record, prepare_request
from core import extract
from security import SecurityError

ROOT=Path(__file__).parent
SAMPLES=ROOT/'acceptance_samples'


class AcceptanceError(ValueError):
    pass


def load_scenarios(root=SAMPLES):
    root=Path(root).resolve()
    manifest=json.loads((root/'manifest.json').read_text())
    entries=manifest.get('scenarios',[])
    if len(entries)!=2 or {x.get('id') for x in entries}!={'SIM_A','SIM_B'}:
        raise AcceptanceError('只允许已审核的两份固定模拟场景')
    loaded=[]
    for entry in entries:
        path=root/entry['file']
        if path.is_symlink() or not path.resolve().is_relative_to(root) or path.name!=entry['file']:
            raise AcceptanceError('模拟材料路径无效')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=entry['sha256']:
            raise AcceptanceError('模拟材料与清单哈希不一致，停止验收')
        record=extract(path.name,data)
        if '模拟' not in path.name or not record['units'] or not record['units'][0]['text'].startswith('【模拟数据：完全虚构'):
            raise AcceptanceError('材料缺少明确模拟标识')
        if record['parse_report']['status']!='parsed' or record['parse_report']['requires_acknowledgement']:
            raise AcceptanceError('验收材料解析不完整，需先修复或人工审核；不自动放行')
        loaded.append((entry,record))
    return manifest,loaded


def preparation_report(root=SAMPLES):
    manifest,loaded=load_scenarios(root)
    return {'report_version':'1.0','phase':'awaiting_secure_configuration',
            'execution_mode':'preparation_only','actual_live_attempts':0,
            'created_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
            'suite_version':manifest['suite_version'],
            'cases':[{'scenario_id':entry['id'],'file_name':record['文件名'],
                      'file_sha256':record['文件SHA256'],'parse_status':record['parse_report']['status'],
                      'call_status':'not_run','requested_model':None,'provider_model':None,'token_usage':None,
                      'automatic_checks':None,'human_review':{'status':'pending','notes':None},
                      'expected_checks':entry['gold']} for entry,record in loaded],
            'acceptance_status':'not_evaluated','accuracy':None}


def preflight(settings,store,principal,loaded):
    reason=settings.ai_disabled_reason(principal)
    if reason:raise AcceptanceError(reason)
    if not settings.single_instance:
        raise AcceptanceError('本验收要求显式确认AI_SINGLE_INSTANCE=true并使用同一持久SQLite')
    if settings.cooldown>60:
        raise AcceptanceError('两份材料的冷却间隔超过60秒，请调整安全测试计划后再运行；未调用模型。')
    budgets=[prepare_request(record,settings)[2] for _,record in loaded]
    remaining=store.budget_snapshot(settings,principal)
    if min(remaining['daily_calls_remaining'],remaining['hourly_calls_remaining'])<2:
        raise AcceptanceError('剩余调用次数不足两份验收，未发起请求')
    for name,requested in [('chars',sum(b['input_chars'] for b in budgets)),
                           ('bytes',sum(b['request_bytes'] for b in budgets))]:
        if requested>min(remaining['daily_'+name+'_remaining'],remaining['hourly_'+name+'_remaining']):
            raise AcceptanceError('剩余累计输入预算不足两份验收，未发起请求')
    return budgets


def automatic_checks(entry,record,result):
    sections=result['sections']
    facts=[x['text'] for x in sections['facts'] if x['kind']=='事实']
    claims=[x['text'] for x in sections['facts'] if x['kind']=='主张']
    gold=entry['gold']
    checks={'required_fact_phrases_present':all(any(p in text for text in facts) for p in gold['fact_phrases']),
            'opposing_claim_phrases_present':all(any(p in text for text in claims) for p in gold['claim_phrases']),
            'timeline_expected_bindings':all(any(row['text']==event['quote'] and
                 all(row.get(k)==event[k] for k in ('time_text','time_state','time_precision'))
                 for row in sections['timeline']) for event in gold['timeline']),
            'pending_evidence_question_present':any(gold['pending_keyword'] in row['reasoning'] for row in sections['pending_evidence'])}
    citations=[]
    for rows in sections.values():
        for row in rows:
            for ref in row['sources']:
                citations.append(ref['document_sha256']==record['文件SHA256'] and
                                 record['units'][ref['unit_index']]['text'][ref['start']:ref['end']]==ref['quote'])
    checks['all_quotes_replay']=bool(citations) and all(citations)
    checks['unknown_times_not_filled']=all(row['time_source'] is None and row['normalized_time'] is None and row['time_text']=='未知'
                                         for row in sections['timeline'] if row['time_state']=='unknown')
    return {'type':'literal_fixture_checks_not_accuracy','checks':checks,
            'status':'passed' if all(checks.values()) else 'needs_review',
            'semantic_correctness':'pending_human_review'}


def write_report(report,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=directory/'report.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');path.chmod(0o600)
    lines=['# AutoLex模型验收记录','',f"阶段：{report['phase']}",f"执行类型：{report['execution_mode']}",
           f"真实尝试次数：{report['actual_live_attempts']}",'',
           '程序匹配检查不能代替语义人工审查；没有真实响应时模型标识和token均为未知，不填0或准确率。','',
           '| 场景 | 调用状态 | 返回模型标识 | token记录 | 人工复核 |','|---|---|---|---|---|']
    for case in report['cases']:
        receipt=case.get('call_receipt') or {}
        model=receipt.get('provider_model') or '未获得'
        usage='已返回，见JSON' if receipt.get('token_usage') is not None else '未获得'
        lines.append(f"| {case['scenario_id']} | {case['call_status']} | {model} | {usage} | pending |")
    (directory/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return path


def run_suite(settings,store,principal,output_root,*,root=SAMPLES,confirm_paid=False,executor=None,sleeper=time.sleep):
    if not confirm_paid:
        raise AcceptanceError('未明确允许两次付费请求；仅可运行准备模式')
    _,loaded=load_scenarios(root)
    preflight(settings,store,principal,loaded)
    # 注入executor的单元测试永远标为offline_test，不能伪装为真实SDK验收。
    real=executor is None
    executor=analyze_record if executor is None else executor
    report=preparation_report(root)
    report.update(phase='execution_in_progress',execution_mode='live_sdk' if real else 'offline_test')
    directory=Path(output_root)/uuid.uuid4().hex
    write_report(report,directory)
    for index,(entry,record) in enumerate(loaded):
        row=report['cases'][index]
        row['requested_model']=settings.model
        delay=store.budget_snapshot(settings,principal)['cooldown_remaining']
        if delay>0:
            if delay>60:raise AcceptanceError('冷却等待超出本批次上限；不会自动重复请求')
            sleeper(delay+0.05)
        try:
            result=executor(record,settings,store,principal,True,coverage_acknowledged=True)
            receipt=result.get('call_receipt',{})
            if real and receipt.get('execution_mode')!='live_sdk':
                raise AcceptanceError('结果不是默认真实SDK路径，不能计入真实模型验收')
            row.update(call_status='response_validated',call_receipt=receipt,provider_model=receipt.get('provider_model'),
                       token_usage=receipt.get('token_usage'),
                       automatic_checks=automatic_checks(entry,record,result))
            response_path=directory/(entry['id']+'_analysis.json')
            response_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');response_path.chmod(0o600)
            row['analysis_file']=response_path.name
        except (AIError,SecurityError,AcceptanceError) as exc:
            receipt=getattr(exc,'receipt',None)
            row.update(call_status='failed' if receipt else 'blocked_before_call',call_receipt=receipt,
                       provider_model=(receipt or {}).get('provider_model'),token_usage=(receipt or {}).get('token_usage'),
                       error_code=getattr(exc,'code','local_preflight_error'),automatic_checks=None)
            row['error_note']='未获得可接受结果；详见错误代码，不能据此填准确率。'
            if real and receipt and receipt.get('execution_mode')=='live_sdk':
                report['actual_live_attempts']+=1
            write_report(report,directory)
            if getattr(exc,'code',None) in ('authentication_failed','rate_limited','cancelled'):
                break  # 认证或服务商额度失败后不继续消耗第二次请求。
            continue
        if real:report['actual_live_attempts']+=1
        write_report(report,directory)
    report.update(phase='awaiting_human_review' if all(c['call_status']=='response_validated' for c in report['cases']) else 'needs_error_review',
                  acceptance_status='not_approved',accuracy=None)
    write_report(report,directory)
    return report,directory
