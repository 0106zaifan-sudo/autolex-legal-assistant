import hashlib
import io
import json
from copy import deepcopy
from pathlib import Path
import unittest
from docx import Document
from case_store import CaseStore, CaseError
from evidence import make_span, verify_span
from core import extract
from ai_ui import demo_analysis

ROOT=Path(__file__).resolve().parents[1]


def document(*lines,title='模拟材料'):
    doc=Document();doc.core_properties.title=title
    for line in lines:doc.add_paragraph(line)
    out=io.BytesIO();doc.save(out);return out.getvalue()


class CaseStoreTests(unittest.TestCase):
    def setUp(self):
        self.store=CaseStore();self.cid=self.store.create_case('模拟辅助驾驶初审')
        self.text='模拟维修记录：车辆发生碰撞。'
        self.data=document(self.text)
        self.did=self.store.attach_document(self.cid,'模拟材料.docx',self.data)

    def anchor(self,cid=None,did=None,text=None):
        cid=cid or self.cid;did=did or self.did;text=text or self.text
        return self.store.add_evidence(cid,did,0,0,len(text),text)

    def demo(self):
        path=ROOT/'samples_ai'/'模拟_AI事故材料.docx'
        did=self.store.attach_document(self.cid,path.name,path.read_bytes())
        return did,demo_analysis(ROOT)

    def test_initial_case_has_missing_basic_info_no_auto_confirmed_facts(self):
        case=self.store.get_case(self.cid)
        self.assertTrue(all(field.value is None and field.status=='missing' for field in case.basic_info.values()))
        self.assertFalse(case.facts);self.assertFalse(case.claims);self.assertFalse(case.timeline)
        self.assertFalse(case.reviews)

    def test_same_filename_different_files_are_not_overwritten(self):
        data=document('模拟不同材料：碰撞日期未确认。')
        other=self.store.attach_document(self.cid,'模拟材料.docx',data)
        case=self.store.get_case(self.cid)
        self.assertNotEqual(other,self.did)
        self.assertEqual(len(case.documents),2)
        self.assertEqual(self.store.get_original(self.cid,self.did),('模拟材料.docx',self.data))
        self.assertEqual(self.store.get_original(self.cid,other)[1],data)
        self.assertEqual(self.store.attach_document(self.cid,'模拟材料.docx',data),other)

    def test_cross_case_document_and_evidence_references_are_rejected(self):
        other=self.store.create_case('模拟另一案件')
        eid=self.anchor()
        with self.assertRaises(CaseError):self.store.record_statement(other,self.text,'party_claim',[eid])
        with self.assertRaises(CaseError):self.store.get_original(other,self.did)
        with self.assertRaises(CaseError):self.store.add_evidence(other,self.did,0,0,len(self.text),self.text)

    def test_shared_file_requires_explicit_assignment_and_case_scoped_anchors(self):
        other=self.store.create_case('模拟明确共享材料案件')
        self.store.attach_document(other,'模拟材料.docx',self.data)
        first=self.anchor();second=self.anchor(other,self.did)
        self.assertNotEqual(first,second)
        with self.assertRaises(CaseError):self.store.record_statement(other,self.text,'documented_fact',[first])

    def test_anchor_replays_original_file_snapshot_and_exact_text(self):
        eid=self.anchor();case=self.store.get_case(self.cid);span=case.evidence[eid];doc=case.documents[self.did]
        self.assertEqual(span.quote,doc.units[span.unit_index]['text'][span.start:span.end])
        self.assertEqual(span.document_sha256,hashlib.sha256(self.data).hexdigest())
        self.assertEqual(verify_span(self.cid,doc,span),span)
        with self.assertRaises(ValueError):verify_span('other-case',doc,span)
        altered=doc.model_copy(deep=True);altered.units[0]['text']='被修改'
        with self.assertRaises(ValueError):make_span(self.cid,altered,0,0,2,'被修')

    def test_invalid_positions_and_quotes_cannot_create_evidence(self):
        for start,end,quote in [(-1,2,'模拟'),(0,999,self.text),(0,2,'伪造'),(True,3,'模拟维')]:
            with self.subTest(start=start,end=end),self.assertRaises(CaseError):
                self.store.add_evidence(self.cid,self.did,0,start,end,quote)
        self.assertFalse(self.store.get_case(self.cid).evidence)

    def test_documented_fact_requires_explicit_human_truth_confirmation(self):
        sid=self.store.record_statement(self.cid,self.text,'documented_fact',[self.anchor()])
        case=self.store.get_case(self.cid)
        self.assertEqual(case.facts[0].kind,'documented_fact')
        self.assertEqual(case.facts[0].verification,'unverified')
        with self.assertRaises(CaseError):self.store.confirm_fact(self.cid,sid,'','')
        self.store.confirm_fact(self.cid,sid,'模拟复核人','仅对虚构情节完成模拟真实性复核，不是真实案件认定')
        case=self.store.get_case(self.cid)
        self.assertEqual(case.facts[0].kind,'confirmed_fact')
        self.assertEqual(case.facts[0].verification,'human_confirmed')
        self.assertEqual(case.reviews[0].scope,'truth_confirmation')
        self.assertTrue(case.reviews[0].reviewed_at.endswith('+08:00'))

    def test_claim_inference_cannot_be_directly_created_as_confirmed_fact(self):
        eid=self.anchor()
        for kind in ('confirmed_fact','ai_inference'):
            with self.subTest(kind=kind),self.assertRaises(CaseError):
                self.store.record_statement(self.cid,self.text,kind,[eid])
        sid=self.store.record_statement(self.cid,self.text,'party_claim',[eid])
        with self.assertRaises(CaseError):self.store.confirm_fact(self.cid,sid,'模拟人','模拟依据')

    def test_obvious_party_claim_is_not_confirmed_by_merely_switching_category(self):
        text='模拟驾驶人主张：系统没有发出提示。'
        did=self.store.attach_document(self.cid,'模拟主张.docx',document(text))
        eid=self.anchor(did=did,text=text)
        sid=self.store.record_statement(self.cid,text,'documented_fact',[eid])
        with self.assertRaises(CaseError):self.store.confirm_fact(self.cid,sid,'模拟人','模拟意见')
        self.assertEqual(self.store.get_case(self.cid).facts[0].kind,'documented_fact')

    def test_generated_statement_or_speaker_not_in_source_is_rejected(self):
        eid=self.anchor()
        with self.assertRaises(CaseError):self.store.record_statement(self.cid,'车辆损失十万元','documented_fact',[eid])
        with self.assertRaises(CaseError):self.store.record_statement(self.cid,self.text,'party_claim',[eid],speaker='虚构新人员')
        with self.assertRaises(CaseError):self.store.record_statement(self.cid,self.text,'documented_fact',[])

    def test_missing_information_is_null_scoped_and_not_invented_as_fact(self):
        self.store.record_missing(self.cid,'本文件未提取到事故完整时间，待核实',[self.did])
        case=self.store.get_case(self.cid)
        item=case.pending_items[-1]
        self.assertEqual(item.kind,'missing_information');self.assertIsNone(item.value)
        self.assertEqual(item.document_ids,[self.did]);self.assertFalse(item.evidence_ids)
        self.assertFalse(case.facts)
        with self.assertRaises(CaseError):self.store.record_missing(self.cid,'待核实',['not-in-case'])

    def test_failed_file_retains_original_report_and_coverage_pending(self):
        raw=b'SIMULATED CORRUPT PDF'
        did=self.store.attach_document(self.cid,'模拟损坏.pdf',raw)
        case=self.store.get_case(self.cid)
        self.assertEqual(case.documents[did].parse_report['status'],'failed')
        self.assertFalse(case.documents[did].units)
        self.assertEqual(self.store.get_original(self.cid,did)[1],raw)
        gaps=[p for p in case.pending_items if p.kind=='coverage_gap' and did in p.document_ids]
        self.assertTrue(gaps);self.assertTrue(gaps[0].coverage_refs)
        self.assertFalse(case.facts)

    def test_basic_candidates_from_different_documents_remain_ambiguous(self):
        for name in ('虚构甲市人民法院','虚构乙市人民法院'):
            self.store.attach_document(self.cid,'模拟法院材料.docx',document(name))
        field=self.store.get_case(self.cid).basic_info['法院']
        self.assertEqual(field.status,'ambiguous');self.assertIsNone(field.value)
        self.assertEqual(len(field.evidence_ids),2)

    def test_ai_import_keeps_fact_claim_inference_and_timeline_separate(self):
        did,result=self.demo();self.store.import_analysis(self.cid,did,result)
        case=self.store.get_case(self.cid)
        self.assertEqual(len(case.facts),1);self.assertEqual(len(case.claims),2)
        self.assertEqual(len(case.inferences),2);self.assertEqual(len(case.timeline),3)
        self.assertTrue(all(s.kind=='documented_fact' and s.verification=='unverified' for s in case.facts))
        self.assertTrue(all(s.origin=='simulation' and '非 AI 调用' in s.analysis_mode for s in case.facts+case.claims+case.inferences))
        self.assertFalse(case.reviews)
        for event in case.timeline:
            anchor=case.evidence[event.evidence_id];time=case.evidence[event.time_evidence_id]
            self.assertEqual(anchor.document_id,did);self.assertEqual(time.document_id,did)
            self.assertGreaterEqual(time.start,anchor.start);self.assertLessEqual(time.end,anchor.end)
        before=(len(case.facts),len(case.claims),len(case.inferences),len(case.timeline),len(case.pending_items))
        self.store.import_analysis(self.cid,did,result)
        case=self.store.get_case(self.cid)
        self.assertEqual(before,(len(case.facts),len(case.claims),len(case.inferences),len(case.timeline),len(case.pending_items)))

    def test_tampered_analysis_or_time_anchor_is_rejected_atomically(self):
        did,result=self.demo()
        for change in ('time','anchor','schema','sections'):
            altered=deepcopy(result)
            if change=='time':altered['sections']['timeline'][0]['time_text']='2099年1月1日'
            elif change=='anchor':altered['sections']['timeline'][0]['time_source']['start']+=1
            elif change=='schema':altered['parser_version']='core.read_units/v1'
            else:altered['sections']='invalid'
            before=self.store.export_json(self.cid)
            with self.subTest(change=change),self.assertRaises(CaseError):self.store.import_analysis(self.cid,did,altered)
            self.assertEqual(before,self.store.export_json(self.cid))

    def test_ai_result_for_other_document_cannot_be_attached_by_filename(self):
        did,result=self.demo()
        other=self.store.attach_document(self.cid,'模拟_AI事故材料.docx',document(self.text))
        with self.assertRaises(CaseError):self.store.import_analysis(self.cid,other,result)
        self.assertFalse(self.store.get_case(self.cid).facts)

    def test_same_analysis_explicitly_shared_has_distinct_case_event_ids(self):
        did,result=self.demo();self.store.import_analysis(self.cid,did,result)
        other=self.store.create_case('模拟共享同一材料的案件')
        path=ROOT/'samples_ai'/'模拟_AI事故材料.docx'
        self.store.attach_document(other,path.name,path.read_bytes());self.store.import_analysis(other,did,result)
        a=self.store.get_case(self.cid);b=self.store.get_case(other)
        self.assertNotEqual(a.timeline[0].event_id,b.timeline[0].event_id)
        self.assertEqual(a.timeline[0].source_event_id,b.timeline[0].source_event_id)
        self.assertFalse(set(a.evidence)&set(b.evidence))

    def test_export_excludes_raw_bytes_and_get_case_is_a_detached_copy(self):
        eid=self.anchor();self.store.record_statement(self.cid,self.text,'unclassified',[eid])
        case=self.store.get_case(self.cid);case.documents[self.did].units[0]['text']='篡改副本'
        self.assertEqual(self.store.get_case(self.cid).documents[self.did].units[0]['text'],self.text)
        data=json.loads(self.store.export_json(self.cid))
        self.assertNotIn('original_bytes',data['documents'][self.did])
        self.assertEqual(data['evidence'][eid]['quote'],self.text)
        self.assertFalse(data['facts'])

    def test_record_attachment_requires_matching_original_bytes(self):
        record=extract('模拟_记录.docx',self.data)
        bad=deepcopy(record);bad['original_bytes']=b'changed'
        with self.assertRaises(CaseError):self.store.attach_record(self.cid,bad)
        did=self.store.attach_record(self.cid,record)
        self.assertEqual(self.store.get_original(self.cid,did)[1],self.data)

    def test_basic_info_is_source_bound_and_never_auto_confirmed(self):
        text='模拟记录：车辆型号为测试车型甲，事故日期为2026年11月1日。'
        did=self.store.attach_document(self.cid,'模拟基本信息.docx',document(text))
        eid=self.store.add_evidence(self.cid,did,0,0,len(text),text)
        self.store.record_basic_info(self.cid,'车辆型号','测试车型甲',[eid])
        self.store.record_basic_info(self.cid,'事故日期','2026年11月1日',[eid])
        case=self.store.get_case(self.cid)
        self.assertEqual(case.basic_info['车辆型号'].value,'测试车型甲')
        self.assertEqual(case.basic_info['事故日期'].status,'unverified')
        with self.assertRaises(CaseError):self.store.record_basic_info(self.cid,'事故日期','2099年1月1日',[eid])

    def test_reimport_cannot_overwrite_human_confirmation(self):
        did,result=self.demo();self.store.import_analysis(self.cid,did,result)
        sid=self.store.get_case(self.cid).facts[0].statement_id
        self.store.confirm_fact(self.cid,sid,'模拟复核人','对模拟情节进行复核，仅作测试')
        self.store.import_analysis(self.cid,did,result)
        case=self.store.get_case(self.cid)
        self.assertEqual(case.facts[0].kind,'confirmed_fact')
        self.assertEqual(len(case.reviews),1)

    def test_unknown_event_time_becomes_pending_without_date_invention(self):
        from ai_analysis import empty_analysis,validate_analysis,build_sources
        quote='模拟记录：车辆发生碰撞，具体日期未记载。'
        did=self.store.attach_document(self.cid,'模拟未知时间.docx',document(quote))
        r=self.store.get_case(self.cid).documents[did].as_record()
        ref={'source_id':'S001','quote':quote}
        raw=empty_analysis(r)
        raw['timeline']=[{'kind':'事实','text':quote,'reasoning':'','sources':[ref],
                          'event_source':ref,'time_state':'unknown','time_text':'未知',
                          'time_precision':'unknown','time_source':None}]
        result=validate_analysis(raw,r,build_sources(r));result['mode']='离线模拟（非AI调用）'
        self.store.import_analysis(self.cid,did,result)
        case=self.store.get_case(self.cid)
        self.assertEqual(case.timeline[0].time_text,'未知')
        self.assertIsNone(case.timeline[0].time_evidence_id)
        self.assertTrue(any(p.kind=='missing_information' and did in p.document_ids for p in case.pending_items))

    def test_unclassified_excerpt_generates_review_task(self):
        self.store.record_statement(self.cid,self.text,'unclassified',[self.anchor()])
        case=self.store.get_case(self.cid)
        self.assertFalse(case.facts)
        self.assertTrue(any(p.kind=='unclassified_review' for p in case.pending_items))
