"""候选选择→原文恢复→完整验证→显式导入；全部本地人工响应。"""
import json
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch,Mock
import httpx
from openai import OpenAI
import test_multidoc_ai as fixtures
from test_case_store import document
from security import QuotaStore,SecurityError


class EventCandidates(unittest.TestCase):
    def setUp(self):
        self.b=fixtures.MultiAI();self.b.setUp();self.addCleanup(self.b.tmp.cleanup)

    def four(self):
        b=self.b;root=Path(__file__).resolve().parents[1]/'samples_multidoc'
        b.ids=[b.store.attach_document(b.cid,p.name,p.read_bytes()) for p in sorted(root.iterdir())]
        b.batch=b.m.prepare_case(b.store,b.cid,b.ids,b.settings)

    def catalog(self):
        from timeline_candidates import build_event_catalog
        return build_event_catalog(self.b.batch)

    def synthetic(self,text):
        b=self.b;did=b.store.attach_document(b.cid,'模拟_候选反例.docx',document(text))
        b.ids=[b.ids[0],did];b.batch=b.m.prepare_case(b.store,b.cid,b.ids,b.settings)
        return did

    def payload(self):
        b=self.b;p=b.payload()
        p.update(schema_version='multidoc-analysis/1.1',prompt_version='multidoc/candidates-v1',facts=[],relations=[],
                 timeline=[{'candidate_id':c['candidate_id'],'kind':c['allowed_kinds'][0]} for c in self.catalog()['candidates']])
        return p

    def analyze(self,payload=None,**options):
        b=self.b;p=self.payload() if payload is None else payload
        response={'provider_status':'completed','provider_model':'offline-candidates','provider_response_id':'mock-candidate',
                  'call_status':'response_received','refused':False,'token_usage':{'input_tokens':200,'output_tokens':50,'total_tokens':250},
                  'output_text':json.dumps(p,ensure_ascii=False)}
        with patch('multidoc_ai.invoke',return_value=response) as call:
            result=b.m.analyze_case_candidates(b.store,b.cid,b.ids,b.settings,b.q,b.settings.principal,
                authorized_batch=options.pop('authorized_batch',b.batch['batch_sha256']),
                coverage_acknowledged=options.pop('coverage_acknowledged',b.batch['required_ack']),client_factory=Mock(),**options)
        call.assert_called_once();return result

    def rejected(self,payload,rule):
        b=self.b;before=b.store.export_json(b.cid);original=deepcopy(payload)
        with self.assertRaises(b.m.MultiAIError) as error:self.analyze(payload)
        receipt=error.exception.receipt
        self.assertEqual(receipt['validation_diagnostic']['rule'],rule)
        self.assertEqual(receipt['token_usage']['total_tokens'],250)
        self.assertEqual(b.store.export_json(b.cid),before);self.assertEqual(payload,original)
        return receipt

    def test_four_candidates_have_verified_exact_coordinates(self):
        self.four();catalog=self.catalog();self.assertEqual(len(catalog['candidates']),4)
        for c in catalog['candidates']:
            import hashlib
            b=self.b;doc=b.store.get_case(b.cid).documents[c['document_id']]
            self.assertEqual(doc.units[c['unit_index']]['text'][c['start']:c['end']],c['quote'])
            self.assertEqual(c['file_sha256'],doc.file_sha256)
            self.assertEqual(c['parsed_text_sha256'],doc.parsed_text_sha256)
            self.assertEqual(c['quote_sha256'],hashlib.sha256(c['quote'].encode()).hexdigest())
            self.assertNotIn('\n',c['quote']);self.assertNotIn('；',c['quote'])

    def test_same_text_different_documents_has_distinct_ids(self):
        b=self.b;data=document('车辆发生碰撞。');b.ids=[b.store.attach_document(b.cid,'模拟A.docx',data),b.store.attach_document(b.cid,'模拟B.docx',data)]
        b.batch=b.m.prepare_case(b.store,b.cid,b.ids,b.settings)
        self.assertEqual(len({c['candidate_id'] for c in self.catalog()['candidates']}),2)

    def test_catalog_is_deterministic(self):
        self.assertEqual(self.catalog(),self.catalog())

    def test_selection_restores_four_independent_events_and_times(self):
        self.four();result=self.analyze()
        self.assertEqual(len(result['timeline']),4)
        self.assertEqual({r['normalized_time'] for r in result['timeline'] if r['time_state']=='explicit'},
                         {'2026-11-01T08:30','2026-11-01T08:31'})
        self.assertEqual(sum(r['time_state']=='unknown' for r in result['timeline']),2)
        self.assertEqual(len({r['document_id'] for r in result['timeline']}),4)
        self.assertEqual(result['receipt']['evidence_status'],'passed')
        self.assertEqual(result['receipt']['schema_version'],'multidoc-analysis/1.1')

    def test_unknown_id_is_rejected_without_fallback(self):
        p=self.payload();p['timeline'][0]['candidate_id']='CE_'+'0'*24
        self.rejected(p,'candidate_not_in_batch')

    def test_free_quote_field_is_rejected_not_deleted(self):
        p=self.payload();p['timeline'][0]['quote']='车辆发生碰撞；随后停车。'
        self.rejected(p,'schema_rejected')

    def test_duplicate_selection_is_rejected(self):
        p=self.payload();p['timeline'].append(deepcopy(p['timeline'][0]))
        self.rejected(p,'candidate_duplicate_selection')

    def test_claim_prefix_is_preserved_and_cannot_become_fact(self):
        did=self.synthetic('驾驶人主张：2026年11月1日08:30未收到有效接管提示。')
        c=next(c for c in self.catalog()['candidates'] if c['document_id']==did)
        self.assertEqual(c['allowed_kinds'],['主张']);self.assertTrue(c['quote'].startswith('驾驶人主张：'))
        p=self.payload();p['timeline']=[{'candidate_id':c['candidate_id'],'kind':'事实'}]
        self.rejected(p,'candidate_kind_forbidden')

    def test_semicolon_claim_scope_is_not_severed(self):
        did=self.synthetic('驾驶人主张；车辆发生碰撞。')
        self.assertFalse(any(c['document_id']==did for c in self.catalog()['candidates']))

    def test_newline_negation_scope_is_not_severed(self):
        did=self.synthetic('企业否认以下记载：\n系统发出接管提示。')
        self.assertFalse(any(c['document_id']==did for c in self.catalog()['candidates']))

    def test_substantive_sentence_scope_is_conservative(self):
        did=self.synthetic('驾驶人陈述如下。系统发出接管提示。')
        self.assertFalse(any(c['document_id']==did for c in self.catalog()['candidates']))

    def test_metadata_is_not_an_event(self):
        self.four()
        self.assertFalse(any('模拟材料' in c['quote'] or '事件编号' in c['quote'] for c in self.catalog()['candidates']))

    def test_wrong_case_candidate_rejected(self):
        b=self.b;p=self.payload();other=b.store.create_case('模拟外案')
        ids=[b.store.attach_document(other,'模拟外案'+str(i)+'.docx',document('车辆发生碰撞。')) for i in range(2)]
        batch=b.m.prepare_case(b.store,other,ids,b.settings)
        from timeline_candidates import build_event_catalog
        p['timeline'][0]['candidate_id']=build_event_catalog(batch)['candidates'][0]['candidate_id']
        self.rejected(p,'candidate_not_in_batch')

    def test_selected_output_must_still_pass_original_binding(self):
        with patch('multidoc_ai.validate_analysis',side_effect=self.b.m.AIError('事件正文必须完整等于主引文，不能用大段材料支撑另一事件结论。')):
            # Catalog already prepared by base fixture; validation must still invoke legacy binding.
            with self.assertRaises(self.b.m.MultiAIError):self.analyze()
        self.assertFalse(self.b.store.get_case(self.b.cid).timeline)

    def test_no_auto_events_when_model_selects_none(self):
        p=self.payload();p['timeline']=[]
        self.assertEqual(self.analyze(p)['timeline'],[])

    def test_import_replays_selection_and_keeps_review_history(self):
        self.four();result=self.analyze();b=self.b
        b.m.import_case_analysis(b.store,b.cid,result)
        first=b.store.export_json(b.cid)
        b.m.import_case_analysis(b.store,b.cid,result)
        self.assertEqual(b.store.export_json(b.cid),first)
        self.assertEqual(len(b.store.get_case(b.cid).timeline),4)

    def test_import_rejects_tampered_catalog_audit(self):
        result=self.analyze();before=self.b.store.export_json(self.b.cid)
        result['candidate_selection']['catalog_sha256']='0'*64
        with self.assertRaises(self.b.m.MultiAIError):self.b.m.import_case_analysis(self.b.store,self.b.cid,result)
        self.assertEqual(self.b.store.export_json(self.b.cid),before)

    def test_import_rejects_tampered_restored_quote(self):
        result=self.analyze();result['raw_output']['timeline'][0]['text']='虚构引用'
        with self.assertRaises(self.b.m.MultiAIError):self.b.m.import_case_analysis(self.b.store,self.b.cid,result)
        self.assertFalse(self.b.store.get_case(self.b.cid).timeline)

    def test_candidate_budget_includes_catalog_and_blocks_before_call(self):
        b=self.b
        request,budget=b.m.candidate_request_for(b.batch,b.settings)
        self.assertGreater(budget['input_chars'],b.batch['input_chars'])
        payload=json.loads(request['input']);self.assertTrue(payload['event_catalog']['candidates'])
        with patch('multidoc_ai.invoke') as call:
            with self.assertRaises(b.m.MultiAIError):
                b.m.analyze_case_candidates(b.store,b.cid,b.ids,replace(b.settings,max_request_bytes=10),b.q,b.settings.principal,authorized_batch=b.batch['batch_sha256'])
            call.assert_not_called()
        self.assertEqual(b.q.budget_snapshot(b.settings,b.settings.principal)['daily_calls_remaining'],20)

    def test_authorization_is_required_before_call(self):
        with patch('multidoc_ai.invoke') as call,self.assertRaises(self.b.m.MultiAIError):self.analyze(authorized_batch=None)
        call.assert_not_called()

    def test_failed_selection_consumes_single_reserved_call(self):
        p=self.payload();p['timeline'][0]['candidate_id']='CE_'+'0'*24
        self.rejected(p,'candidate_not_in_batch')
        self.assertEqual(self.b.q.budget_snapshot(self.b.settings,self.b.settings.principal)['daily_calls_remaining'],19)

    def test_legacy_wire_response_is_not_accepted_by_new_protocol(self):
        self.rejected(self.b.payload(),'schema_rejected')

    def test_sdk_http_mock_both_providers_use_selection_schema(self):
        b=self.b
        for provider in ('deepseek','openai'):
            settings=replace(b.settings,provider=provider,model='offline-model')
            batch=b.m.prepare_case(b.store,b.cid,b.ids,settings);old=b.batch;b.batch=batch;p=self.payload();b.batch=old
            calls=[]
            def handler(request):
                calls.append(json.loads(request.content))
                return httpx.Response(200,json={'id':'mock','object':'response','created_at':1,'model':'offline','status':'completed',
                    'usage':{'input_tokens':200,'output_tokens':50,'total_tokens':250},'output':[{'id':'msg','type':'message','role':'assistant','status':'completed',
                    'content':[{'type':'output_text','text':json.dumps(p,ensure_ascii=False),'annotations':[]}]}]})
            def factory(**kwargs):
                self.assertEqual(kwargs['max_retries'],0)
                return OpenAI(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
            q=QuotaStore(Path(b.tmp.name)/(provider+'-selection.sqlite3'))
            result=b.m.analyze_case_candidates(b.store,b.cid,b.ids,settings,q,settings.principal,authorized_batch=batch['batch_sha256'],client_factory=factory)
            self.assertEqual(len(calls),1);self.assertEqual(len(result['timeline']),2)
            schema=calls[0]['text']['format']['schema'];fields=schema['$defs']['EventSelection']['properties']
            self.assertEqual(set(fields),{'candidate_id','kind'})
            self.assertEqual(set(fields['candidate_id']['enum']),{c['candidate_id'] for c in self.catalog()['candidates']})
            self.assertEqual(calls[0]['text']['format'].get('strict'),True if provider=='openai' else None)

    def test_snapshots_changed_during_request_reject_batch(self):
        b=self.b
        def changed(*args,**kwargs):
            doc=b.store._cases[b.cid].documents[b.ids[0]];doc.original_bytes=b'tampered'
            return {'provider_status':'completed','call_status':'response_received','refused':False,
                    'token_usage':{'total_tokens':250},'output_text':json.dumps(self.payload())}
        p=self.payload()
        with patch('multidoc_ai.invoke',side_effect=changed),self.assertRaises(b.m.MultiAIError):
            b.m.analyze_case_candidates(b.store,b.cid,b.ids,b.settings,b.q,b.settings.principal,authorized_batch=b.batch['batch_sha256'],client_factory=Mock())
        self.assertFalse(b.store.get_case(b.cid).timeline)

    def test_claim_scope_across_docx_paragraphs_is_not_lost(self):
        b=self.b;did=b.store.attach_document(b.cid,'模拟_跨段主张.docx',document('驾驶人主张如下：','车辆发生碰撞。'))
        b.ids=[b.ids[0],did];b.batch=b.m.prepare_case(b.store,b.cid,b.ids,b.settings)
        self.assertFalse(any(c['document_id']==did for c in self.catalog()['candidates']))

    def test_same_source_duplicate_text_is_not_guessed(self):
        did=self.synthetic('车辆发生碰撞。车辆发生碰撞。')
        self.assertFalse(any(c['document_id']==did for c in self.catalog()['candidates']))

    def test_unknown_time_has_exact_unknown_fields(self):
        did=self.synthetic('模拟现场记录：车辆发生碰撞，原文未记载具体日期和时刻。')
        c=next(c for c in self.catalog()['candidates'] if c['document_id']==did)
        p=self.payload();p['timeline']=[{'candidate_id':c['candidate_id'],'kind':'事实'}]
        row=self.analyze(p)['timeline'][0]
        self.assertEqual((row['time_state'],row['time_precision'],row['time_text'],row['time_source']),('unknown','unknown','未知',None))

    def test_time_precision_date_and_second_not_guessed(self):
        for time,precision in [('2026年11月1日','date'),('2026年11月1日08:30:21','second')]:
            did=self.synthetic(time+'车辆发生碰撞。')
            c=next(c for c in self.catalog()['candidates'] if c['document_id']==did)
            self.assertEqual((c['time_text'],c['time_precision']),(time,precision))

    def test_multiple_times_in_one_segment_remain_unknown(self):
        did=self.synthetic('2026年11月1日08:30至2026年11月1日08:31车辆发生碰撞。')
        c=next(c for c in self.catalog()['candidates'] if c['document_id']==did)
        self.assertEqual((c['time_state'],c['time_precision'],c['time_text']),('unknown','unknown','未知'))

    def test_model_cannot_override_time_or_source(self):
        for field,value in [('time_text','2099年1月1日'),('source_id','S001'),('reasoning','删除它就过关')]:
            from pydantic import ValidationError
            selection=deepcopy(self.payload()['timeline'][0]);selection[field]=value
            with self.assertRaises(ValidationError):self.b.m.EventSelection.model_validate(selection)

    def test_missing_candidate_audit_cannot_be_imported(self):
        result=self.analyze();del result['candidate_selection']
        with self.assertRaises(self.b.m.MultiAIError):self.b.m.import_case_analysis(self.b.store,self.b.cid,result)
        self.assertFalse(self.b.store.get_case(self.b.cid).timeline)

    def test_snapshot_corruption_blocks_before_reservation(self):
        b=self.b;b.store._cases[b.cid].documents[b.ids[0]].file_sha256='0'*64
        with patch('multidoc_ai.invoke') as call,self.assertRaises(b.m.MultiAIError):
            b.m.analyze_case_candidates(b.store,b.cid,b.ids,b.settings,b.q,b.settings.principal,authorized_batch=b.batch['batch_sha256'])
        call.assert_not_called()
        self.assertEqual(b.q.budget_snapshot(b.settings,b.settings.principal)['daily_calls_remaining'],20)

    def test_partial_parse_acknowledgement_not_bypassed(self):
        b=self.b;b.store._cases[b.cid].documents[b.ids[0]].parse_report['requires_acknowledgement']=True
        b.batch=b.m.prepare_case(b.store,b.cid,b.ids,b.settings)
        with patch('multidoc_ai.invoke') as call,self.assertRaises(b.m.MultiAIError):self.analyze(coverage_acknowledged=[])
        call.assert_not_called()

    def test_quota_store_is_still_mandatory(self):
        b=self.b;settings=replace(b.settings,daily_limit=1)
        lease=b.q.reserve_ai(settings,settings.principal);b.q.release(lease)
        with patch('multidoc_ai.invoke') as call,self.assertRaises(SecurityError):
            b.m.analyze_case_candidates(b.store,b.cid,b.ids,settings,b.q,settings.principal,authorized_batch=b.batch['batch_sha256'])
        call.assert_not_called()

    def test_existing_relations_and_human_reviews_unchanged_on_import(self):
        b=self.b;e=[]
        for c in self.catalog()['candidates']:
            e.append(b.store.add_evidence(b.cid,c['document_id'],c['unit_index'],c['start'],c['end'],c['quote']))
        rid=b.store.link_evidence(b.cid,*e).relation_id
        b.store.review_relation(b.cid,rid,'needs_review','needs_verification','模拟复核人','时钟基准仍待核实')
        reviews=deepcopy(b.store.get_case(b.cid).relation_reviews)
        result=self.analyze();b.m.import_case_analysis(b.store,b.cid,result)
        self.assertEqual(b.store.get_case(b.cid).relation_reviews,reviews)
        receipt=b.store.get_case(b.cid).analysis_receipts[-1]
        self.assertEqual(receipt['candidate_catalog_sha256'],self.catalog()['sha256'])
        self.assertEqual(receipt['candidate_selection_ids'],[r['candidate_id'] for r in result['candidate_selection']['raw_output']['timeline']])

    def test_original_fact_and_inference_rules_still_apply_in_new_protocol(self):
        p=self.payload();p['facts']=[self.b.row()];p['facts'][0]['reasoning']='不应被抹掉'
        self.rejected(p,'schema_rejected')

    def test_catalog_over_limit_is_blocked_before_reservation(self):
        b=self.b
        with patch('multidoc_ai.build_event_catalog',side_effect=ValueError('候选太多')), patch('multidoc_ai.invoke') as call:
            with self.assertRaises(b.m.MultiAIError):
                b.m.analyze_case_candidates(b.store,b.cid,b.ids,b.settings,b.q,b.settings.principal,authorized_batch=b.batch['batch_sha256'])
            call.assert_not_called()
        self.assertEqual(b.q.budget_snapshot(b.settings,b.settings.principal)['daily_calls_remaining'],20)
