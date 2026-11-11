"""会话案件的显式离线工作包。内存读取、重解析、全图验证后单次提交。"""
from copy import deepcopy
from datetime import datetime
import hashlib
import io
import json
import re
import stat
import threading
import zipfile
from pathlib import PurePosixPath
from case_schema import CaseBundle, EvidenceSpan
from case_store import CaseStore
from document_parser import PARSER_VERSION, MAX_BYTES
from evidence import verify_span
from ai_analysis import empty_analysis, build_sources, validate_analysis, _apply_output_quality

_COMMIT_LOCK=threading.RLock()
FORMAT_VERSION='autolex-workspace/1.0'
MAX_ZIP_BYTES=32*1024*1024
MAX_EXPANDED_BYTES=64*1024*1024
MAX_JSON_BYTES=8*1024*1024
MAX_ENTRIES=128
MAX_DOCUMENTS=16
MAX_RATIO=200
HASH=re.compile(r'^[0-9a-f]{64}$')
CASE_ID=re.compile(r'^case_[0-9a-f]{32}$')
RECEIPT_KEYS=frozenset('run_id case_id execution_mode provider base_url requested_model provider_model provider_response_id sdk_version protocol schema_version prompt_version prompt_sha256 batch_sha256 document_snapshots input_budget started_at call_status provider_status format_status evidence_status semantic_status http_status token_usage billing duration_ms candidate_version candidate_catalog_sha256 candidate_selection_ids pending_catalog_version pending_catalog_sha256 pending_selection_ids pending_statement_ids analysis_output_sha256 pending_alias_version pending_alias_map_sha256 pending_alias_selection'.split())
SECRET_KEYS=frozenset(('api_key','openai_api_key','deepseek_api_key','gh_token','github_token','password','password_hash','authorization','secrets','authorized_batch','principal','auth_state'))
CREDENTIAL=re.compile(r'(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{25,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY)')


class WorkspaceError(ValueError):
    def __init__(self,code):
        self.code=code
        super().__init__('工作包未通过安全校验（'+code+'）；未导入或覆盖案件。')


def require(condition,code):
    if not condition:raise WorkspaceError(code)


def sha(data):return hashlib.sha256(data).hexdigest()


