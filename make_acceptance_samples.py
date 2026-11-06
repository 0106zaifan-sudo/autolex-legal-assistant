"""两份完全虚构的辅助驾驶事故材料及人工预设核对项，不生成模型测试结果。"""
from pathlib import Path
import hashlib
import json
from docx import Document

ROOT=Path(__file__).parent/'acceptance_samples'
SCENARIOS=[
    {'id':'SIM_A','file':'模拟_接管提示争议.docx','lines':[
        '【模拟数据：完全虚构，仅用于AutoLex模型集成验收，不是真实案件】',
        '模拟现场记录：2026年11月1日08:30，车辆在封闭测试场地发生碰撞。',
        '模拟驾驶人主张：2026年11月1日08:29已接管方向盘，碰撞前未收到接管提示。',
        '模拟企业主张：2026年11月1日08:29系统已发出接管提示。',
        '模拟维修记录：2026年11月2日09:00，车辆完成维修。',
        '模拟资料目录：原始提示日志是否完整尚未核实。'],
     'gold':{'fact_phrases':['车辆在封闭测试场地发生碰撞'],
             'claim_phrases':['已接管方向盘','系统已发出接管提示'],
             'timeline':[{'quote':'模拟现场记录：2026年11月1日08:30，车辆在封闭测试场地发生碰撞。',
                          'time_text':'2026年11月1日08:30','time_state':'explicit','time_precision':'minute'},
                         {'quote':'模拟维修记录：2026年11月2日09:00，车辆完成维修。',
                          'time_text':'2026年11月2日09:00','time_state':'explicit','time_precision':'minute'}],
             'pending_keyword':'日志','human_checks':['碰撞不得配维修日期','相反提示主张必须分别保留','不认定责任归属或损失金额']}},
    {'id':'SIM_B','file':'模拟_时间缺失与日志核验.docx','lines':[
        '【模拟数据：完全虚构，仅用于AutoLex模型集成验收，不是真实案件】',
        '模拟现场记录：车辆发生碰撞，原文未记载具体日期和时刻。',
        '模拟接收记录：2026年11月4日，测试方收到车辆检查材料。',
        '模拟驾驶人主张：碰撞发生前系统未发出接管提示。',
        '模拟企业主张：提示是否发出仍需核对原始日志。',
        '模拟资料目录：仅列出检查摘要，原始车载日志是否完整尚未核实。'],
     'gold':{'fact_phrases':['车辆发生碰撞'],
             'claim_phrases':['系统未发出接管提示','提示是否发出仍需核对原始日志'],
             'timeline':[{'quote':'模拟现场记录：车辆发生碰撞，原文未记载具体日期和时刻。',
                          'time_text':'未知','time_state':'unknown','time_precision':'unknown'},
                         {'quote':'模拟接收记录：2026年11月4日，测试方收到车辆检查材料。',
                          'time_text':'2026年11月4日','time_state':'explicit','time_precision':'date'}],
             'pending_keyword':'日志','human_checks':['接收日期不得填成碰撞日期','不得补造碰撞日期或午夜','日志完整性是待核实事项，不认定日志已缺失']}}
]


def generate(root=ROOT):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    entries=[]
    for scenario in SCENARIOS:
        doc=Document()
        for line in scenario['lines']:doc.add_paragraph(line)
        path=root/scenario['file'];doc.save(path)
        entries.append({key:scenario[key] for key in ('id','file','gold')}|
                       {'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (root/'manifest.json').write_text(json.dumps({'suite_version':'1.0','data_type':'模拟材料（非真实案件）','scenarios':entries},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    generate();print('两份模拟材料与预设核对项已生成；没有模型调用或测试结果。')
