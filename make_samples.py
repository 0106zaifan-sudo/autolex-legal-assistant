"""生成纯虚构测试资料，无真实法院、案号或法律条文断言。"""
from pathlib import Path
from docx import Document
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
ROOT = Path(__file__).parent / 'samples'
ROOT.mkdir(exist_ok=True)
SAMPLES = [
 ('模拟_辅助驾驶责任', ['【模拟数据：纯虚构，仅测试功能，不是真实案件】', '虚构甲市人民法院', '案号：（2099）模拟民初001号', '争议焦点：辅助驾驶提示是否充分（虚构测试问题）。', '测试法律依据：《虚构智能驾驶测试规则》第一条。', '测试事实：消费者反映辅助驾驶功能与宣传不一致。']),
 ('模拟_车联网数据', ['【模拟数据：纯虚构，仅测试功能，不是真实案件】', '虚构乙市人民法院', '案号：（2099）模拟民初002号', '争议焦点：车辆位置数据的收集范围是否清晰告知（虚构测试问题）。', '测试法律依据：《虚构车联网数据测试规则》第二条。', '测试事实：用户申请删除车辆位置数据。']),
]
pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
for name, lines in SAMPLES:
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    doc.save(ROOT / (name + '.docx'))
    pdf = canvas.Canvas(str(ROOT / (name + '.pdf')))
    pdf.setFont('STSong-Light', 12)
    for i, line in enumerate(lines):
        pdf.drawString(40, 790 - i * 32, line)
    pdf.save()
doc = Document()
doc.add_paragraph('【模拟数据：信息缺失样本，仅用于测试】')
doc.add_paragraph('测试主题：动力电池质量。本资料未记载法院、案号、争议焦点和法律依据。')
table = doc.add_table(rows=1, cols=1)
table.cell(0, 0).text = '表格正文：维修记录测试文本。'
doc.save(ROOT / '模拟_信息缺失.docx')
pdf = canvas.Canvas(str(ROOT / '模拟_无文字页.pdf'))
pdf.setTitle('SIMULATED EMPTY PAGE - NOT A REAL CASE')
pdf.rect(40, 40, 400, 500)
pdf.showPage()
pdf.save()
print('已生成 6 个明确标识的模拟样本')