def encoded(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()


def safe_tree(value,depth=0):
    require(depth<=50,'json_depth_limit')
    if isinstance(value,dict):
        require(not any(str(k).lower() in SECRET_KEYS for k in value),'forbidden_credentials_or_authorization')
        for v in value.values():safe_tree(v,depth+1)
    elif isinstance(value,list):
        for v in value:safe_tree(v,depth+1)
    elif isinstance(value,str):require(not CREDENTIAL.search(value),'credential_pattern_detected')


def load_json(data,limit=MAX_JSON_BYTES):
    require(type(data) is bytes and len(data)<=limit,'json_size_limit')
    def pairs(items):
        result={}
        for k,v in items:
            require(k not in result,'duplicate_json_key');result[k]=v
        return result
    try:
        value=json.loads(data.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda _x:(_ for _ in ()).throw(WorkspaceError('json_nonfinite')))
        require(isinstance(value,dict),'json_object_required');safe_tree(value);return value
    except WorkspaceError:raise
    except Exception:raise WorkspaceError('invalid_json') from None


def safe_path(name):
    return (isinstance(name,str) and name and len(name)<=255 and not any(ord(c)<32 for c in name)
            and '\\' not in name and ':' not in name and not name.startswith('/')
            and all(p not in ('','.','..') for p in name.split('/')) and str(PurePosixPath(name))==name)


def zip_members(data,*,nested=False):
    require(type(data) is bytes and len(data)<=MAX_ZIP_BYTES,'zip_size_limit')
    require(data.startswith(b'PK\x03\x04') and data[-22:-18]==b'PK\x05\x06' and data[-18:-14]==b'\x00'*4,'zip_wrapper_or_multidisk')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos=z.infolist();require(0<len(infos)<=(2000 if nested else MAX_ENTRIES),'zip_entry_limit')
            require(not z.comment,'zip_comment_forbidden')
            total=0;names=set()
            for i in infos:
                name=i.filename
                require(safe_path(name.rstrip('/')) if nested and i.is_dir() else safe_path(name),'unsafe_zip_path')
                key=name.rstrip('/').casefold();require(key not in names,'duplicate_zip_entry');names.add(key)
                require(nested or (not i.is_dir() and not(i.external_attr&0x10)),'zip_directory_forbidden')
                modes=(0,stat.S_IFDIR) if nested and i.is_dir() else (0,stat.S_IFREG)
                require(stat.S_IFMT(i.external_attr>>16) in modes,'zip_special_file')
                offset=i.header_offset
                require(0<=offset<=len(data)-30 and data[offset:offset+4]==b'PK\x03\x04','zip_local_header')
                require(int.from_bytes(data[offset+6:offset+8],'little')==i.flag_bits and int.from_bytes(data[offset+8:offset+10],'little')==i.compress_type,'zip_header_mismatch')
                require(not(i.flag_bits&1),'zip_encrypted')
                require(i.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'zip_compression_method')
                require(not i.comment,'zip_entry_comment')
                require(0<=i.file_size<=MAX_BYTES and i.compress_size>=0,'zip_entry_size')
                require(i.file_size/max(1,i.compress_size)<=MAX_RATIO,'zip_ratio_limit')
                total+=i.file_size;require(total<=MAX_EXPANDED_BYTES,'zip_expanded_limit')
                if not nested:
                    require(name in ('manifest.json','case.json','analysis.json') or re.fullmatch(r'files/[0-9a-f]{64}\.(?:pdf|docx)',name),'unexpected_zip_member')
            output={}
            for i in infos:
                with z.open(i) as f:data_part=f.read(i.file_size+1)
                require(len(data_part)==i.file_size,'zip_actual_size')
                output[i.filename]=data_part
            return output
    except WorkspaceError:raise
    except Exception:raise WorkspaceError('invalid_zip') from None


def check_original(name,data):
    require(type(data) is bytes and 0<len(data)<=MAX_BYTES,'original_size_limit')
    require(safe_path(name) and '/' not in name and len(name)<=200 and name.lower().endswith(('.pdf','.docx')),'original_filename')
    require(not CREDENTIAL.search(data.decode('latin1')),'credential_pattern_detected')
    if name.lower().endswith('.docx'):
        members=zip_members(data,nested=True)
        require('[Content_Types].xml' in members and 'word/document.xml' in members,'invalid_docx')
        for path,content in members.items():
            require(not re.search(r'(?i)vba|activex|embeddings/|\.(exe|dll|js|vbs|ps1)$',path),'active_docx_content')
            if path.lower().endswith(('.xml','.rels')):
                require(b'<!DOCTYPE' not in content.replace(b'\x00',b'').upper() and b'<!ENTITY' not in content.replace(b'\x00',b'').upper(),'xml_entities_forbidden')


def timestamp(value):
    try:require(datetime.fromisoformat(value).utcoffset() is not None,'review_time_invalid')
    except WorkspaceError:raise
    except Exception:raise WorkspaceError('review_time_invalid') from None


def unique(rows,attr):
    result={getattr(row,attr):row for row in rows}
    require(len(result)==len(rows),'duplicate_graph_identifier');return result


def validate_graph(store,cid):
    """检查整个关联图，不以Pydantic类型通过替代证据/时间/审阅校验。"""
    case=store._case(cid)
    require(CASE_ID.fullmatch(cid) is not None,'case_id_format')
    require(case.schema_version in ('1.1','1.2'),'case_version_unsupported')
    require(case.schema_version=='1.2' or (not case.analysis_receipts and not any(r.ai_origins for r in case.relations)),'case_version_fields_mismatch')
    require(0<len(case.title.strip())<=120,'case_title_invalid')
    require(len(case.documents)<=MAX_DOCUMENTS and sum(len(getattr(case,key)) for key in ('evidence','facts','claims','inferences','unclassified','timeline','pending_items','relations','relation_reviews','reviews'))<=10000,'graph_size_limit')
    def refs(ids,allow_empty=False):
        require(allow_empty or bool(ids),'missing_evidence_reference')
        require(all(eid in case.evidence for eid in ids),'foreign_evidence_reference')
        return [case.evidence[eid] for eid in ids]
    def docs(ids):require(bool(ids) and all(did in case.documents for did in ids),'foreign_document_reference')
    for eid,span in case.evidence.items():
        require(eid==span.evidence_id and span.document_id in case.documents and span.case_id==cid,'evidence_ownership')
        verify_span(cid,case.documents[span.document_id],span)
    # 独立副本重放写入约束，只验证，不将新时间戳/确认写回工作包案件。
    replay=CaseStore();replay._cases[cid]=CaseBundle(case_id=cid,title=case.title,documents=case.documents,evidence=case.evidence)
    all_statements=[]
    for section,expected in [('facts',('documented_fact','confirmed_fact')),('claims',('party_claim',)),('inferences',('ai_inference',)),('unclassified',('unclassified',))]:
        for row in getattr(case,section):
            require(row.kind in expected,'statement_category_mismatch')
            refs(row.evidence_ids)
            require(row.verification==('human_confirmed' if row.kind=='confirmed_fact' else 'unverified'),'statement_verification_mismatch')
            kind='documented_fact' if row.kind=='confirmed_fact' else row.kind
            sid=replay._append_statement(replay._case(cid),row.text,kind,row.evidence_ids,origin=row.origin,speaker=row.speaker,analysis_mode=row.analysis_mode)
            require(sid==row.statement_id,'statement_identity_mismatch');all_statements.append(row)
            if kind=='ai_inference' or (kind=='documented_fact' and row.origin!='manual'):
                for span in refs(row.evidence_ids):
                    record=case.documents[span.document_id].as_record();sources=build_sources(record)
                    matches=[s for s in sources if s['unit_index']==span.unit_index and s['start']<=span.start and span.end<=s['start']+len(s['text']) and s['text'].count(span.quote)==1]
                    require(len(matches)==1,'statement_source_ambiguous')
                    ref={'source_id':matches[0]['source_id'],'quote':span.quote}
                    raw=empty_analysis(record);section='pending_evidence' if kind=='ai_inference' else 'facts'
                    raw[section]=[{'kind':'推断' if kind=='ai_inference' else '事实','text':span.quote if kind=='ai_inference' else row.text,
                                   'reasoning':row.text if kind=='ai_inference' else '', 'sources':[ref]}]
                    _apply_output_quality(validate_analysis(raw,record,sources),record)

    statements=unique(all_statements,'statement_id')
    reviewed={}
    for review in case.reviews:
        require(review.statement_id in statements and review.statement_id not in reviewed,'human_review_reference')
        row=statements[review.statement_id];require(row.kind=='confirmed_fact','unexpected_truth_review')
        timestamp(review.reviewed_at)
        replay.confirm_fact(cid,row.statement_id,review.reviewer,review.note)
        reviewed[row.statement_id]=review
    require(all(row.statement_id in reviewed for row in case.facts if row.kind=='confirmed_fact'),'confirmed_fact_without_review')
    for key,field in case.basic_info.items():
        spans=refs(field.evidence_ids,allow_empty=field.status=='missing')
        require(key in ('法院','案号','事故日期','车辆型号'),'unknown_basic_field')
        if field.status=='missing':require(field.value is None and not field.evidence_ids,'missing_field_has_value')
        elif field.status=='ambiguous':require(field.value is None and bool(spans),'ambiguous_field_invalid')
        else:require(bool(field.value) and bool(field.value.strip()) and any(field.value in s.quote for s in spans),'basic_field_not_in_quote')
    unique(case.timeline,'event_id')
    for event in case.timeline:
        require(event.statement_id in statements and event.evidence_id in case.evidence,'timeline_reference')
        statement=statements[event.statement_id];anchor=case.evidence[event.evidence_id]
        require(statement.kind in ('documented_fact','confirmed_fact','party_claim') and event.evidence_id in statement.evidence_ids,'timeline_statement_kind')
        record=case.documents[anchor.document_id].as_record();sources=build_sources(record)
        matches=[s for s in sources if s['unit_index']==anchor.unit_index and s['start']<=anchor.start and anchor.end<=s['start']+len(s['text']) and s['text'].count(anchor.quote)==1]
        require(len(matches)==1,'timeline_source_ambiguous')
        ref={'source_id':matches[0]['source_id'],'quote':anchor.quote}
        row={'kind':'主张' if statement.kind=='party_claim' else '事实','text':statement.text,'reasoning':'','sources':[deepcopy(ref)],'event_source':deepcopy(ref),
             'time_state':event.time_state,'time_text':event.time_text,'time_precision':event.time_precision,
             'time_source':deepcopy(ref) if event.time_state=='explicit' else None}
        raw=empty_analysis(record);raw['timeline']=[row];canonical=validate_analysis(raw,record,sources)['sections']['timeline'][0]
        require(event.source_event_id==canonical['statement_id'] and event.event_id=='event_'+sha((cid+event.source_event_id).encode())[:24],'timeline_identity')
        require(event.normalized_time==canonical['normalized_time'],'timeline_normalized_time')
        if canonical['time_source']:
            time=canonical['time_source'];spans=refs([event.time_evidence_id]);actual=spans[0]
            require((actual.document_id,actual.unit_index,actual.start,actual.end,actual.quote)==(anchor.document_id,time['unit_index'],time['start'],time['end'],time['quote']),'timeline_time_binding')
        else:require(event.time_evidence_id is None,'unknown_time_reference')
        allowed=('时间未知，未参与排序',) if event.time_state=='unknown' else ('原文时间，先后不代表因果','同日含仅日期记录，日内顺序待核实','同分钟记录未确定秒级顺序')
        require(event.chronology_status in allowed,'timeline_chronology_status')
    unique(case.pending_items,'pending_id')
    for pending in case.pending_items:
        require(bool(pending.text.strip()),'empty_pending_item')
        docs(pending.document_ids);spans=refs(pending.evidence_ids,allow_empty=True)
        require(all(s.document_id in pending.document_ids for s in spans),'pending_evidence_scope')
        if pending.pending_id.startswith('time_'):
            event=next((e for e in case.timeline if pending.pending_id=='time_'+e.event_id),None)
            require(event is not None and event.time_state=='unknown' and pending.evidence_ids==statements[event.statement_id].evidence_ids,'pending_time_reference')
        if pending.kind in ('ai_inference_review','unclassified_review'):

            sid=pending.pending_id.removeprefix('review_')
            require(pending.pending_id.startswith('review_') and sid in statements,'pending_statement_reference')
            expected='ai_inference' if pending.kind=='ai_inference_review' else 'unclassified'
            require(statements[sid].kind==expected and set(pending.evidence_ids)==set(statements[sid].evidence_ids),'pending_statement_mismatch')
        if pending.kind=='ai_inference_review':require(pending.text==statements[pending.pending_id.removeprefix('review_')].text,'pending_inference_text')
        require(pending.kind!='coverage_gap' or bool(pending.coverage_refs),'coverage_reference_missing')
        for ref in pending.coverage_refs:

            require(ref.get('document_id') in pending.document_ids,'coverage_document_reference')
            report=case.documents[ref['document_id']].parse_report
            require(any(ref.get('coverage_id')==issue.get('coverage_id') and ref.get('code')==issue['code'] and ref.get('location')==issue['location'] for issue in report['issues']),'coverage_reference')
    from evidence_relations import compare_quotes
    relations=unique(case.relations,'relation_id')
    for relation in case.relations:
        left,right=refs([relation.left_id,relation.right_id])
        require(left.document_id!=right.document_id and left.document_sha256!=right.document_sha256,'relation_independence')
        if relation.method=='ai_multidoc/v1':
            from multidoc_ai import digest
            require(relation.relation_id=='ai_relation_'+digest([cid,sorted([relation.left_id,relation.right_id]),relation.relation_type,relation.reason])[:24],'relation_identity')
            require(bool(relation.ai_origins),'missing_ai_relation_origin')
            for origin in relation.ai_origins:validate_ai_origin(store,cid,relation,origin)
        else:
            require(not relation.ai_origins,'unexpected_ai_origin')
            proposal=compare_quotes(left.quote,right.quote);require(proposal is not None,'unsupported_relation')
            require((relation.relation_type,relation.method,relation.reason)==proposal,'relation_rule_mismatch')
            expected='relation_'+sha(json.dumps([cid,sorted([relation.left_id,relation.right_id])]).encode())[:24]
            require(relation.relation_id==expected,'relation_identity')
    chain={};reviews=unique(case.relation_reviews,'review_id');previous_times={}
    for review in case.relation_reviews:
        require(review.relation_id in relations and review.reviewer.strip() and review.reason.strip(),'relation_review_reference')
        require(re.fullmatch(r'relation_review_[0-9a-f]{32}',review.review_id) is not None,'review_id_invalid')
        require(review.previous_review_id==chain.get(review.relation_id),'relation_review_chain')
        timestamp(review.reviewed_at);now=datetime.fromisoformat(review.reviewed_at)
        require(review.relation_id not in previous_times or now>=previous_times[review.relation_id],'relation_review_time_order')
        chain[review.relation_id]=review.review_id;previous_times[review.relation_id]=now
    validate_receipts(case)


def validate_receipts(case,*,require_pending_statements=True):
    runs=set();catalogs={}
    for receipt in case.analysis_receipts:
        require(set(receipt)<=RECEIPT_KEYS and receipt.get('case_id')==case.case_id,'receipt_fields_or_case')
        require(receipt.get('run_id') and receipt['run_id'] not in runs,'receipt_duplicate_run');runs.add(receipt['run_id'])
        if receipt.get('schema_version')!='multidoc-analysis/1.4':
            require(not any(k in receipt for k in ('pending_alias_version','pending_alias_map_sha256','pending_alias_selection')),'receipt_protocol_fields_mismatch')
        snapshots=receipt.get('document_snapshots',[])
        require(isinstance(snapshots,list) and 2<=len(snapshots)<=4 and len({s['document_id'] for s in snapshots})==len(snapshots),'receipt_document_scope')
        for snapshot in snapshots:
            require(set(snapshot)=={'document_id','file_sha256','parsed_text_sha256','parser_version'},'receipt_snapshot_fields')
            doc=case.documents.get(snapshot['document_id']);require(doc is not None,'receipt_document_reference')
            require(all(getattr(doc,k)==v for k,v in snapshot.items()),'receipt_snapshot_mismatch')
        require(receipt.get('provider') in ('openai','deepseek') and receipt.get('format_status')=='passed' and receipt.get('evidence_status')=='passed','receipt_validation_status')
        require(receipt.get('schema_version') in ('multidoc-analysis/1.0','multidoc-analysis/1.1','multidoc-analysis/1.2','multidoc-analysis/1.3','multidoc-analysis/1.4'),'receipt_schema_version')
        if receipt['schema_version'] in ('multidoc-analysis/1.2','multidoc-analysis/1.3','multidoc-analysis/1.4'):
            if receipt['schema_version']=='multidoc-analysis/1.4':
                from multidoc_v14 import validate_saved_receipt
            elif receipt['schema_version']=='multidoc-analysis/1.3':
                from multidoc_v13 import validate_saved_receipt
            else:
                from multidoc_v12 import validate_saved_receipt
            try:validate_saved_receipt(case,receipt,require_statements=require_pending_statements)
            except (ValueError,KeyError,TypeError):require(False,'receipt_pending_selection_invalid')
        elif receipt['schema_version']=='multidoc-analysis/1.1':
            from multidoc_ai import prepare_case
            from timeline_candidates import build_event_catalog,CANDIDATE_VERSION
            from security import Settings
            require(receipt.get('candidate_version')==CANDIDATE_VERSION,'receipt_candidate_version')
            key=tuple(sorted(s['document_id'] for s in snapshots))
            if key not in catalogs:
                temp=CaseStore();temp._cases[case.case_id]=case
                batch=prepare_case(temp,case.case_id,list(key),Settings(provider=receipt['provider'],model=receipt.get('requested_model','')))
                catalogs[key]=build_event_catalog(batch)
            catalog=catalogs[key];ids=receipt.get('candidate_selection_ids')
            require(receipt.get('candidate_catalog_sha256')==catalog['sha256'],'receipt_candidate_catalog')
            require(isinstance(ids,list) and len(ids)<=24 and len(ids)==len(set(ids)) and set(ids)<={c['candidate_id'] for c in catalog['candidates']},'receipt_candidate_ids')
        usage=receipt.get('token_usage')
        if usage is not None:
            require(isinstance(usage,dict),'receipt_usage_type')
            for key in ('input_tokens','output_tokens','total_tokens'):
                if key in usage:require(type(usage[key]) is int and usage[key]>=0,'receipt_usage_count')
        if 'billing' in receipt:
            from ai_providers import billing_record
            require(receipt['billing']==billing_record(usage),'receipt_billing_mismatch')
        safe_tree(receipt)


def validate_ai_origin(store,cid,relation,origin):
    from multidoc_ai import prepare_case,validate_case_output,empty_analysis,SCHEMA_VERSION,PROMPT_VERSION
    from security import Settings
    allowed={'batch_sha256','left','right','relation_type','reasoning','prompt_version','prompt_sha256','provider','requested_model','provider_model','run_id'}
    require(set(origin)==allowed,'ai_origin_fields');case=store._case(cid)
    for side in ('left','right'):
        data=origin[side];span=EvidenceSpan.model_validate({k:v for k,v in data.items() if k!='source_id'},strict=True)
        require(span.evidence_id in case.evidence and case.evidence[span.evidence_id]==span,'ai_origin_evidence')
        verify_span(cid,case.documents[span.document_id],span)
    require(origin['relation_type']==relation.relation_type and origin['reasoning']==relation.reason,'ai_origin_relation_mismatch')
    # 重叠摘录去重允许历史原建议范围不同，但必须与已存关系两侧分别重叠。
    a,b=(case.evidence[relation.left_id],case.evidence[relation.right_id])
    x,y=(case.evidence[origin['left']['evidence_id']],case.evidence[origin['right']['evidence_id']])
    def overlap(p,q):return p.document_id==q.document_id and p.unit_index==q.unit_index and max(p.start,q.start)<min(p.end,q.end) and (p.quote in q.quote or q.quote in p.quote)
    require((overlap(a,x) and overlap(b,y)) or (overlap(a,y) and overlap(b,x)),'ai_origin_pair')
    settings=Settings(provider=origin['provider'],model=origin['requested_model'])
    # 验证历史原文/推断关系，不恢复历史授权，不把旧Prompt哈希冒充当前Prompt。
    receipt=next((r for r in case.analysis_receipts if r.get('run_id')==origin['run_id']),None)
    require(receipt is not None,'ai_origin_receipt_missing')
    require(all(origin[k]==receipt.get(k) for k in ('batch_sha256','prompt_sha256','prompt_version','provider','requested_model','provider_model')),'ai_origin_receipt_mismatch')
    selected=receipt.get('document_snapshots',[])
    require(bool(selected),'ai_origin_receipt_missing')
    batch=prepare_case(store,cid,[s['document_id'] for s in selected],settings)
    raw={'schema_version':SCHEMA_VERSION,'prompt_version':PROMPT_VERSION,'case_id':cid,'batch_sha256':batch['batch_sha256'],
         'facts':[],'timeline':[],'pending_evidence':[],'relations':[{'left':{k:origin['left'][k] for k in ('source_id','quote')},
          'right':{k:origin['right'][k] for k in ('source_id','quote')},'relation_type':origin['relation_type'],'reasoning':origin['reasoning']}]}
    validate_case_output(store,cid,batch,raw)


def stage_case(payload,originals):
    fields=set(CaseBundle.model_fields)
    require(fields-{'analysis_receipts'}<=set(payload)<=fields,'incomplete_case_structure')
    require(payload.get('schema_version') in ('1.1','1.2'),'case_version_unsupported')
    require(isinstance(payload.get('documents'),dict) and len(payload['documents'])<=MAX_DOCUMENTS,'document_count_limit')
    require(set(originals)==set(payload['documents']),'missing_or_extra_original')
    require(CASE_ID.fullmatch(payload.get('case_id','')) is not None,'case_id_format')
    temp=CaseStore();cid=payload['case_id'];temp._cases[cid]=CaseBundle(case_id=cid,title=payload['title'])
    hydrated=deepcopy(payload)
    for did,saved in payload['documents'].items():
        require(HASH.fullmatch(did) is not None and saved.get('document_id')==did,'document_identity')
        require('original_bytes' not in saved,'embedded_original_bytes_forbidden')
        check_original(saved['file_name'],originals[did])
        require(saved['file_sha256']==sha(originals[did]) and saved['parser_version']==PARSER_VERSION,'file_hash_or_parser_version')
        fresh_id=temp.attach_document(cid,saved['file_name'],originals[did]);doc=temp._case(cid).documents[fresh_id]
        require(doc.parse_report['status'] in ('parsed','partial'),'document_parse_not_restorable')
        require(fresh_id==did and json.dumps(doc.model_dump(),sort_keys=True,ensure_ascii=False)==json.dumps(saved,sort_keys=True,ensure_ascii=False),'document_reparse_mismatch')
        hydrated['documents'][did]['original_bytes']=originals[did]
    case=CaseBundle.model_validate(hydrated,strict=True);temp._cases[cid]=case
    validate_graph(temp,cid);return temp


def validate_analysis_attachment(temp,cid,analysis):
    from multidoc_ai import import_case_analysis
    from copy import deepcopy
    require(analysis.get('case_id')==cid and isinstance(analysis.get('receipt'),dict),'analysis_case_mismatch')
    # 仅白名单结构化分析，绝不导出任意会话字典或认证状态。
    allowed={'schema_version','prompt_version','case_id','batch_sha256','selected_documents','documents','source_manifest','raw_output','per_document','facts','timeline','pending_evidence','relations','completeness_diagnostics','cross_document_diagnostics','verification','semantic_status','candidate_selection','pending_selection','receipt'}
    require(set(analysis)<=allowed,'analysis_extra_fields')
    receipt=analysis['receipt'];require(set(receipt)<=RECEIPT_KEYS and receipt.get('evidence_status')=='passed' and receipt.get('format_status')=='passed','analysis_not_validated')
    require(receipt.get('case_id')==cid and receipt.get('batch_sha256')==analysis.get('batch_sha256'),'analysis_receipt_binding')
    require({d['document_id'] for d in receipt.get('document_snapshots',[])}==set(analysis.get('selected_documents',[])),'analysis_receipt_scope')
    validate_receipts(CaseBundle(case_id=cid,title=temp._case(cid).title,documents=temp._case(cid).documents,analysis_receipts=[receipt]),require_pending_statements=False)
    safe_tree(analysis)
    clone=CaseStore();clone._cases[cid]=temp.get_case(cid)
    import_case_analysis(clone,cid,deepcopy(analysis))  # 验证后的副本变化丢弃，不自动归档附件。


def _export(store,cid,analysis):
    payload=load_json(store.export_json(cid).encode());case=store.get_case(cid)
    originals={did:doc.original_bytes for did,doc in case.documents.items()}
    temp=stage_case(payload,originals)
    if analysis is not None:validate_analysis_attachment(temp,cid,analysis)
    members={'case.json':encoded(payload)};documents=[]
    for did,doc in case.documents.items():
        path='files/'+did+PurePosixPath(doc.file_name).suffix.lower();members[path]=doc.original_bytes
        documents.append({'document_id':did,'path':path})
    if analysis is not None:members['analysis.json']=encoded(analysis)
    manifest={'format_version':FORMAT_VERSION,'case_id':cid,'parser_version':PARSER_VERSION,'documents':documents,
              'analysis_included':analysis is not None,'members':[{'path':n,'size':len(b),'sha256':sha(b)} for n,b in members.items()]}
    members['manifest.json']=encoded(manifest)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in members.items():z.writestr(name,data)
    result=out.getvalue();zip_members(result);return result


def export_workspace(store,cid,*,analysis=None):
    try:return _export(store,cid,analysis)
    except WorkspaceError:raise
    except Exception:raise WorkspaceError('case_validation_failed') from None


def _restore(store,data):
    members=zip_members(data);require('manifest.json' in members and 'case.json' in members,'missing_manifest_or_case')
    manifest=load_json(members['manifest.json'],256*1024)
    require(set(manifest)=={'format_version','case_id','parser_version','documents','analysis_included','members'},'manifest_fields')
    require(manifest['format_version']==FORMAT_VERSION and manifest['parser_version']==PARSER_VERSION,'workspace_version_unsupported')
    require(type(manifest['analysis_included']) is bool,'manifest_analysis_flag')
    require(isinstance(manifest['members'],list) and isinstance(manifest['documents'],list),'manifest_structure')
    expected={}
    for row in manifest['members']:
        require(set(row)=={'path','size','sha256'} and type(row['size']) is int and HASH.fullmatch(row['sha256']) is not None,'manifest_member')
        require(row['path'] not in expected and row['path']!='manifest.json','manifest_duplicate_member');expected[row['path']]=row
    require(set(members)==set(expected)|{'manifest.json'},'missing_or_extra_zip_member')
    for name,row in expected.items():require(row['size']==len(members[name]) and row['sha256']==sha(members[name]),'member_hash_or_size')
    payload=load_json(members['case.json']);require(payload['case_id']==manifest['case_id'],'manifest_case_mismatch')
    require(payload['case_id'] not in store.list_cases(),'case_id_conflict')
    originals={};paths=[]
    for row in manifest['documents']:
        require(set(row)=={'document_id','path'} and HASH.fullmatch(row['document_id']) is not None,'manifest_document')
        did=row['document_id'];require(did not in originals and row['path'] in members,'manifest_document_duplicate_or_missing')
        require(row['path'] in ('files/'+did+'.pdf','files/'+did+'.docx'),'manifest_document_path')
        originals[did]=members[row['path']];paths.append(row['path'])
    require(set(expected)=={'case.json'}|set(paths)|({'analysis.json'} if manifest['analysis_included'] else set()),'manifest_layout')
    for did in originals:require(row_suffix(payload,did)==PurePosixPath(next(r['path'] for r in manifest['documents'] if r['document_id']==did)).suffix,'document_extension_mismatch')
    temp=stage_case(payload,originals);analysis=load_json(members['analysis.json']) if manifest['analysis_included'] else None
    if analysis is not None:validate_analysis_attachment(temp,payload['case_id'],analysis)
    # 所有操作都在临时store。最后一次冲突检查后只写入这一个案件。
    cid=payload['case_id']
    with _COMMIT_LOCK:
        require(cid not in store.list_cases(),'case_id_conflict')
        store._cases[cid]=temp.get_case(cid)
    return {'case_id':cid,'analysis':analysis,'history_trust':'imported_unverified_identity'}


def row_suffix(payload,did):return PurePosixPath(payload['documents'][did]['file_name']).suffix.lower()


def restore_workspace(store,data):
    try:return _restore(store,data)
    except WorkspaceError:raise
    except Exception:raise WorkspaceError('workspace_validation_failed') from None


def restore_legacy(store,json_bytes,original_files):
    """仅接受当前可精确重解析的1.1/1.2 JSON+按原始安全文件名匹配的完整原件集合。"""
    try:
        require(isinstance(original_files,dict),'legacy_files_required')
        payload=load_json(json_bytes);docs=payload.get('documents',{})
        names=[d['file_name'] for d in docs.values()];require(len(names)==len(set(names)),'legacy_duplicate_filename')
        require(set(names)==set(original_files),'legacy_missing_or_extra_file')
        require(sum(len(b) for b in original_files.values())<=MAX_EXPANDED_BYTES,'legacy_total_size_limit')
        require(payload['case_id'] not in store.list_cases(),'case_id_conflict')
        temp=stage_case(payload,{did:original_files[d['file_name']] for did,d in docs.items()})
        cid=payload['case_id']
        with _COMMIT_LOCK:
            require(cid not in store.list_cases(),'case_id_conflict')
            store._cases[cid]=temp.get_case(cid)
        return {'case_id':cid,'analysis':None,'history_trust':'imported_unverified_identity'}
    except WorkspaceError:raise
    except Exception:raise WorkspaceError('legacy_validation_failed') from None
