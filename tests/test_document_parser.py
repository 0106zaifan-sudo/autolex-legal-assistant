"""覆盖检查使用真实内存PDF/DOCX和局部故障注入，无OCR/模型调用。"""
import io
import json
import unittest
from unittest.mock import patch, PropertyMock, Mock
from docx import Document
from docx.oxml import OxmlElement
from pypdf import PdfReader, PdfWriter
from pypdf._page import PageObject
from pypdf.generic import NameObject, BooleanObject, DictionaryObject, ArrayObject
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image
from core import extract, read_units
from document_parser import parse_document, DocumentParseError, PARSER_VERSION
from ai_analysis import analyze_record, AIError
from security import Settings


def doc_bytes(doc):
    out=io.BytesIO();doc.save(out);return out.getvalue()


def pdf_text(text='SIMULATED TEXT'):
    out=io.BytesIO();c=canvas.Canvas(out);c.drawString(40,750,text);c.save();return out.getvalue()


class ParserCoverageTests(unittest.TestCase):
    def test_bad_files_return_structured_reports_and_legacy_exception_has_report(self):
        for name in ('模拟_bad.pdf','模拟_bad.docx','模拟_bad.txt'):
            with self.subTest(name=name):
                result=parse_document(name,b'broken')
                self.assertIn(result.report['status'],('failed','rejected'))
                self.assertFalse(result.units)
                self.assertTrue(result.report['issues'])
                json.dumps(result.report,ensure_ascii=False)
                with self.assertRaises(DocumentParseError) as caught:read_units(name,b'broken')
                self.assertEqual(caught.exception.report['file_sha256'],result.report['file_sha256'])

    def test_pdf_blank_page_is_distinguished_from_scan(self):
        writer=PdfWriter();writer.add_blank_page(width=200,height=200)
        out=io.BytesIO();writer.write(out)
        r=parse_document('模拟_空白.pdf',out.getvalue())
        self.assertEqual(r.report['counts']['blank_pages'],1)
        self.assertEqual(r.report['counts']['suspected_scan_pages'],0)
        self.assertEqual(r.report['items'][0]['status'],'blank_page')

    def test_image_only_pdf_is_suspected_scan_without_claiming_ocr(self):
        out=io.BytesIO();c=canvas.Canvas(out)
        c.drawImage(ImageReader(Image.new('RGB',(30,30),'black')),40,400,width=100,height=100)
        c.save()
        r=parse_document('模拟_扫描.pdf',out.getvalue())
        self.assertEqual(r.report['counts']['suspected_scan_pages'],1)
        self.assertEqual(r.report['items'][0]['status'],'suspected_scan')
        self.assertIn('未执行 OCR',r.report['items'][0]['message'])
        self.assertFalse(r.units[0]['text'].strip())

    def test_vector_only_page_does_not_claim_definite_blank_or_scan(self):
        out=io.BytesIO();c=canvas.Canvas(out);c.rect(40,40,100,100);c.save()
        r=parse_document('模拟_图形.pdf',out.getvalue())
        self.assertEqual(r.report['items'][0]['status'],'no_text')
        self.assertEqual(r.report['counts']['blank_pages'],0)
        self.assertEqual(r.report['counts']['suspected_scan_pages'],0)

    def test_one_pdf_page_failure_keeps_other_pages_and_positions(self):
        writer=PdfWriter()
        for text in ('SIMULATED ONE','SIMULATED TWO','SIMULATED THREE'):
            writer.add_page(PdfReader(io.BytesIO(pdf_text(text))).pages[0])
        writer.pages[1][NameObject('/AuditFail')]=BooleanObject(True)
        out=io.BytesIO();writer.write(out)
        original=PageObject.extract_text
        def extract_page(page,*args,**kwargs):
            if page.get('/AuditFail'):raise RuntimeError('SENSITIVE_INTERNAL_BODY')
            return original(page,*args,**kwargs)
        with patch.object(PageObject,'extract_text',extract_page):
            r=parse_document('模拟_局部失败.pdf',out.getvalue())
        self.assertEqual(len(r.units),3)
        self.assertIn('ONE',r.units[0]['text'])
        self.assertEqual(r.units[1],{'location':'PDF 第 2 页','text':''})
        self.assertIn('THREE',r.units[2]['text'])
        self.assertEqual(r.report['counts']['failed_pages'],1)
        self.assertNotIn('SENSITIVE',json.dumps(r.report))
        self.assertEqual(r.report['status'],'partial')

    def test_pdf_table_coverage_is_explicitly_unverified_even_without_tags(self):
        r=parse_document('模拟_文字.pdf',pdf_text())
        self.assertEqual(r.report['table_coverage'],'unverified')
        self.assertTrue(r.report['requires_acknowledgement'])
        self.assertTrue(any(i['code']=='pdf_table_coverage_unverified' for i in r.report['issues']))

    def test_tagged_pdf_table_is_detected_but_not_falsely_claimed_complete(self):
        writer=PdfWriter();writer.add_page(PdfReader(io.BytesIO(pdf_text())).pages[0])
        writer._root_object[NameObject('/StructTreeRoot')]=DictionaryObject({NameObject('/K'):ArrayObject([
            DictionaryObject({NameObject('/S'):NameObject('/Table')})])})
        out=io.BytesIO();writer.write(out)
        r=parse_document('模拟_标签表格.pdf',out.getvalue())
        self.assertEqual(r.report['counts']['tagged_tables_detected'],1)
        self.assertEqual(r.report['table_coverage'],'unverified')

    def test_unreadable_image_resources_are_not_declared_blank(self):
        writer=PdfWriter();writer.add_blank_page(width=200,height=200)
        out=io.BytesIO();writer.write(out)
        with patch('document_parser._image_count',side_effect=RuntimeError):
            r=parse_document('模拟_资源失败.pdf',out.getvalue())
        self.assertEqual(r.report['items'][0]['status'],'no_text')
        self.assertTrue(any(i['code']=='image_inspection_failed' for i in r.report['issues']))

    def test_encrypted_and_oversized_page_count_are_rejected(self):
        writer=PdfWriter();writer.add_blank_page(width=200,height=200);writer.encrypt('simulated-password')
        out=io.BytesIO();writer.write(out)
        self.assertEqual(parse_document('模拟_加密.pdf',out.getvalue()).report['issues'][0]['code'],'encrypted_pdf')
        writer=PdfWriter()
        for _ in range(301):writer.add_blank_page(width=20,height=20)
        out=io.BytesIO();writer.write(out)
        self.assertEqual(parse_document('模拟_页数.pdf',out.getvalue()).report['issues'][0]['code'],'page_limit')

    def test_docx_normal_table_cells_are_accounted_and_text_is_locatable(self):
        doc=Document();doc.add_paragraph('【模拟】正文')
        table=doc.add_table(rows=1,cols=2)
        table.cell(0,0).text='模拟左格';table.cell(0,1).text='模拟右格'
        r=parse_document('模拟_表格.docx',doc_bytes(doc))
        self.assertEqual(r.report['status'],'parsed')
        self.assertEqual(r.report['counts']['cells_detected'],2)
        self.assertEqual(r.report['counts']['cells_read'],2)
        self.assertEqual(r.units[1],{'location':'DOCX 表 1 行 1 列 1','text':'模拟左格'})
        self.assertEqual(r.report['table_coverage'],'physical_cells_accounted')

    def test_nested_table_is_read_with_hierarchical_location(self):
        doc=Document();outer=doc.add_table(rows=1,cols=1)
        outer.cell(0,0).text='模拟父单元格'
        nested=outer.cell(0,0).add_table(rows=1,cols=2)
        nested.cell(0,0).text='模拟嵌套左';nested.cell(0,1).text='模拟嵌套右'
        r=parse_document('模拟_嵌套.docx',doc_bytes(doc))
        self.assertEqual(r.report['counts']['tables_detected'],2)
        self.assertEqual(r.report['counts']['tables_read'],2)
        self.assertEqual(r.report['counts']['cells_read'],3)
        self.assertTrue(any('嵌套表' in u['location'] and u['text']=='模拟嵌套左' for u in r.units))
        self.assertEqual(r.report['status'],'parsed')

    def test_merged_cells_are_counted_as_physical_xml_cells(self):
        doc=Document();table=doc.add_table(rows=1,cols=2)
        table.cell(0,0).merge(table.cell(0,1)).text='模拟合并单元格'
        r=parse_document('模拟_合并.docx',doc_bytes(doc))
        self.assertEqual(r.report['counts']['cells_detected'],1)
        self.assertEqual(r.report['counts']['cells_read'],1)
        self.assertEqual(sum(u['text'].count('模拟合并单元格') for u in r.units),1)

    def test_table_inside_unsupported_control_reports_omission(self):
        doc=Document();doc.add_paragraph('模拟正常正文')
        table=doc.add_table(rows=1,cols=1);table.cell(0,0).text='模拟未覆盖表格'
        control=OxmlElement('w:sdt');content=OxmlElement('w:sdtContent')
        content.append(table._tbl);control.append(content);doc.element.body.insert(1,control)
        r=parse_document('模拟_控件表格.docx',doc_bytes(doc))
        self.assertEqual(r.report['counts']['tables_detected'],1)
        self.assertEqual(r.report['counts']['tables_read'],0)
        self.assertEqual(r.report['table_coverage'],'gap_detected')
        self.assertTrue(any(i['code']=='coverage_count_gap' for i in r.report['issues']))
        self.assertNotIn('模拟未覆盖表格',''.join(u['text'] for u in r.units))

    def test_textbox_revision_and_header_are_reported_not_invented_as_body(self):
        doc=Document();p=doc.add_paragraph('模拟正文')
        picture=OxmlElement('w:pict');textbox=OxmlElement('w:txbxContent')
        inner=OxmlElement('w:p');run=OxmlElement('w:r');text=OxmlElement('w:t');text.text='模拟文本框隐含内容'
        run.append(text);inner.append(run);textbox.append(inner);picture.append(textbox);p._p.append(picture)
        ins=OxmlElement('w:ins');run=OxmlElement('w:r');text=OxmlElement('w:t');text.text='模拟修订'
        run.append(text);ins.append(run);p._p.append(ins)
        doc.sections[0].header.paragraphs[0].text='模拟页眉重要说明'
        r=parse_document('模拟_未覆盖区域.docx',doc_bytes(doc))
        codes={x['code'] for x in r.report['issues']}
        self.assertTrue({'unsupported_txbxContent','unsupported_ins','unsupported_part'}<=codes)
        body=''.join(u['text'] for u in r.units)
        self.assertNotIn('模拟文本框隐含内容',body)
        self.assertNotIn('模拟页眉重要说明',body)
        self.assertEqual(r.report['status'],'partial')

    def test_cell_failure_reports_gap_but_preserves_readable_paragraph(self):
        doc=Document();doc.add_paragraph('模拟保留正文');doc.add_table(rows=1,cols=2)
        with patch('document_parser._Cell.text',new_callable=PropertyMock,side_effect=RuntimeError('SECRET')):
            r=parse_document('模拟_单元格失败.docx',doc_bytes(doc))
        self.assertIn('模拟保留正文',r.units[0]['text'])
        self.assertEqual(r.report['counts']['cells_read'],0)
        self.assertTrue(any(i['code']=='cell_read_failed' for i in r.report['issues']))
        self.assertNotIn('SECRET',json.dumps(r.report))

    def test_incomplete_coverage_blocks_ai_before_client_or_quota(self):
        record=extract('模拟_文字.pdf',pdf_text())
        settings=Settings(api_key='mock-not-real',password_hash='mock-hash',mode='local')
        client,quota=Mock(),Mock()
        with self.assertRaisesRegex(AIError,'解析覆盖'):
            analyze_record(record,settings,quota,settings.principal,True,client_factory=client)
        client.assert_not_called();quota.reserve_ai.assert_not_called()
        self.assertEqual(record['parser_version'],PARSER_VERSION)

    def test_old_parse_version_requires_rereading_original(self):
        from ai_analysis import analysis_context
        doc=Document();doc.add_paragraph('模拟正文')
        record=extract('模拟.docx',doc_bytes(doc))
        record['parser_version']='core.read_units/v1'
        with self.assertRaisesRegex(AIError,'重新读取'):analysis_context(record)
