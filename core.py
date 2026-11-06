"""纯本地规则提取。字段均为原文摘录候选；绝不自动标为已核验。"""
from __future__ import annotations
import hashlib
import io
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
from document_parser import MAX_BYTES, PARSER_VERSION, DocumentParseError, read_with_report

FIELDS = ('法院', '案号', '争议焦点', '法律依据')
PENDING = '待人工核验'
PATTERNS = {
    '法院': r'(?:[\u4e00-\u9fff]{2,30}?人民法院)',
    '案号': r'[（(]\d{4}[）)][\u4e00-\u9fffA-Za-z0-9]{1,24}号',
    '争议焦点': r'(?:争议焦点|争议的焦点)[：:]\s*[^\n]+',
    '法律依据': r'《[^》\n]{1,80}》(?:第[一二三四五六七八九十百千万零〇\d]+条(?:之[一二三四五六七八九十\d]+)?(?:第[一二三四五六七八九十\d]+款)?)?',
}


def read_units(name: str, data: bytes) -> list[dict]:
    """兼容旧接口；失败异常同时携带结构化解析报告。"""
    return read_with_report(name, data).units


def extract(name: str, data: bytes) -> dict:
    parsed = read_with_report(name, data)
    units = parsed.units
    candidates = []
    for field, pattern in PATTERNS.items():
        for unit in units:
            for m in re.finditer(pattern, unit['text']):
                candidates.append({'字段': field, '原文摘录': m.group(),
                                   '原文位置': unit['location'], '字符起点': m.start(),
                                   '字符终点': m.end(), '核验状态': PENDING,
                                   '核验人': '', '核验时间': '', '核验备注': ''})
        if not any(c['字段'] == field for c in candidates):
            candidates.append({'字段': field, '原文摘录': '', '原文位置': '未定位',
                               '字符起点': None, '字符终点': None, '核验状态': PENDING,
                               '核验人': '', '核验时间': '', '核验备注': '未找到明确表述，禁止补写推断'})
    for i, c in enumerate(candidates):
        c['候选ID'] = str(i + 1)
    content = '\n'.join(u['text'] for u in units)
    # 标识来自上传文件名或正文；样本生成器保证两处均有标识。
    simulated = '模拟' in name or '【模拟数据' in content
    warnings = []
    if not content.strip():
        warnings.append('未读取到正文：可能为扫描件或空文件。此版本不含 OCR，请人工检查。')
    elif suffix_pdf(name) and any(not u['text'].strip() for u in units):
        warnings.append('存在未读取到文字的 PDF 页，请人工检查扫描页。')
    warnings.extend(i['message'] for i in parsed.report['issues'])
    warnings = list(dict.fromkeys(warnings))
    return {'id': hashlib.sha256(name.encode() + b'\0' + data).hexdigest(),
            '文件名': Path(name).name, '文件SHA256': hashlib.sha256(data).hexdigest(),
            '数据类型': '模拟数据（非真实案件）' if simulated else '用户上传（真实性未核验）',
            'units': units, 'candidates': candidates, 'warnings': warnings, 'audit': [],
            'original_bytes': bytes(data), 'parser_version': PARSER_VERSION, 'parse_report': parsed.report}


def suffix_pdf(name):
    return Path(name).suffix.lower() == '.pdf'


def review(record, candidate_id, status, reviewer, note):
    c = next(c for c in record['candidates'] if c['候选ID'] == candidate_id)
    if status not in (PENDING, '已人工核验', '提取有误'):
        raise ValueError('无效核验状态')
    if not reviewer.strip() or not note.strip():
        raise ValueError('请填写核验人和核验备注（核验范围、出处或错误原因）')
    if status == '已人工核验' and not c['原文摘录']:
        raise ValueError('无原文摘录的字段不能标为已人工核验')
    event = {'候选ID': candidate_id, '字段': c['字段'], '原状态': c['核验状态'],
             '新状态': status, '核验人': reviewer.strip(), '核验备注': note.strip(),
             '核验时间': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')}
    record['audit'].append(event)
    c.update({k: event[k] for k in ('核验人', '核验时间', '核验备注')})
    c['核验状态'] = status


def summary(record):
    row = {'文件名': record['文件名'], '数据类型': record['数据类型']}
    for field in FIELDS:
        values = list(dict.fromkeys(c['原文摘录'] for c in record['candidates'] if c['字段'] == field and c['原文摘录']))
        row[field] = '；'.join(values) or '未提取到明确内容'
    row['原文位置'] = '；'.join(dict.fromkeys(c['原文位置'] for c in record['candidates']))
    states = {c['核验状态'] for c in record['candidates']}
    row['核验状态'] = '提取有误' if '提取有误' in states else (PENDING if PENDING in states else '已人工核验')
    row['文件SHA256'] = record['文件SHA256']
    return row


def search(records, keyword='', courts=(), statuses=(), kinds=()):
    terms = keyword.casefold().split()
    result = []
    for record in records:
        row = summary(record)
        haystack = (' '.join(str(v) for v in row.values()) + '\n' + '\n'.join(u['text'] for u in record['units'])).casefold()
        if not all(t in haystack for t in terms):
            continue
        if courts and not any(c in row['法院'].split('；') for c in courts):
            continue
        if statuses and row['核验状态'] not in statuses:
            continue
        if kinds and row['数据类型'] not in kinds:
            continue
        result.append(record)
    return result


def safe_cell(value):
    # 防止用户上传的正文在 Excel 中变成公式。
    if isinstance(value, str):
        value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', value)
        if value.lstrip().startswith(('=', '+', '-', '@')):
            value = "'" + value
        return value[:32767]
    return value


def export_excel(records):
    summaries, details, sources, audits = [], [], [], []
    for r in records:
        summaries.append(summary(r))
        base = {'文件名': r['文件名'], '数据类型': r['数据类型'], '文件SHA256': r['文件SHA256']}
        details.extend({**base, **c} for c in r['candidates'])
        for u in r['units']:
            # Excel 单格有限，长页拆分保留全部正文。
            for start in range(0, max(1, len(u['text'])), 30000):
                sources.append({**base, '原文位置': u['location'], '分片字符起点': start,
                                '正文': u['text'][start:start + 30000]})
        audits.extend({**base, **a} for a in r['audit'])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        sheets = {'资料总表': summaries, '字段与出处': details, '原文摘录': sources, '核验日志': audits,
                  '使用说明': [{'说明': '全部提取结果初始为待人工核验。已人工核验表示用户录入的核验结论，系统未验证法律效力。模拟数据不能作为法律依据。字符区间为解析文本的零起点左闭右开区间。Excel超长候选单格最多32767字符，完整正文见原文摘录分片。'}]}
        for title, rows in sheets.items():
            frame = pd.DataFrame(rows if rows else [{'说明': '暂无记录'}])
            frame = frame.map(safe_cell)
            frame.to_excel(writer, sheet_name=title, index=False)
            ws = writer.sheets[title]
            ws.freeze_panes = 'A2'
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(65, max(16, len(str(col[0].value)) * 2 + 4))
    return buf.getvalue()
