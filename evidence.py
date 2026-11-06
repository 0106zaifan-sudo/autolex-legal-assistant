"""案件内的证据锚点：原始文件、解析快照、位置及连续引文共同校验。"""
import hashlib
import json
from case_schema import EvidenceSpan


def snapshot_hash(units):
    text = json.dumps(units, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(text.encode()).hexdigest()


def make_span(case_id, document, unit_index, start, end, quote):
    if hashlib.sha256(document.original_bytes).hexdigest() != document.file_sha256:
        raise ValueError('原始文件哈希不一致')
    if snapshot_hash(document.units) != document.parsed_text_sha256:
        raise ValueError('解析文本快照不一致')
    if not (type(unit_index) is int and 0 <= unit_index < len(document.units)
            and type(start) is int and type(end) is int):
        raise ValueError('无效原文位置')
    unit = document.units[unit_index]
    if not (0 <= start < end <= len(unit['text'])) or unit['text'][start:end] != quote:
        raise ValueError('引文和原文位置不一致')
    identity = json.dumps([case_id, document.document_id, document.file_sha256,
                           document.parsed_text_sha256, document.parser_version, unit_index, start, end])
    return EvidenceSpan(evidence_id='evidence_'+hashlib.sha256(identity.encode()).hexdigest()[:24],
                        case_id=case_id, document_id=document.document_id,
                        document_sha256=document.file_sha256, parsed_text_sha256=document.parsed_text_sha256,
                        parser_version=document.parser_version, unit_index=unit_index,
                        location=unit['location'], start=start, end=end, quote=quote)


def verify_span(case_id, document, span):
    expected = make_span(case_id, document, span.unit_index, span.start, span.end, span.quote)
    if span != expected:
        raise ValueError('证据不属于本案件、文档或快照')
    return span
