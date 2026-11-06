"""PDF/DOCX文本层解析及覆盖清单。未读取区域不作为不存在的证据。"""
from __future__ import annotations
import hashlib
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

PARSER_VERSION = 'core.read_units/v2-coverage'
MAX_BYTES = 20 * 1024 * 1024


class DocumentParseError(ValueError):
    def __init__(self, report):
        self.report = report
        super().__init__(report['issues'][0]['message'] if report['issues'] else '文件读取失败')


def safe_name(name):
    return str(name).replace('\\', '/').rsplit('/', 1)[-1]


class ParseResult:
    def __init__(self, name, data):
        self.units = []
        self.report = {'report_version': '1.0', 'parser_version': PARSER_VERSION,
                       'file_name': safe_name(name), 'file_sha256': hashlib.sha256(data).hexdigest(),
                       'status': 'parsed', 'items': [], 'issues': [], 'counts': {},
                       'limitations': [], 'requires_acknowledgement': False,
                       'completeness': 'text_layer_only_not_proven_complete'}

    def item(self, kind, location, status, message='', unit_index=None, xml_path=None):
        item = {'coverage_id': f'C{len(self.report["items"])+1:04}', 'kind': kind,
                'location': location, 'status': status, 'message': message,
                'unit_index': unit_index, 'xml_path': xml_path}
        self.report['items'].append(item)
        return item

    def issue(self, code, location, message, item=None, severity='warning'):
        self.report['issues'].append({'code': code, 'location': location, 'message': message,
                                     'coverage_id': item['coverage_id'] if item else None, 'severity': severity})
        if severity != 'info':
            self.report['requires_acknowledgement'] = True

    def unit(self, kind, location, text, status=None, message='', xml_path=None):
        index = len(self.units)
        self.units.append({'location': location, 'text': text})
        return self.item(kind, location, status or ('read' if text.strip() else 'empty'), message, index, xml_path)

    def fail(self, code, message, status='failed'):
        self.report['status'] = status
        self.issue(code, '文件', message)
        return self

    def finish(self):
        if self.report['status'] == 'parsed' and self.report['requires_acknowledgement']:
            self.report['status'] = 'partial'
        self.report['counts']['extracted_units'] = len(self.units)
        self.report['counts']['extracted_characters'] = sum(len(u['text']) for u in self.units)
        self.report['counts']['issue_count'] = len(self.report['issues'])
        return self


def _object(obj):
    return obj.get_object() if hasattr(obj, 'get_object') else obj


def _image_count(resources, seen=None, depth=0):
    # 只检查资源结构，不解码图片像素；嵌入Form也可能含扫描图像。
    seen = set() if seen is None else seen
    if depth > 5:
        raise ValueError('resource_depth')
    resources = _object(resources) or {}
    objects = _object(resources.get('/XObject')) or {}
    total = 0
    for raw in objects.values():
        obj = _object(raw)
        identity = id(obj)
        if identity in seen:
            continue
        seen.add(identity)
        if len(seen) > 200:
            raise ValueError('resource_limit')
        if obj.get('/Subtype') == '/Image':
            total += 1
        elif obj.get('/Subtype') == '/Form':
            total += _image_count(obj.get('/Resources'), seen, depth+1)
    return total


def _tagged_tables(reader):
    root = _object(reader.trailer['/Root']).get('/StructTreeRoot')
    stack, seen, count = [root], set(), 0
    while stack:
        node = _object(stack.pop())
        if node is None or isinstance(node, (int, str)):
            continue
        if id(node) in seen:
            continue
        seen.add(id(node))
        if len(seen) > 2000:
            raise ValueError('structure_limit')
        if isinstance(node, (list, tuple)):
            stack.extend(node)
        elif hasattr(node, 'get'):
            count += node.get('/S') == '/Table'
            child = node.get('/K')
            if child is not None:
                stack.append(child)
    return count


