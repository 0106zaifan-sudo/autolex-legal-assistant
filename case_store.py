"""显式案件归档与人工确认。原文件仅留会话内存，不默认写入磁盘。"""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import re
import uuid
from core import extract
from document_parser import DocumentParseError, PARSER_VERSION, safe_name
from case_schema import (CaseBundle, CaseField, CaseEvent, DocumentSnapshot, HumanReview,
                         PendingItem, Statement)
from evidence import make_span, snapshot_hash, verify_span
from ai_analysis import (SECTIONS, analysis_context, validate_analysis, build_sources)


class CaseError(ValueError):
    pass


def _id(prefix):
    return prefix+'_'+uuid.uuid4().hex


class CaseStore:
    def __init__(self):
        self._cases = {}

    def list_cases(self):
        return {cid: case.title for cid, case in self._cases.items()}

    def _case(self, case_id):
        if case_id not in self._cases:
            raise CaseError('案件不存在于当前会话')
        return self._cases[case_id]

    def get_case(self, case_id):
        return self._case(case_id).model_copy(deep=True)

    def create_case(self, title):
        if not title.strip() or len(title) > 120:
            raise CaseError('请填写不超过120字符的案件标签')
        case = CaseBundle(case_id=_id('case'), title=title.strip(),
                          basic_info={name: CaseField() for name in ('法院', '案号', '事故日期', '车辆型号')})
        self._cases[case.case_id] = case
        return case.case_id

    def attach_document(self, case_id, name, data):
        case = self._case(case_id)
        try:
            record = extract(name, data)
        except DocumentParseError as exc:
            # 无法读取的文件也保留原件和报告；没有虚构正文或候选信息。
            record = {'id': hashlib.sha256(name.encode()+b'\0'+data).hexdigest(), '文件名': safe_name(name),
                      '文件SHA256': hashlib.sha256(data).hexdigest(), 'units': [],
                      'parser_version': PARSER_VERSION, 'parse_report': exc.report, 'candidates': [],
                      '数据类型': '模拟数据（非真实案件）' if '模拟' in name else '用户上传（真实性未核验）'}
        if record['id'] in case.documents:
            return record['id']
        document = DocumentSnapshot(document_id=record['id'], file_name=record['文件名'],
                                    file_sha256=record['文件SHA256'], parsed_text_sha256=snapshot_hash(record['units']),
                                    parser_version=record['parser_version'], data_type=record['数据类型'],
                                    units=deepcopy(record['units']), parse_report=deepcopy(record['parse_report']),
                                    candidates=deepcopy(record['candidates']), original_bytes=bytes(data))
        case.documents[document.document_id] = document
        for issue in document.parse_report['issues']:
            case.pending_items.append(PendingItem(pending_id=_id('pending'), kind='coverage_gap',
                text=issue['message'], document_ids=[document.document_id],
                coverage_refs=[{'document_id': document.document_id, 'coverage_id': issue.get('coverage_id'),
                                'code': issue['code'], 'location': issue['location']}]))
        self._refresh_basic(case)
        return document.document_id

    def attach_record(self, case_id, record):
        data = record.get('original_bytes')
        if not isinstance(data, bytes) or hashlib.sha256(data).hexdigest() != record['文件SHA256']:
            raise CaseError('没有可校验的原始文件，不能仅凭文件名归档')
        # 不信任外部传来的解析快照；从保留的原字节重新解析。
        return self.attach_document(case_id, record['文件名'], data)

    def _document(self, case, document_id):
        if document_id not in case.documents:
            raise CaseError('文档未明确加入本案件')
        return case.documents[document_id]

    def add_evidence(self, case_id, document_id, unit_index, start, end, quote):
        case = self._case(case_id)
        document = self._document(case, document_id)
        try:
            span = make_span(case_id, document, unit_index, start, end, quote)
        except ValueError as exc:
            raise CaseError(str(exc)) from None
        case.evidence[span.evidence_id] = span
        return span.evidence_id

    def _references(self, case, evidence_ids):
        spans = []
        for eid in evidence_ids:
            if eid not in case.evidence:
                raise CaseError('引用不属于当前案件')
            span = case.evidence[eid]
            verify_span(case.case_id, self._document(case, span.document_id), span)
            spans.append(span)
        if not spans:
            raise CaseError('提取内容必须保留证据引用')
        return spans

    def _refresh_basic(self, case):
        for field in ('法院', '案号'):
            values = {}
            for doc in case.documents.values():
                for c in doc.candidates:
                    if c['字段'] == field and c['原文摘录']:
                        index = next(i for i, u in enumerate(doc.units) if u['location'] == c['原文位置'])
                        eid = self.add_evidence(case.case_id, doc.document_id, index, c['字符起点'], c['字符终点'], c['原文摘录'])
                        values.setdefault(c['原文摘录'], []).append(eid)
            if len(values) == 1:
                value, ids = next(iter(values.items()))
                case.basic_info[field] = CaseField(value=value, status='unverified', evidence_ids=ids,
                                                  note='原文规则候选，未确认属于本案')
            elif values:
                case.basic_info[field] = CaseField(status='ambiguous', evidence_ids=[eid for ids in values.values() for eid in ids],
                                                  note='不同材料存在多个候选，不自动选择')

    def _append_statement(self, case, text, kind, evidence_ids, origin='manual', speaker=None, analysis_mode=None):
        spans = self._references(case, evidence_ids)
        if kind != 'ai_inference' and not any(text and text in span.quote for span in spans):
            raise CaseError('事实或主张正文必须直接摘自引文，不允许补写')
        if speaker and not any(speaker in span.quote for span in spans):
            raise CaseError('说话人未出现在引文，不能自行补充')
        identity = json.dumps([case.case_id, text, kind, sorted(evidence_ids)], ensure_ascii=False)
        sid = 'statement_'+hashlib.sha256(identity.encode()).hexdigest()[:24]
        collection = {'documented_fact': case.facts, 'party_claim': case.claims,
                      'ai_inference': case.inferences, 'unclassified': case.unclassified}[kind]
        if not any(row.statement_id == sid for row in collection):
            collection.append(Statement(statement_id=sid, kind=kind, text=text, evidence_ids=evidence_ids,
                                        speaker=speaker, origin=origin, analysis_mode=analysis_mode,
                                        support_status='推断支持关系待人工核验' if kind == 'ai_inference' else '引文已校验，真实性未确认'))
        return sid

    def record_basic_info(self, case_id, field, value, evidence_ids):
        case = self._case(case_id)
        if field not in case.basic_info:
            raise CaseError('未知基本信息字段')
        spans = self._references(case, evidence_ids)
        if not value.strip() or not any(value in span.quote for span in spans):
            raise CaseError('基本信息必须直接摘自本案引用，不自动补充或归一化未知信息')
        case.basic_info[field] = CaseField(value=value, status='unverified', evidence_ids=evidence_ids,
                                          note='用户选择的原文候选，归属与真实性仍待核实')

    def record_statement(self, case_id, text, kind, evidence_ids, speaker=None):
        if kind not in ('documented_fact', 'party_claim', 'unclassified'):
            raise CaseError('不能直接创建已确认事实或冒充AI推断')
        case = self._case(case_id)
        sid = self._append_statement(case, text, kind, evidence_ids, speaker=speaker)
        if kind == 'unclassified' and not any(p.pending_id == 'review_'+sid for p in case.pending_items):
            docs = list(dict.fromkeys(case.evidence[eid].document_id for eid in evidence_ids))
            case.pending_items.append(PendingItem(pending_id='review_'+sid, kind='unclassified_review',
                                                 text='摘录尚未确定类别，待人工分类', document_ids=docs, evidence_ids=evidence_ids))
        return sid

    def record_missing(self, case_id, text, document_ids):
        case = self._case(case_id)
        if not text.strip() or not document_ids:
            raise CaseError('待核实事项须注明问题及检查的文档范围')
        for did in document_ids:
            self._document(case, did)
        pending = PendingItem(pending_id=_id('pending'), kind='missing_information', text=text.strip(), document_ids=document_ids)
        case.pending_items.append(pending)
        return pending.pending_id

    def confirm_fact(self, case_id, statement_id, reviewer, note):
        case = self._case(case_id)
        if not reviewer.strip() or not note.strip():
            raise CaseError('确认事实需填写复核人及真实性核实依据，不能仅核对文字')
        statement = next((s for s in case.facts if s.statement_id == statement_id), None)
        if statement is None or statement.kind != 'documented_fact':
            raise CaseError('只有未确认的材料记载事实可以申请人工确认，主张或推断不能直接升级')
        spans = self._references(case, statement.evidence_ids)
        if any(re.search(r'主张|称|回忆|陈述|认为|否认|自述|表示|供述|推测|可能|估计', span.quote) for span in spans):
            raise CaseError('引文包含主张或不确定表述，不能仅凭此将内容确认成事实')
        statement.kind = 'confirmed_fact'
        statement.verification = 'human_confirmed'
        statement.support_status = '用户录入的真实性复核结论，系统未验证复核人身份或材料真实'
        case.reviews.append(HumanReview(statement_id=statement_id, reviewer=reviewer.strip(), note=note.strip(),
                                        scope='truth_confirmation', reviewed_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')))

    def _validated_result(self, document, result):
        if not isinstance(result, dict) or not isinstance(result.get('sections'), dict) or set(result['sections']) != set(SECTIONS):
            raise CaseError('分析结构无效')
        record = document.as_record()
        # 导入导出的JSON也必须重新执行绑定检查，不能信任“已校验”字样。
        raw = {key: result.get(key) for key in analysis_context(record)}
        for section in SECTIONS:
            raw[section] = []
            for row in result.get('sections', {}).get(section, []):
                item = {key: row[key] for key in ('kind', 'text', 'reasoning')}
                item['sources'] = [{k: ref[k] for k in ('source_id', 'quote')} for ref in row['sources']]
                if section == 'timeline':
                    event = {k: row['event_source'][k] for k in ('source_id', 'quote')}
                    item.update(event_source=event, time_state=row['time_state'], time_text=row['time_text'],
                                time_precision=row['time_precision'], time_source=event if row['time_state'] == 'explicit' else None)
                raw[section].append(item)
        canonical = validate_analysis(raw, record, build_sources(record))
        if (canonical['sections'] != result.get('sections') or result.get('file_sha256') != document.file_sha256
                or result.get('file_name') != document.file_name):
            raise CaseError('分析结果、时间锚点或来源被修改，不予导入')
        return canonical

    def import_analysis(self, case_id, document_id, result):
        case = self._case(case_id)
        document = self._document(case, document_id)
        try:
            canonical = self._validated_result(document, result)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise CaseError('AI结果不属于当前文档/快照，或证据绑定未通过，未写入案件') from None
        # 所有结构校验先完成，之后才变更案件，避免部分导入。
        for section in SECTIONS:
            for row in canonical['sections'][section]:
                evidence_ids = [self.add_evidence(case_id, document_id, ref['unit_index'], ref['start'], ref['end'], ref['quote']) for ref in row['sources']]
                kind = {'事实': 'documented_fact', '主张': 'party_claim', '推断': 'ai_inference'}[row['kind']]
                text = row['reasoning'] if kind == 'ai_inference' else row['text']
                mode = str(result.get('mode', '来源模式未提供'))[:200]
                origin = ('simulation' if '模拟' in mode or '离线' in mode
                          else ('ai' if mode == 'AI生成（待人工核验）' and result.get('model') else 'unknown'))
                sid = self._append_statement(case, text, kind, evidence_ids, origin=origin, analysis_mode=mode)
                event_id = 'event_' + hashlib.sha256((case_id+row.get('statement_id', '')).encode()).hexdigest()[:24]
                if section == 'timeline' and not any(event.event_id == event_id for event in case.timeline):
                    time_ref = row['time_source']
                    time_id = self.add_evidence(case_id, document_id, time_ref['unit_index'], time_ref['start'], time_ref['end'], time_ref['quote']) if time_ref else None
                    case.timeline.append(CaseEvent(event_id=event_id, source_event_id=row['statement_id'], statement_id=sid, evidence_id=evidence_ids[0],
                        time_evidence_id=time_id, time_state=row['time_state'], time_text=row['time_text'],
                        time_precision=row['time_precision'], normalized_time=row['normalized_time'], chronology_status=row['chronology_status']))
                    if row['time_state'] == 'unknown':
                        case.pending_items.append(PendingItem(pending_id='time_'+event_id, kind='missing_information',
                            text='此事件未绑定明确时间，需人工核实；不代表现实中不存在时间记录',
                            document_ids=[document_id], evidence_ids=evidence_ids))
                if kind == 'ai_inference':
                    key = 'review_'+sid
                    if not any(item.pending_id == key for item in case.pending_items):
                        case.pending_items.append(PendingItem(pending_id=key, kind='ai_inference_review', text=text,
                                                             document_ids=[document_id], evidence_ids=evidence_ids))

    def get_original(self, case_id, document_id):
        doc = self._document(self._case(case_id), document_id)
        if hashlib.sha256(doc.original_bytes).hexdigest() != doc.file_sha256:
            raise CaseError('原文件一致性检查失败')
        return doc.file_name, bytes(doc.original_bytes)

    def link_evidence(self, case_id, left_id, right_id):
        from evidence_relations import compare_quotes
        from case_schema import EvidenceRelation
        case=self._case(case_id)
        left,right=self._references(case,[left_id,right_id])
        if left.document_id==right.document_id:
            raise CaseError('跨文件关系必须引用不同文档')
        # 改名副本也不作为独立文件互证。
        if left.document_sha256==right.document_sha256:
            raise CaseError('相同文件字节的副本不作为跨文件互证')
        proposal=compare_quotes(left.quote,right.quote)
        if proposal is None:raise CaseError('没有受支持的共同事件/主题，不生成关系')
        ids=sorted([left_id,right_id])
        rid='relation_'+hashlib.sha256(json.dumps([case_id,ids]).encode()).hexdigest()[:24]
        old=next((r for r in case.relations if r.relation_id==rid),None)
        if old:return old.model_copy(deep=True)
        kind,method,reason=proposal
        relation=EvidenceRelation(relation_id=rid,left_id=ids[0],right_id=ids[1],relation_type=kind,method=method,reason=reason)
        if case.schema_version=='1.0':case.schema_version='1.1'
        case.relations.append(relation)
        return relation.model_copy(deep=True)

    def discover_relations(self, case_id):
        from itertools import combinations
        from evidence_relations import compare_quotes
        case=self._case(case_id)
        # 先完整复核，再写入，避免损坏锚点导致部分发现结果。
        spans=self._references(case,list(case.evidence)) if case.evidence else []
        if len(spans)>150:raise CaseError('请将本次审阅证据控制在150条以内')
        for a,b in combinations(spans,2):
            if a.document_id!=b.document_id and a.document_sha256!=b.document_sha256 and compare_quotes(a.quote,b.quote):
                self.link_evidence(case_id,a.evidence_id,b.evidence_id)

    def review_relation(self, case_id, relation_id, status, relation_type, reviewer, reason):
        from case_schema import RelationReview
        case=self._case(case_id)
        relation=next((r for r in case.relations if r.relation_id==relation_id),None)
        if relation is None:raise CaseError('关系不属于本案')
        self._references(case,[relation.left_id,relation.right_id])
        if not reviewer.strip() or not reason.strip():raise CaseError('须填写复核人及具体理由')
        previous=next((r.review_id for r in reversed(case.relation_reviews) if r.relation_id==relation_id),None)
        review=RelationReview(review_id=_id('relation_review'),relation_id=relation_id,status=status,
                              relation_type=relation_type,reviewer=reviewer.strip(),reason=reason.strip(),
                              reviewed_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),previous_review_id=previous)
        case.relation_reviews.append(review)

    def export_json(self, case_id):
        case=self._case(case_id)
        if case.evidence:self._references(case,list(case.evidence))
        for relation in case.relations:
            self._references(case,[relation.left_id,relation.right_id])
        return case.model_dump_json(indent=2)
