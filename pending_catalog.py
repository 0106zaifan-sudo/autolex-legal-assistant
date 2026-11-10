"""生产与离线原型共享的可信完整物理行目录；不生成语义结论。"""
import hashlib
from pydantic import Field
from ai_analysis import StrictModel
from evidence import make_span
from multidoc_ai import digest
CATALOG_VERSION = 'pending-source-catalog/1'
MAX_CANDIDATES = 96
class CatalogError(ValueError):
 def __init__(self,code):self.code=code;super().__init__(code)

class PendingSelection(StrictModel):
    anchor_id: str = Field(pattern=r'^PE_[a-f0-9]{24}$')
    evidence_ids: list[str] = Field(min_length=1, max_length=4)
    reasoning: str = Field(min_length=1, max_length=600)


def build_pending_catalog(store, cid, batch):
    case = store.get_case(cid)
    whole_lines = {}
    for did in sorted(batch['records']):
        doc = case.documents[did]
        for ui, unit in enumerate(doc.units):
            cursor = 0
            for line in unit['text'].splitlines(keepends=True):
                whole_lines[(did, ui, cursor, cursor+len(line))] = line
                cursor += len(line)
    entries, excluded = [], []
    for source in batch['sources']:
        key = (source['document_id'], source['unit_index'], source['start'], source['end'])
        if whole_lines.get(key) != source['text']:
            excluded.append({k:source[k] for k in ('document_id','source_id','unit_index','start','end')})
            excluded[-1]['rule'] = 'physical_line_split'
            continue
        span = make_span(cid, case.documents[source['document_id']], source['unit_index'],
                         source['start'], source['end'], source['text'])
        if source['text'].count(span.quote) != 1:
            raise CatalogError('candidate_quote_not_unique')
        entry = {k:source[k] for k in ('case_id','document_id','file_sha256','parsed_text_sha256',
                                     'parser_version','source_id','unit_index','location','start','end')}
        entry.update(quote=span.quote, quote_sha256=hashlib.sha256(span.quote.encode()).hexdigest(),
                     evidence_span_id=span.evidence_id, scope='recorded_text_not_confirmed_fact')
        entry['candidate_id'] = 'PE_'+digest([CATALOG_VERSION,entry])[:24]
        entries.append(entry)
        if len(entries)>MAX_CANDIDATES:
            raise CatalogError('catalog_limit_exceeded')
    if len({e['candidate_id'] for e in entries}) != len(entries):
        raise CatalogError('candidate_id_collision')
    value = {'version':CATALOG_VERSION,'case_id':cid,'batch_sha256':batch['batch_sha256'],
             'entries':entries,'excluded':excluded}
    return {**value,'sha256':digest(value)}