def _parse_pdf(result, data):
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        return result.fail('encrypted_pdf', '加密 PDF 暂不支持，请提供可读取版本', 'rejected')
    total = len(reader.pages)
    if total > 300:
        return result.fail('page_limit', 'MVP 单份 PDF 最多 300 页', 'rejected')
    counts = result.report['counts']
    counts.update(pages_total=total, pages_attempted=0, pages_with_text=0,
                  blank_pages=0, suspected_scan_pages=0, failed_pages=0, images_detected=0)
    for index in range(total):
        location = f'PDF 第 {index+1} 页'
        counts['pages_attempted'] += 1
        try:
            page = reader.pages[index]
            text = page.extract_text() or ''
        except Exception:
            counts['failed_pages'] += 1
            item = result.unit('page', location, '', 'read_failed', '本页文字读取失败，不能认定无内容。')
            result.issue('page_read_failed', location, item['message'], item)
            continue
        inspected = True
        try:
            images = _image_count(page.get('/Resources'))
        except Exception:
            images, inspected = 0, False
            result.issue('image_inspection_failed', location, '图片资源检查失败，无法确认本页是否含未读图像。')
        counts['images_detected'] += images
        if text.strip():
            counts['pages_with_text'] += 1
            item = result.unit('page', location, text, 'read')
            if images:
                result.issue('image_content_unread', location, '本页含图片；图片内文字未读取，需人工核对。', item)
            if '\ufffd' in text or '\x00' in text or re.search(r'\(cid:\d+\)', text):
                result.issue('text_quality_warning', location, '提取文字可能存在乱码，需对照原页。', item)
        elif images:
            counts['suspected_scan_pages'] += 1
            item = result.unit('page', location, '', 'suspected_scan', '含图像但无可提取文字，疑似扫描页；未执行 OCR。')
            result.issue('suspected_scan', location, item['message'], item)
        elif inspected and not page.get('/Contents') and not page.get('/Annots'):
            counts['blank_pages'] += 1
            item = result.unit('page', location, '', 'blank_page', '未发现内容流、图像或注释，按结构判为空白页。')
            result.issue('blank_page', location, item['message'], item)
        else:
            item = result.unit('page', location, '', 'no_text', '无可提取文字，可能为图形、扫描或空白；不能确定。')
            result.issue('no_extractable_text', location, item['message'], item)
    try:
        counts['tagged_tables_detected'] = _tagged_tables(reader)
    except Exception:
        counts['tagged_tables_detected'] = None
        result.issue('table_inspection_failed', 'PDF 结构树', '表格标签检查失败。')
    result.report['table_coverage'] = 'unverified'
    result.issue('pdf_table_coverage_unverified', 'PDF 全文',
                 'PDF 视觉表格未做结构还原或单元格完整性核验；无标签不代表无表格，可能存在遗漏。')
    result.report['limitations'].extend(['没有 OCR，不读取图片内文字；图像计数仅检查XObject资源，不保证识别内联图像。',
                                       '页码为文件物理页序，位置为解析文本字符偏移，未提供版面坐标。',
                                       'PDF 表格完整性及文本阅读顺序需对照原件；不能给出真实全文覆盖率。'])
    return result


UNSUPPORTED = {'txbxContent': '文本框', 'ins': '修订插入', 'del': '修订删除',
               'sdt': '内容控件', 'altChunk': '嵌入外部内容', 'drawing': '图片或绘图',
               'pict': '图形', 'commentReference': '批注引用',
               'footnoteReference': '脚注引用', 'endnoteReference': '尾注引用',
               'fldSimple': '简单域', 'fldChar': '域标记', 'object': '嵌入对象'}


