import io
from pathlib import Path
import unittest
from copy import deepcopy
from docx import Document
from openpyxl import load_workbook
from core import extract, search, review, summary, export_excel, read_units, MAX_BYTES

ROOT = Path(__file__).resolve().parents[1]

def doc_bytes(lines):
    d = Document()
    for line in lines:
        d.add_paragraph(line)
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


class CoreTests(unittest.TestCase):
    def setUp(self):
        p = ROOT / 'samples' / '模拟_辅助驾驶责任.docx'
        self.r = extract(p.name, p.read_bytes())

    def test_pdf_and_docx_same_candidates(self):
        p = ROOT / 'samples' / '模拟_辅助驾驶责任.pdf'
        pdf = extract(p.name, p.read_bytes())
        self.assertEqual([c['原文摘录'] for c in self.r['candidates']], [c['原文摘录'] for c in pdf['candidates']])
        self.assertTrue(all(c['原文位置'] == 'PDF 第 1 页' for c in pdf['candidates']))

    def test_exact_source_trace(self):
        for c in self.r['candidates']:
            u = next(u for u in self.r['units'] if u['location'] == c['原文位置'])
            self.assertEqual(c['原文摘录'], u['text'][c['字符起点']:c['字符终点']])
            self.assertEqual(c['核验状态'], '待人工核验')

    def test_missing_fields_never_invented_and_table_read(self):
        p = ROOT / 'samples' / '模拟_信息缺失.docx'
        r = extract(p.name, p.read_bytes())
        self.assertEqual(len(r['candidates']), 4)
        self.assertTrue(all(not c['原文摘录'] and c['核验状态'] == '待人工核验' for c in r['candidates']))
        self.assertTrue(any('表格正文' in u['text'] for u in r['units']))

    def test_blank_pdf_warns(self):
        p = ROOT / 'samples' / '模拟_无文字页.pdf'
        r = extract(p.name, p.read_bytes())
        self.assertTrue(r['warnings'])
        self.assertTrue(all(not c['原文摘录'] for c in r['candidates']))

    def test_keyword_full_text_and_and_semantics(self):
        self.assertEqual(search([self.r], '消费者 宣传'), [self.r])
        self.assertEqual(search([self.r], '消费者 不存在词'), [])

    def test_filters(self):
        self.assertEqual(search([self.r], courts=['虚构甲市人民法院']), [self.r])
        self.assertEqual(search([self.r], courts=['虚构乙市人民法院']), [])
        self.assertEqual(search([self.r], statuses=['已人工核验']), [])
        self.assertEqual(search([self.r], kinds=['用户上传（真实性未核验）']), [])

    def test_review_audit_and_aggregate(self):
        for c in self.r['candidates']:
            review(self.r, c['候选ID'], '已人工核验', '测试核验人', '仅核对模拟原文一致性')
        self.assertEqual(summary(self.r)['核验状态'], '已人工核验')
        self.assertEqual(len(self.r['audit']), 4)
        review(self.r, '1', '提取有误', '测试核验人', '模拟错误标记')
        self.assertEqual(summary(self.r)['核验状态'], '提取有误')

    def test_review_requires_identity_and_evidence(self):
        with self.assertRaises(ValueError):
            review(self.r, '1', '已人工核验', '', '')
        self.assertEqual(self.r['audit'], [])
        missing = extract('missing.docx', doc_bytes(['没有明确法律字段']))
        with self.assertRaises(ValueError):
            review(missing, '1', '已人工核验', '甲', '备注')

    def test_multiple_mentions_kept(self):
        r = extract('多候选.docx', doc_bytes(['虚构甲市人民法院与虚构乙市人民法院', '引用《虚构规则甲》第一条及《虚构规则乙》第二条。']))
        self.assertEqual(len([c for c in r['candidates'] if c['字段'] == '法院']), 2)
        self.assertEqual(len([c for c in r['candidates'] if c['字段'] == '法律依据']), 2)

    def test_content_simulation_marker(self):
        r = extract('renamed.docx', doc_bytes(['【模拟数据：虚构】']))
        self.assertIn('模拟数据', r['数据类型'])

    def test_export_reopens_preserves_trace_and_neutralizes_formula(self):
        r = deepcopy(self.r)
        r['文件名'] = '=HYPERLINK("bad")'
        review(r, '1', '提取有误', '核验员', '测试错误')
        wb = load_workbook(io.BytesIO(export_excel([r])))
        self.assertEqual(len(wb.sheetnames), 5)
        self.assertEqual(wb['字段与出处'].max_row, 5)
        self.assertEqual(wb['核验日志'].max_row, 2)
        self.assertNotEqual(wb['资料总表']['A2'].data_type, 'f')
        self.assertTrue(wb['资料总表']['A2'].value.startswith("'="))

    def test_long_original_preserved(self):
        r = extract('long.docx', doc_bytes(['甲' * 65000]))
        wb = load_workbook(io.BytesIO(export_excel([r])))
        ws = wb['原文摘录']
        headers = [c.value for c in ws[1]]
        col = headers.index('正文') + 1
        restored = ''.join(ws.cell(i, col).value or '' for i in range(2, ws.max_row + 1))
        self.assertEqual(len(restored), 65000)

    def test_invalid_files_and_limits(self):
        for name, data in [('bad.pdf', b'bad'), ('bad.docx', b'bad'), ('bad.txt', b'text'), ('big.pdf', b'x' * (MAX_BYTES + 1))]:
            with self.subTest(name=name), self.assertRaises(Exception):
                read_units(name, data)


if __name__ == '__main__':
    unittest.main()
