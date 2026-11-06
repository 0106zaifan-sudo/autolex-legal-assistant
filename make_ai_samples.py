"""仅生成第二阶段的独立模拟样本，不改变第一阶段6份样本。"""
from pathlib import Path
import json
from docx import Document
ROOT = Path(__file__).parent / 'samples_ai'
LINES = [
    '【模拟数据：AI事故分析测试材料，纯虚构，不是真实案件】',
    '维修记录记载：2026年11月1日08:30，测试车辆在模拟封闭场地发生碰撞。',
    '测试驾驶人主张：2026年11月1日08:29已接管方向盘，碰撞前未收到提示。',
    '测试企业主张：2026年11月1日08:29系统已发出接管提示。',
    '资料目录记载：已附一份维修记录；事故前后原始车载日志是否完整尚未核实。',
    '模拟记录未记载车速、伤亡情况或责任认定结论。',
]
ROOT.mkdir(exist_ok=True)
doc=Document()
for line in LINES:doc.add_paragraph(line)
doc.save(ROOT/'模拟_AI事故材料.docx')

def item(kind, idx, reasoning='', time=None):
    result={'kind':kind,'text':LINES[idx], 'reasoning':reasoning,
            'sources':[{'source_id':f'S{idx+1:03}','quote':LINES[idx]}]}
    if time is not None:result['time_text']=time
    return result
payload={
 'facts':[item('事实',1),item('主张',2),item('主张',3)],
 'timeline':[item('事实',1,time='2026年11月1日08:30'),item('主张',2,time='2026年11月1日08:29'),item('主张',3,time='2026年11月1日08:29')],
 'issues':[item('推断',2,'待核实推断：接管提示是否实际发出、驾驶人是否收到，相关记录能否相互印证？')],
 'pending_evidence':[item('推断',4,'待核实推断：原始日志是否完整、时间戳是否同步，能否与维修记录核对？')],
}
(ROOT/'mock_analysis.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
print('已生成明确标识的第二阶段模拟材料及固定响应')