def _parse_docx(result, data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 5000 or sum(i.file_size for i in entries) > 80*1024*1024:
            return result.fail('expanded_limit', 'DOCX 解压总量或文件数量过大，拒绝处理', 'rejected')
        extras = []
        for name in archive.namelist():
            if re.fullmatch(r'word/(?:header\d+|footer\d+|footnotes|endnotes|comments)\.xml', name):
                try:
                    root = ET.fromstring(archive.read(name))
                    has_content = any((e.text or '').strip() for e in root.iter(qn('w:t')))
                    has_content = has_content or any(True for _ in root.iter(qn('w:drawing')))
                except Exception:
                    has_content = True
                if has_content:
                    extras.append(name)
    doc = Document(io.BytesIO(data))
    body, tree = doc.element.body, doc.element.getroottree()
    counts = result.report['counts']
    counts.update(tables_detected=len(body.findall('.//' + qn('w:tbl'))), tables_read=0,
                  cells_detected=len(body.findall('.//' + qn('w:tc'))), cells_attempted=0, cells_read=0,
                  paragraphs_detected=len(body.findall('.//' + qn('w:p'))), paragraphs_read=0)
    table_index, paragraph_index = 0, 0

    def inspect_nodes(node, location):
        for tag, description in UNSUPPORTED.items():
            for element in node.iter(qn('w:' + tag)):
                xml_path = tree.getpath(element)
                item = result.item('unsupported_object', location, 'unsupported', description+'未纳入正文解析', xml_path=xml_path)
                result.issue('unsupported_' + tag, location, item['message'], item)

    def parse_table(element, parent, prefix=''):
        nonlocal table_index
        table_index += 1
        number = table_index
        table = Table(element, parent)
        table_location = f'{prefix}DOCX 表 {number}' if not prefix else f'{prefix}嵌套表 {number}'
        counts['tables_read'] += 1
        result.item('table', table_location, 'read', xml_path=tree.getpath(element))
        for ri, row in enumerate(element.findall(qn('w:tr')), 1):
            ci = 1
            for cell_xml in row.findall(qn('w:tc')):
                location = f'{table_location} 行 {ri} 列 {ci}'
                counts['cells_attempted'] += 1
                try:
                    cell = _Cell(cell_xml, table)
                    text = cell.text
                    item = result.unit('table_cell', location, text, xml_path=tree.getpath(cell_xml))
                    counts['cells_read'] += 1
                    counts['paragraphs_read'] += len(cell_xml.findall(qn('w:p')))
                    for p in cell_xml.findall(qn('w:p')):
                        inspect_nodes(p, location)
                    for child in cell_xml:
                        if child.tag == qn('w:tbl'):
                            parse_table(child, cell, location+' / ')
                        elif child.tag not in (qn('w:p'), qn('w:tcPr')):
                            inspect_nodes(child, location)
                    span = cell_xml.find(qn('w:tcPr'))
                    span = span.find(qn('w:gridSpan')) if span is not None else None
                    ci += max(1, int(span.get(qn('w:val')))) if span is not None else 1
                except Exception:
                    # 若嵌套表格失败，已有父单元格文字也保留，但覆盖错误明确记录。
                    if not result.units or result.units[-1]['location'] != location:
                        result.unit('table_cell', location, '', 'read_failed', xml_path=tree.getpath(cell_xml))
                    result.issue('cell_read_failed', location, '此单元格或嵌套内容读取失败，可能遗漏。')
                    ci += 1

    for child in body:
        if child.tag == qn('w:p'):
            paragraph_index += 1
            location = f'DOCX 正文第 {paragraph_index} 段'
            try:
                result.unit('paragraph', location, Paragraph(child, doc).text, xml_path=tree.getpath(child))
                counts['paragraphs_read'] += 1
                inspect_nodes(child, location)
            except Exception:
                result.unit('paragraph', location, '', 'read_failed', xml_path=tree.getpath(child))
                result.issue('paragraph_read_failed', location, '本段读取失败，不能认定无内容。')
        elif child.tag == qn('w:tbl'):
            try:
                parse_table(child, doc)
            except Exception:
                result.issue('table_read_failed', 'DOCX 正文表格', '表格读取失败，可能遗漏。')
        elif child.tag != qn('w:sectPr'):
            inspect_nodes(child, 'DOCX 正文 / '+tree.getpath(child))
    for part in extras:
        item = result.item('unsupported_part', part, 'unsupported', '页眉页脚、批注或注释部分未纳入正文')
        result.issue('unsupported_part', part, item['message'], item)
    for key, read in [('tables_detected', 'tables_read'), ('cells_detected', 'cells_read'), ('paragraphs_detected', 'paragraphs_read')]:
        if counts[key] != counts[read]:
            result.issue('coverage_count_gap', 'DOCX 正文', f'{key}={counts[key]}，{read}={counts[read]}，存在未覆盖或读取失败区域。')
    result.report['table_coverage'] = 'physical_cells_accounted' if counts['cells_detected'] == counts['cells_read'] else 'gap_detected'
    result.report['limitations'].extend(['DOCX 段落/表格位置不等于 Word 页码。',
                                       '修订、文本框、图片及注释不自动转成正文事实；表格计数是物理XML单元格，不代表版面完整复原。'])
    return result


def parse_document(name, data):
    result = ParseResult(name, data)
    if len(data) > MAX_BYTES:
        return result.fail('size_limit', '单文件不能超过 20 MB', 'rejected').finish()
    suffix = Path(name).suffix.lower()
    if suffix not in ('.pdf', '.docx'):
        return result.fail('unsupported_format', '只支持 PDF 和 DOCX', 'rejected').finish()
    try:
        result = _parse_pdf(result, data) if suffix == '.pdf' else _parse_docx(result, data)
    except Exception:
        result.fail('file_read_failed', '文件读取失败，请检查损坏、格式或不支持的内容；未读取内容不能当作不存在。')
    if result.report['status'] not in ('failed', 'rejected') and not any(u['text'].strip() for u in result.units):
        result.issue('no_body_text', '全文', '未读取到正文文字；可能为空白、扫描或不支持的对象，需人工处理。')
    return result.finish()


def read_with_report(name, data):
    result = parse_document(name, data)
    if result.report['status'] in ('failed', 'rejected'):
        raise DocumentParseError(result.report)
    return result
