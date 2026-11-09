"""四份原有虚构材料和人工反例，纯规则，无模型调用。"""
import hashlib
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from case_store import CaseStore
from test_case_store import document

ROOT=Path(__file__).resolve().parents[1]

class ConflictReview(unittest.TestCase):
    def setUp(self):
        import conflict_review as c
        self.c=c;self.store=CaseStore();self.cid=self.store.create_case('模拟冲突审查')
        self.anchors={}
        for path in sorted((ROOT/'samples_multidoc').iterdir()):
            did=self.store.attach_document(self.cid,path.name,path.read_bytes());doc=self.store.get_case(self.cid).documents[did]
            for i,unit in enumerate(doc.units):
                line=next((line for line in unit['text'].splitlines(keepends=True) if '事件编号：' in line),None)
                if line:
                    start=unit['text'].index(line);eid=self.store.add_evidence(self.cid,did,i,start,start+len(line),line)
                    self.store.record_statement(self.cid,line,'party_claim' if any(s in path.name for s in ('驾驶人','企业')) else 'documented_fact',[eid])
                    self.anchors[path.name]=eid
        self.store.discover_relations(self.cid)

    def pair(self,a='模拟_现场记录.pdf',b='模拟_电子数据摘要.pdf'):
        return self.c.review_pair(self.store,self.cid,self.anchors[a],self.anchors[b])

    def synthetic(self,a,b):
        ids=[]
        for i,text in enumerate((a,b)):
            did=self.store.attach_document(self.cid,'模拟反例'+str(i)+'.docx',document(text,title=str(i)))
            ids.append(self.store.add_evidence(self.cid,did,0,0,len(text),text))
        return ids

    def test_fixed_time_difference_is_literal_only(self):
        row=self.pair();self.assertEqual(row['time']['literal_delta_seconds'],60)
        self.assertFalse(row['time']['reliable_comparison']);self.assertIsNone(row['time']['actual_delta_seconds'])
        self.assertIsNone(row['time']['selected_time'])
        self.assertEqual(row['left']['time']['precision'],'minute');self.assertEqual(row['right']['time']['precision'],'minute')

    def test_emit_and_receive_are_distinct_not_contradictory(self):
        row=self.pair('模拟_企业说明.docx','模拟_驾驶人陈述.docx')
        self.assertEqual(row['assessment_type'],'related');self.assertEqual(row['predicate']['rule'],'different_behavior_stages')
        self.assertEqual({row['left']['predicate']['stage'],row['right']['predicate']['stage']},{'system_emit','driver_receive'})

    def test_same_event_closed_opposite_predicate_is_candidate(self):
        ids=self.synthetic('事件编号：SIM-X；系统已发出接管提示。','事件编号：SIM-X；系统未发出接管提示。')
        row=self.c.review_pair(self.store,self.cid,*ids)
        self.assertEqual(row['assessment_type'],'inconsistency_candidate')
        self.assertEqual(row['predicate']['rule'],'same_proposition_opposite_polarity')
        self.assertEqual(row['verification'],'待人工核验')

    def test_four_behavior_stages_are_separate(self):
        statements=['系统已发出接管提示。','车辆已输出接管提示。','驾驶人已收到接管提示。','驾驶人已感知接管提示。']
        for a,b in zip(statements,statements[1:]):
            ids=self.synthetic('事件编号：SIM-X；'+a,'事件编号：SIM-X；'+b)
            self.assertEqual(self.c.review_pair(self.store,self.cid,*ids)['assessment_type'],'related')

    def test_date_missing_precision_mismatch_event_unknown_block_delta(self):
        for a,b in [('事件编号：SIM-X；08:30车辆发生碰撞。','事件编号：SIM-X；08:31车辆发生碰撞。'),
                    ('事件编号：SIM-X；2026年11月1日车辆发生碰撞。','事件编号：SIM-X；2026年11月1日08:31车辆发生碰撞。'),
                    ('2026年11月1日08:30车辆发生碰撞。','2026年11月1日08:31车辆发生碰撞。')]:
            ids=self.synthetic(a,b);row=self.c.review_pair(self.store,self.cid,*ids)
            self.assertIsNone(row['time']['literal_delta_seconds']);self.assertFalse(row['time']['reliable_comparison'])

    def test_multiple_times_timezone_or_clock_doubt_block_delta(self):
        for extra in ['时区未知。','时钟基准尚未确认。','北京时间。','另记2026年11月1日08:32。']:
            ids=self.synthetic('事件编号：SIM-X；2026年11月1日08:30车辆发生碰撞。'+extra,'事件编号：SIM-X；2026年11月1日08:31车辆发生碰撞。')
            self.assertIsNone(self.c.review_pair(self.store,self.cid,*ids)['time']['literal_delta_seconds'])

    def test_different_event_identifiers_do_not_merge(self):
        ids=self.synthetic('事件编号：SIM-A；系统已发出接管提示。','事件编号：SIM-B；系统未发出接管提示。')
        row=self.c.review_pair(self.store,self.cid,*ids)
        self.assertIsNone(row['assessment_type']);self.assertEqual(row['identity']['status'],'different_event')

    def test_quote_complex_negation_unsupported_wording_stays_unverified(self):
        for text in ['“系统已发出接管提示”。','系统并非未发出接管提示。','系统可能发出接管提示。','驾驶人称系统肯定发出过提示。','系统未必没有发出接管提示。']:
            ids=self.synthetic('事件编号：SIM-X；'+text,'事件编号：SIM-X；系统未发出接管提示。')
            self.assertEqual(self.c.review_pair(self.store,self.cid,*ids)['assessment_type'],'needs_verification')

    def test_same_predicate_affirmative_is_support_candidate_only(self):
        ids=self.synthetic('事件编号：SIM-X；系统已发出接管提示。','事件编号：SIM-X；系统已发出接管提示。')
        self.assertEqual(self.c.review_pair(self.store,self.cid,*ids)['assessment_type'],'support_candidate')

    def test_full_sources_hashes_and_quotes_are_preserved(self):
        row=self.pair()
        for side in ('left','right'):
            value=row[side];span=self.store.get_case(self.cid).evidence[value['evidence_id']]
            self.assertEqual(value['quote'],span.quote);self.assertEqual(value['start'],span.start)
            self.assertEqual(value['file_sha256'],span.document_sha256)
            self.assertEqual(value['quote_sha256'],hashlib.sha256(span.quote.encode()).hexdigest())
            self.assertIn('事件编号',value['quote'])

    def test_missing_logs_is_bounded_check_suggestion(self):
        row=self.pair();gaps=row['right']['gaps'];self.assertTrue(gaps)
        self.assertEqual(gaps[0]['quote'],'原始日志未提供')
        self.assertTrue(any('当前材料' in s for s in row['suggestions']))
        self.assertTrue(all('现实中不存在' not in s or '不代表' in s for s in row['suggestions']))

    def test_invalid_quote_hash_coordinate_or_case_raises(self):
        eid=self.anchors['模拟_现场记录.pdf'];base=self.store.get_case(self.cid)
        for field,value in [('quote','伪造内容'),('start',1),('document_sha256','0'*64),('case_id','case_foreign')]:
            self.store._cases[self.cid]=base.model_copy(deep=True)
            setattr(self.store._cases[self.cid].evidence[eid],field,value)
            with self.assertRaises(self.c.ConflictReviewError):self.pair()

    def test_original_bytes_or_snapshot_tampering_rejected(self):
        base=self.store.get_case(self.cid)
        for field,value in [('original_bytes',b'fake'),('parsed_text_sha256','0'*64),('parser_version','future')]:
            self.store._cases[self.cid]=base.model_copy(deep=True)
            doc=self.store._cases[self.cid].documents[base.evidence[self.anchors['模拟_现场记录.pdf']].document_id]
            setattr(doc,field,value)
            with self.assertRaises(self.c.ConflictReviewError):self.pair()

    def test_cross_case_and_identical_file_copies_rejected(self):
        other=self.store.create_case('模拟外案')
        with self.assertRaises(self.c.ConflictReviewError):self.c.review_pair(self.store,other,*list(self.anchors.values())[:2])
        span=self.store.get_case(self.cid).evidence[self.anchors['模拟_现场记录.pdf']];doc=self.store.get_case(self.cid).documents[span.document_id]
        did=self.store.attach_document(self.cid,'模拟副本.pdf',doc.original_bytes)
        eid=self.store.add_evidence(self.cid,did,span.unit_index,span.start,span.end,span.quote)
        with self.assertRaises(self.c.ConflictReviewError):self.c.review_pair(self.store,self.cid,span.evidence_id,eid)

    def test_read_only_review_never_changes_case_or_confirms_facts(self):
        before=self.store.export_json(self.cid)
        with patch.object(self.store,'confirm_fact',side_effect=AssertionError('must not confirm')),patch('multidoc_ai.invoke',side_effect=AssertionError('no AI')):
            self.c.build_workbench(self.store,self.cid);self.pair()
        self.assertEqual(self.store.export_json(self.cid),before)

    def test_modified_rejected_re_review_history_and_workspace_roundtrip(self):
        rows=self.c.build_workbench(self.store,self.cid);rid=rows[0]['relation_id']
        for status in ('modified','rejected','needs_review'):
            self.store.review_relation(self.cid,rid,status,'needs_verification','模拟审阅员','核对原始记录与来源')
        before=self.c.build_workbench(self.store,self.cid)
        from workspace_bundle import export_workspace,restore_workspace
        target=CaseStore();restore_workspace(target,export_workspace(self.store,self.cid))
        self.assertEqual(self.c.build_workbench(target,self.cid),before)
        reviews=target.get_case(self.cid).relation_reviews
        self.assertEqual(reviews[1].previous_review_id,reviews[0].review_id)
        self.assertEqual(reviews[2].previous_review_id,reviews[1].review_id)
        self.assertEqual(target.get_case(self.cid).reviews,[])

    def test_truncated_negation_or_subject_is_not_interpreted(self):
        ids=self.synthetic('事件编号：SIM-X；驾驶人主张：系统未发出接管提示。','事件编号：SIM-X；系统已发出接管提示。')
        first=self.store.get_case(self.cid).evidence[ids[0]];quote='系统未发出接管提示。'
        doc=self.store.get_case(self.cid).documents[first.document_id];start=doc.units[0]['text'].index(quote)
        short=self.store.add_evidence(self.cid,doc.document_id,0,start,start+len(quote),quote)
        self.assertEqual(self.c.review_pair(self.store,self.cid,short,ids[1])['assessment_type'],'needs_verification')

    def test_narrow_candidate_event_uses_verified_identifier_context(self):
        from multidoc_ai import prepare_case
        from timeline_candidates import build_event_catalog
        from security import Settings
        case=self.store.get_case(self.cid);batch=prepare_case(self.store,self.cid,list(case.documents),Settings())
        choices=[c for c in build_event_catalog(batch)['candidates'] if c['time_state']=='explicit']
        eids=[self.store.add_evidence(self.cid,c['document_id'],c['unit_index'],c['start'],c['end'],c['quote']) for c in choices]
        row=self.c.review_pair(self.store,self.cid,*eids)
        self.assertEqual(abs(row['time']['literal_delta_seconds']),60)
        self.assertTrue(row['left']['event_identity_source'])

    def test_unknown_unsupported_text_does_not_invent_proposition(self):
        ids=self.synthetic('事件编号：SIM-X；接管提示相关维修材料目录。','事件编号：SIM-X；驾驶人未收到接管提示。')
        self.assertEqual(self.c.review_pair(self.store,self.cid,*ids)['assessment_type'],'needs_verification')

    def test_pdf_generic_table_warning_remains_visible(self):
        row=self.pair()
        self.assertFalse(row['left']['parse_complete'])
        self.assertIn('pdf_table_coverage_unverified',row['left']['parse_issue_codes'])
        self.assertTrue(row['left']['text_comparison_eligible'])
        self.assertFalse(row['time']['reliable_comparison'])

    def test_other_parse_gaps_block_arithmetic(self):
        eid=self.anchors['模拟_现场记录.pdf'];span=self.store.get_case(self.cid).evidence[eid]
        report=self.store._cases[self.cid].documents[span.document_id].parse_report
        report['issues'].append({'code':'page_text_failed','location':'PDF 第1页','coverage_id':None,'message':'模拟读取问题','severity':'warning'})
        self.assertIsNone(self.pair()['time']['literal_delta_seconds'])
        ids=self.synthetic('事件编号：SIM-X；系统已发出接管提示。','事件编号：SIM-X；系统未发出接管提示。')
        span=self.store.get_case(self.cid).evidence[ids[0]]
        report=self.store._cases[self.cid].documents[span.document_id].parse_report
        report.update(status='partial',requires_acknowledgement=True)
        report['issues'].append({'code':'tracked_change','location':'正文','coverage_id':None,'message':'模拟修订未解析','severity':'warning'})
        self.assertEqual(self.c.review_pair(self.store,self.cid,*ids)['assessment_type'],'needs_verification')
        ids=self.synthetic('事件编号：SIM-X；原始日志未提供。','事件编号：SIM-X；系统未发出接管提示。')
        span=self.store.get_case(self.cid).evidence[ids[0]]
        report=self.store._cases[self.cid].documents[span.document_id].parse_report
        report.update(status='partial',requires_acknowledgement=True)
        report['issues'].append({'code':'tracked_change','location':'正文','coverage_id':None,'message':'模拟修订未解析','severity':'warning'})
        self.assertEqual(self.c.review_pair(self.store,self.cid,*ids)['left']['gaps'],[])

    def test_date_only_comparison_never_adds_midnight(self):
        ids=self.synthetic('事件编号：SIM-X；2026年11月1日车辆发生碰撞。','事件编号：SIM-X；2026年11月2日车辆发生碰撞。')
        row=self.c.review_pair(self.store,self.cid,*ids)
        self.assertEqual(row['time']['literal_delta_days'],1);self.assertIsNone(row['time']['literal_delta_seconds'])
        self.assertNotIn('T00:00',row['left']['time']['normalized'])

    def test_same_time_is_not_a_truth_or_clock_confirmation(self):
        ids=self.synthetic('事件编号：SIM-X；2026年11月1日08:30车辆发生碰撞。','事件编号：SIM-X；现场记录：2026年11月1日08:30车辆发生碰撞。')
        row=self.c.review_pair(self.store,self.cid,*ids)
        self.assertEqual(row['time']['literal_delta_seconds'],0);self.assertFalse(row['time']['reliable_comparison'])
        self.assertEqual(row['assessment_type'],'support_candidate')

    def test_cropped_clock_or_following_uncertainty_blocks_comparison(self):
        for qualifier in ('时钟基准未确认。','上述记载尚未核实。'):
            text='事件编号：SIM-X；2026年11月1日08:30车辆发生碰撞。'+qualifier
            ids=self.synthetic(text,'事件编号：SIM-X；2026年11月1日08:31车辆发生碰撞。')
            span=self.store.get_case(self.cid).evidence[ids[0]];quote='2026年11月1日08:30车辆发生碰撞。'
            start=text.index(quote);short=self.store.add_evidence(self.cid,span.document_id,0,start,start+len(quote),quote)
            row=self.c.review_pair(self.store,self.cid,short,ids[1])
            self.assertIsNone(row['time']['literal_delta_seconds'])

    def test_subject_declaration_in_prior_paragraph_not_discarded(self):
        did=self.store.attach_document(self.cid,'模拟前置归属.docx',document('驾驶人主张如下：','事件编号：SIM-X；系统未发出接管提示。'))
        doc=self.store.get_case(self.cid).documents[did];quote=doc.units[1]['text']
        eid=self.store.add_evidence(self.cid,did,1,0,len(quote),quote)
        ids=self.synthetic('事件编号：SIM-X；系统已发出接管提示。','事件编号：SIM-X；车辆已输出接管提示。')
        row=self.c.review_pair(self.store,self.cid,eid,ids[0])
        self.assertFalse(row['left']['scope_valid']);self.assertEqual(row['assessment_type'],'needs_verification')

    def test_log_gap_is_not_borrowed_from_next_record(self):
        text='事件编号：SIM-X；2026年11月1日08:30车辆发生碰撞。\n事件编号：SIM-Y；原始日志未提供。'
        did=self.store.attach_document(self.cid,'模拟两条记录.docx',document(text));quote=text.splitlines(keepends=True)[0]
        eid=self.store.add_evidence(self.cid,did,0,0,len(quote),quote)
        ids=self.synthetic('事件编号：SIM-X；2026年11月1日08:31车辆发生碰撞。','事件编号：SIM-Y；系统已发出接管提示。')
        row=self.c.review_pair(self.store,self.cid,eid,ids[0]);self.assertEqual(row['left']['gaps'],[])

    def test_multiple_event_ids_and_unrelated_topics_are_not_merged(self):
        ids=self.synthetic('事件编号：SIM-X；事件编号：SIM-Y；系统已发出接管提示。','事件编号：SIM-X；系统未发出接管提示。')
        row=self.c.review_pair(self.store,self.cid,*ids);self.assertEqual(row['identity']['status'],'unproven')
        self.assertEqual(row['assessment_type'],'needs_verification')

    def test_review_limit_and_safe_errors_do_not_echo_original(self):
        with patch.object(self.c,'MAX_RELATIONS',1),self.assertRaises(self.c.ConflictReviewError):self.c.build_workbench(self.store,self.cid)
        eid=self.anchors['模拟_现场记录.pdf'];self.store._cases[self.cid].evidence[eid].quote='PRIVATE_QUOTE_MUST_NOT_LOG'
        with self.assertRaises(self.c.ConflictReviewError) as caught:self.pair()
        self.assertNotIn('PRIVATE_QUOTE',str(caught.exception))

    def test_latest_review_separate_from_original_candidate(self):
        row=self.c.build_workbench(self.store,self.cid)[0];rid=row['relation_id'];original=deepcopy(row['original_candidate'])
        self.store.review_relation(self.cid,rid,'modified','related','模拟甲','仅确认有关联')
        self.store.review_relation(self.cid,rid,'rejected','needs_verification','模拟乙','材料独立性仍需审查')
        current=next(r for r in self.c.build_workbench(self.store,self.cid) if r['relation_id']==rid)
        self.assertEqual(current['original_candidate'],original);self.assertEqual(current['latest_review']['status'],'rejected')
        self.assertEqual(len(current['history']),2)

    def test_review_never_replays_fact_confirmation_even_with_prior_truth_history(self):
        statement=next(s for s in self.store.get_case(self.cid).facts if '现场记录' in s.text)
        self.store.confirm_fact(self.cid,statement.statement_id,'模拟先前核验人','模拟历史真实性确认记录')
        before=self.store.export_json(self.cid)
        with patch('case_store.CaseStore.confirm_fact',side_effect=AssertionError('no fact confirmation during review')):
            self.c.build_workbench(self.store,self.cid)
        self.assertEqual(self.store.export_json(self.cid),before)

    def test_log_quotation_negation_or_claim_not_relabelled_as_missing(self):
        for text in ('否认原始日志未提供。','“原始日志未提供”。','原始日志未提供并不属实。','原始日志未提供？','驾驶人主张；原始日志未提供。'):
            ids=self.synthetic('事件编号：SIM-X；'+text,'事件编号：SIM-X；系统已发出接管提示。')
            row=self.c.review_pair(self.store,self.cid,*ids)
            self.assertEqual(row['left']['gaps'],[])
            self.assertFalse(any('材料明确记载原始日志未提供' in s for s in row['suggestions']))
