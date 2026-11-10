"""固定虚构CASE-001的人工编号选择演示；没有模型、Secrets、配额或生产导入选项。"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from case_store import CaseStore
from security import Settings
from prototypes.pending_evidence_selection import (prepare_selection,validate_selection,PrototypeError,
                                                    SCHEMA_VERSION,PROMPT_VERSION)

ROOT = Path(__file__).resolve().parents[1]
SITE = '事故时间栏目08:30来自P01口述，仅按分钟填写，未作时钟校核。'
EDR = 'EDR只提供相对触发锚点t=0的测试摘要，未提供可信绝对日期。'
BODY = '原始二进制数据及提取过程镜像未提供，摘要为二次转写。'
TITLE = '模拟材料：EDR摘要'
COMPANY = '原始二进制日志、设备镜像和完整性签名未随本说明提供。'
CLAIM = '企业主张：驾驶人已收到接管提示。'


def run_demo():
    store=CaseStore();temporary=store.create_case('完全虚构 CASE-001离线编号选择')
    # 仅固定测试夹具使用稳定case_id，方便人工比对；不是向既有案件写入。
    cid='case_'+hashlib.sha256(b'CASE-001 pending-selection offline prototype/1').hexdigest()[:32]
    case=store._cases.pop(temporary);case.case_id=cid;store._cases[cid]=case
    data=ROOT/'datasets/CASE-001/standard';ids=[]
    for d in json.loads((data/'manifest.json').read_text())['documents']:
        if d['material_id'] in ('D01','D03','D04'):
            path=data/d['path'];raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=d['sha256']:raise ValueError('固定虚构材料哈希不符')
            ids.append(store.attach_document(cid,path.name,raw))
    prepared=prepare_selection(store,cid,ids,Settings(provider='deepseek',model='deepseek-flash'))

    def fixture_id(quote):
        # 人工夹具预先指定完整原文，严格唯一匹配以构造人工选择；不是运行时修复错误引用。
        rows=[e for e in prepared['catalog']['entries'] if e['quote'].rstrip('\r\n')==quote]
        if len(rows)!=1:raise ValueError('人工夹具原文不唯一，停止；不近似搜索')
        return rows[0]['candidate_id']

    def response(quotes,question):
        chosen=[fixture_id(q) for q in quotes]
        return {'schema_version':SCHEMA_VERSION,'prompt_version':PROMPT_VERSION,'case_id':cid,
                'batch_sha256':prepared['batch']['batch_sha256'],'catalog_sha256':prepared['catalog']['sha256'],
                'pending_evidence':[{'anchor_id':chosen[0],'evidence_ids':chosen,'reasoning':question}]}

    fixtures=[('d01_d04_multisource',(SITE,EDR),'待核实推断：D01口述分钟与D04的EDR相对锚点是否有可核对的基准？'),
              ('d04_explicit_title',(BODY,TITLE),'待核实推断：D04的EDR摘要原始数据是否需要核查？'),
              ('d01_d03_multisource',(SITE,COMPANY),'待核实推断：D01时间来源与D03的原始日志材料是否需要分别核查？')]
    before=store.export_json(cid);examples=[]
    for name,quotes,question in fixtures:
        raw=response(quotes,question)
        examples.append({'id':name,'selection_origin':'human_authored_offline_fixture',
                         'raw_selection':raw,'result':validate_selection(store,cid,prepared,raw)})
    failures=[]
    bad=response((BODY,),'待核实推断：D04的EDR摘要原始数据是否需要核查？')
    unknown=deepcopy(examples[0]['raw_selection']);unknown['pending_evidence'][0]['evidence_ids'][1]='PE_'+'f'*24
    for name,raw in (('d04_missing_explicit_term_source',bad),('unknown_candidate',unknown)):
        try:validate_selection(store,cid,prepared,raw)
        except PrototypeError as exc:failures.append({'id':name,'code':exc.code,'diagnostic':exc.diagnostic})
        else:raise AssertionError('反例未被拒绝')
    misleading=response((CLAIM,),'待核实推断：驾驶人已收到提示的自述是否需要核查？')
    limitations={'id':'wrong_subject_attribution','human_expected_assessment':'企业主张被误称驾驶人自述，需人工纠正，词面绑定不会自动检出',
                 'result':validate_selection(store,cid,prepared,misleading)}
    assert store.export_json(cid)==before
    return {'declaration':'完全虚构，仅用于软件测试；人工编号选择，不是真实模型输出或验收通过',
            'execution_mode':'offline_prototype_no_model','real_model_calls':0,'automatic_retries':0,
            'authorization_status':'not_requested_offline_only','production_import_allowed':False,
            'budget':prepared['budget'],'catalog_entries':len(prepared['catalog']['entries']),
            'catalog_excluded':prepared['catalog']['excluded'],
            'required_acknowledgements':prepared['required_acknowledgements'],
            'examples':examples,'expected_rejections':failures,'semantic_counterexample':limitations}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='将固定虚构演示JSON写入指定本地文件；不调用模型')
    args=parser.parse_args(argv)
    report=run_demo();text=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(text)
    else:print(text,end='')
    return 0


if __name__=='__main__':raise SystemExit(main())
