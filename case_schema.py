"""案件Schema：字面一致性、人工确认和信息缺失分开记录。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)


class EvidenceSpan(Model):
    evidence_id: str
    case_id: str
    document_id: str
    document_sha256: str
    parsed_text_sha256: str
    parser_version: str
    unit_index: int = Field(ge=0)
    location: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)


class DocumentSnapshot(Model):
    document_id: str
    file_name: str
    file_sha256: str
    parsed_text_sha256: str
    parser_version: str
    data_type: str
    units: list[dict]
    parse_report: dict
    candidates: list[dict] = Field(default_factory=list)
    original_bytes: bytes = Field(exclude=True, repr=False)

    def as_record(self):
        return {'id': self.document_id, '文件名': self.file_name, '文件SHA256': self.file_sha256,
                '数据类型': self.data_type, 'units': self.units, 'parser_version': self.parser_version,
                'parse_report': self.parse_report, 'candidates': self.candidates,
                'original_bytes': self.original_bytes, 'audit': []}


class CaseField(Model):
    value: str | None = None
    status: Literal['missing', 'unverified', 'ambiguous'] = 'missing'
    evidence_ids: list[str] = Field(default_factory=list)
    note: str = '未提供可确认信息，不自行补充'


class Statement(Model):
    statement_id: str
    kind: Literal['documented_fact', 'confirmed_fact', 'party_claim', 'ai_inference', 'unclassified']
    text: str
    evidence_ids: list[str] = Field(min_length=1)
    speaker: str | None = None
    origin: Literal['manual', 'ai', 'simulation', 'unknown']
    verification: Literal['unverified', 'human_confirmed'] = 'unverified'
    support_status: str = '引文一致性不等于真实性已确认'
    analysis_mode: str | None = None


class PendingItem(Model):
    pending_id: str
    kind: Literal['missing_information', 'coverage_gap', 'ai_inference_review', 'unclassified_review']
    text: str
    document_ids: list[str]
    evidence_ids: list[str] = Field(default_factory=list)
    coverage_refs: list[dict] = Field(default_factory=list)
    status: Literal['open', 'resolved'] = 'open'
    value: None = None


class CaseEvent(Model):
    event_id: str
    source_event_id: str
    statement_id: str
    evidence_id: str
    time_evidence_id: str | None
    time_state: Literal['explicit', 'unknown']
    time_text: str
    time_precision: Literal['date', 'minute', 'second', 'unknown']
    normalized_time: str | None
    chronology_status: str
    verification: Literal['unverified'] = 'unverified'


class HumanReview(Model):
    statement_id: str
    reviewer: str
    note: str
    scope: Literal['truth_confirmation']
    reviewed_at: str


class CaseBundle(Model):
    schema_version: Literal['1.0'] = '1.0'
    case_id: str
    title: str  # 操作者标签，不是自动提取/确认的法律案件名称。
    basic_info: dict[str, CaseField] = Field(default_factory=dict)
    documents: dict[str, DocumentSnapshot] = Field(default_factory=dict)
    evidence: dict[str, EvidenceSpan] = Field(default_factory=dict)
    facts: list[Statement] = Field(default_factory=list)
    claims: list[Statement] = Field(default_factory=list)
    inferences: list[Statement] = Field(default_factory=list)
    unclassified: list[Statement] = Field(default_factory=list)
    timeline: list[CaseEvent] = Field(default_factory=list)
    pending_items: list[PendingItem] = Field(default_factory=list)
    reviews: list[HumanReview] = Field(default_factory=list)
