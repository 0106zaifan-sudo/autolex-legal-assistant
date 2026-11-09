"""完全虚构的四份V2材料；不生成模型结果。"""
from pathlib import Path
from docx import Document
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

LINES={
 '模拟_现场记录.pdf':'事件编号：SIM-V2-001；现场记录：2026年11月1日08:30车辆发生碰撞。',
 '模拟_驾驶人陈述.docx':'事件编号：SIM-V2-001；驾驶人未收到接管提示。',
 '模拟_企业说明.docx':'事件编号：SIM-V2-001；系统已发出接管提示。',
 '模拟_电子数据摘要.pdf':'事件编号：SIM-V2-001；摘要：2026年11月1日08:31车辆发生碰撞。原始日志未提供。',
}

def generate(root):
 root=Path(root);root.mkdir(parents=True,exist_ok=True)
 pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
 for name,text in LINES.items():
  header='【模拟材料：完全虚构，不是真实案件；来源及真实性未核验】'
  if name.endswith('.docx'):
   doc=Document();doc.add_paragraph(header);doc.add_paragraph(text);doc.save(root/name)
  else:
   c=canvas.Canvas(str(root/name));c.setFont('STSong-Light',11)
   c.drawString(35,790,header);c.drawString(35,765,text);c.save()

if __name__=='__main__':generate(Path(__file__).parent/'samples_multidoc')
