"""重建明确标识的模拟材料及Schema 2.0固定响应，不调用模型。"""
from pathlib import Path
import json
from docx import Document
from ai_analysis import analysis_context
from core import extract

ROOT = Path(__file__).parent / 'samples_ai'
LINES = [
    '【模拟数据：AI事故分析测试材料，纯虚构，不是真实案件】',
    '维修记录记载：2026年11月1日08:30，测试车辆在模拟封闭场地发生碰撞。',
    '测试驾驶人主张：2026年11月1日08:29已接管方向盘，碰撞前未收到提示。',
    '测试企业主张：2026年11月1日08:29系统已发出接管提示。',
    '资料目录记载：已附一份维修记录；事故前后原始车载日志是否完整尚未核实。',
    '模拟记录未记载车速、伤亡情况或责任认定结论。',
]


def build_mock_payload(record):
    def item(kind, idx, reasoning='', time=None):
        ref = {'source_id': f'S{idx+1:03}', 'quote': LINES[idx]}
        result = {'kind': kind, 'text': LINES[idx], 'reasoning': reasoning, 'sources': [ref]}
        if time is not None:
            result.update(time_state='explicit', time_text=time, time_precision='minute',
                          event_source=dict(ref), time_source=dict(ref))
        return result
    return {**analysis_context(record),
            'facts': [item('事实', 1), item('主张', 2), item('主张', 3)],
            'timeline': [item('事实', 1, time='2026年11月1日08:30'),
                         item('主张', 2, time='2026年11月1日08:29'),
                         item('主张', 3, time='2026年11月1日08:29')],
            'issues': [item('推断', 2, '待核实推断：接管提示是否实际发出、驾驶人是否收到，相关记录能否相互印证？')],
            'pending_evidence': [item('推断', 4, '待核实推断：原始日志是否完整、时间戳是否同步，能否与维修记录核对？')]}


def generate_samples(output_dir=ROOT):
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    doc = Document()
    for line in LINES:
        doc.add_paragraph(line)
    path = output_dir / '模拟_AI事故材料.docx'
    doc.save(path)
    record = extract(path.name, path.read_bytes())
    (output_dir / 'mock_analysis.json').write_text(
        json.dumps(build_mock_payload(record), ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    generate_samples()
    print('已生成明确标识的Schema 2.0模拟材料及固定响应（非AI调用）')
