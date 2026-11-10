"""完全离线、人工选择CASE-001证据编号；不是三次真实响应的重建。"""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from case_store import CaseStore
from security import Settings
from test_case_store import document
import multidoc_ai as m

DATA = Path(__file__).resolve().parents[1]/'datasets/CASE-001/standard'
SITE = '事故时间栏目08:30来自P01口述，仅按分钟填写，未作时钟校核。'
EDR = 'EDR只提供相对触发锚点t=0的测试摘要，未提供可信绝对日期。'
BODY = '原始二进制数据及提取过程镜像未提供，摘要为二次转写。'
TITLE = '模拟材料：EDR摘要'
COMPANY = '原始二进制日志、设备镜像和完整性签名未随本说明提供。'
CLAIM = '企业主张：驾驶人已收到接管提示。'
QUESTION = '待核实推断：D01口述分钟与D04的EDR相对锚点是否有可核对的时钟基准？'


class PendingSelectionPrototype(unittest.TestCase):
    def setUp(self):
        from prototypes import pending_evidence_selection as p
        self.p = p
        self.store = CaseStore(); self.cid = self.store.create_case('完全虚构 CASE-001编号选择原型')
        self.ids = {}; self.materials = {}
        for d in json.loads((DATA/'manifest.json').read_text())['documents']:
            if d['material_id'] in ('D01','D03','D04'):
                path = DATA/d['path']; raw = path.read_bytes()
                self.materials[d['material_id']] = (path.name, raw)
                self.ids[d['material_id']] = self.store.attach_document(self.cid, path.name, raw)
        self.settings = Settings(provider='deepseek', model='deepseek-flash')
        self.prepared = p.prepare_selection(self.store, self.cid, list(self.ids.values()), self.settings)

    def entry(self, quote, did=None):
        return next(e for e in self.prepared['catalog']['entries'] if e['quote'].rstrip('\r\n') == quote
                    and (did is None or e['document_id']==self.ids[did]))

    def payload(self, quotes=(SITE,EDR), reasoning=QUESTION):
        ids = [self.entry(q)['candidate_id'] for q in quotes]
        return {'schema_version':self.p.SCHEMA_VERSION, 'prompt_version':self.p.PROMPT_VERSION,
                'case_id':self.cid,'batch_sha256':self.prepared['batch']['batch_sha256'],
                'catalog_sha256':self.prepared['catalog']['sha256'],
                'pending_evidence':[{'anchor_id':ids[0], 'evidence_ids':ids, 'reasoning':reasoning}]}

    def run_selection(self, raw):
        return self.p.validate_selection(self.store,self.cid,self.prepared,raw)

    def reject(self, raw, code):
        before = self.store.export_json(self.cid)
        with self.assertRaises(self.p.PrototypeError) as caught:self.run_selection(raw)
        self.assertEqual(caught.exception.code,code)
        self.assertEqual(self.store.export_json(self.cid),before)
        return caught.exception

    def legacy(self, quotes, text, reasoning):
        refs=[{'source_id':self.entry(q)['source_id'],'quote':self.entry(q)['quote']} for q in quotes]
        b=self.prepared['batch']
        return {'schema_version':m.SCHEMA_VERSION,'prompt_version':m.PROMPT_VERSION,
                'case_id':self.cid,'batch_sha256':b['batch_sha256'], 'facts':[], 'timeline':[], 'relations':[],
                'pending_evidence':[{'kind':'推断','text':text,'sources':refs,'reasoning':reasoning}]}

    def test_schema_removes_free_copy_fields_and_keeps_semantic_choice(self):
        properties=self.prepared['response_schema']['$defs']['PendingSelection']['properties']
        self.assertEqual(set(properties),{'anchor_id','evidence_ids','reasoning'})
        self.assertFalse(self.prepared['response_schema']['additionalProperties'])
        self.assertNotEqual(self.p.SCHEMA_VERSION,m.CANDIDATE_SCHEMA_VERSION)

    def test_catalog_is_deterministic_and_source_bound(self):
        other=self.p.prepare_selection(self.store,self.cid,list(reversed(self.ids.values())),self.settings)
        self.assertEqual(other,self.prepared)
        self.assertEqual(len({e['candidate_id'] for e in other['catalog']['entries']}),len(other['catalog']['entries']))
        for e in other['catalog']['entries']:
            doc=self.store.get_case(self.cid).documents[e['document_id']]
            self.assertEqual(e['case_id'],self.cid)
            self.assertEqual(e['quote'],doc.units[e['unit_index']]['text'][e['start']:e['end']])
            self.assertEqual(e['file_sha256'],doc.file_sha256)
            self.assertEqual(e['parsed_text_sha256'],doc.parsed_text_sha256)
            self.assertEqual(e['parser_version'],doc.parser_version)

    def test_d01_d04_restoration_keeps_both_sources_and_exact_text(self):
        raw=self.payload();before=deepcopy(raw);result=self.run_selection(raw)
        row=result['resolved_pending_evidence'][0]
        self.assertEqual(row['text'],self.entry(SITE)['quote'])
        self.assertEqual({s['document_id'] for s in row['sources']},{self.ids['D01'],self.ids['D04']})
        self.assertEqual(row['reasoning'],QUESTION)
        self.assertEqual(result['validation']['semantic_status'],'pending_human_review')
        self.assertEqual(raw,before)
        self.assertEqual(self.store.get_case(self.cid).inferences,[])

    def test_d01_d03_restores_multiple_sources_without_summary_text(self):
        result=self.run_selection(self.payload((SITE,COMPANY),'待核实推断：D01的时间来源与D03的原始日志材料是否需要分别核对？'))
        self.assertEqual(len(result['resolved_pending_evidence'][0]['sources']),2)
        self.assertEqual(result['resolved_pending_evidence'][0]['text'],self.entry(SITE)['quote'])

    def test_primary_must_be_explicit_member_not_automatically_appended(self):
        raw=self.payload();raw['pending_evidence'][0]['anchor_id']=self.entry(BODY)['candidate_id']
        self.reject(raw,'anchor_not_selected')

    def test_primary_can_be_second_selected_source(self):
        raw=self.payload();raw['pending_evidence'][0]['anchor_id']=self.entry(EDR)['candidate_id']
        result=self.run_selection(raw)
        self.assertEqual(result['resolved_pending_evidence'][0]['text'],self.entry(EDR)['quote'])
        self.assertEqual(len(result['resolved_pending_evidence'][0]['sources']),2)

    def test_unknown_identifier_is_rejected_without_search(self):
        raw=self.payload();raw['pending_evidence'][0]['evidence_ids'][1]='PE_'+'f'*24
        self.reject(raw,'candidate_not_in_catalog')

    def test_no_free_quote_text_or_kind_is_accepted(self):
        for key,value in (('quote',SITE),('text','改写摘要'),('kind','事实')):
            with self.subTest(key=key):
                raw=self.payload();raw['pending_evidence'][0][key]=value
                self.reject(raw,'selection_schema_invalid')

    def test_duplicate_evidence_identifier_is_rejected_not_dropped(self):
        raw=self.payload();raw['pending_evidence'][0]['evidence_ids'].append(raw['pending_evidence'][0]['anchor_id'])
        self.reject(raw,'duplicate_evidence_selection')

    def test_duplicate_issues_are_rejected_not_silently_deduplicated(self):
        raw=self.payload();raw['pending_evidence'].append(deepcopy(raw['pending_evidence'][0]))
        self.reject(raw,'duplicate_pending_selection')

    def test_multiple_distinct_questions_on_same_sources_are_preserved(self):
        raw=self.payload();other=deepcopy(raw['pending_evidence'][0])
        other['reasoning']='待核实推断：口述时间与相对触发锚点的来源独立性是否需要核查？'
        raw['pending_evidence'].append(other)
        self.assertEqual(len(self.run_selection(raw)['resolved_pending_evidence']),2)

    def test_missing_source_list_is_not_inferred_from_reasoning(self):
        raw=self.payload();raw['pending_evidence'][0]['evidence_ids']=[]
        self.reject(raw,'selection_schema_invalid')

    def test_more_than_four_sources_is_not_truncated(self):
        raw=self.payload();raw['pending_evidence'][0]['evidence_ids']=[e['candidate_id'] for e in self.prepared['catalog']['entries'][:5]]
        self.reject(raw,'selection_schema_invalid')

    def test_tampered_quote_in_prepared_catalog_is_not_trusted(self):
        self.prepared['catalog']['entries'][0]['quote']='伪造文本'
        self.reject(self.payload(),'prepared_context_changed')

    def test_tampered_coordinates_are_not_trusted(self):
        raw=self.payload();self.prepared['catalog']['entries'][0]['start']+=1
        self.reject(raw,'prepared_context_changed')

    def test_tampered_sha_is_not_trusted(self):
        raw=self.payload();self.prepared['catalog']['entries'][0]['file_sha256']='0'*64
        self.reject(raw,'prepared_context_changed')

    def test_wrong_case_is_rejected(self):
        raw=self.payload();raw['case_id']='case_'+'0'*32
        self.reject(raw,'selection_context_mismatch')

    def test_stale_catalog_fingerprint_is_rejected(self):
        raw=self.payload();raw['catalog_sha256']='0'*64
        self.reject(raw,'selection_context_mismatch')

    def test_stale_batch_fingerprint_is_rejected(self):
        raw=self.payload();raw['batch_sha256']='0'*64
        self.reject(raw,'selection_context_mismatch')

    def test_current_original_bytes_tamper_is_rejected(self):
        raw=self.payload();self.store._cases[self.cid].documents[self.ids['D04']].original_bytes+=b'bad'
        self.reject(raw,'current_archive_invalid')

    def test_current_parsed_snapshot_tamper_is_rejected(self):
        raw=self.payload();self.store._cases[self.cid].documents[self.ids['D03']].units[0]['text']+='伪造'
        self.reject(raw,'current_archive_invalid')

    def test_same_text_different_documents_retains_separate_candidates(self):
        store=CaseStore();cid=store.create_case('同文不同出处虚构测试')
        dids=[store.attach_document(cid,f'模拟{i}.docx',document('驾驶人主张：未收到提示。',title=str(i))) for i in range(2)]
        context=self.p.prepare_selection(store,cid,dids,self.settings)
        rows=context['catalog']['entries']
        self.assertEqual(len(rows),2);self.assertEqual(rows[0]['quote'],rows[1]['quote'])
        self.assertNotEqual(rows[0]['candidate_id'],rows[1]['candidate_id'])
        self.assertNotEqual(rows[0]['document_id'],rows[1]['document_id'])

    def test_same_materials_in_another_case_have_different_candidates(self):
        cid=self.store.create_case('另一个虚构案件')
        ids=[self.store.attach_document(cid,*v) for v in self.materials.values()]
        other=self.p.prepare_selection(self.store,cid,ids,self.settings)
        self.assertFalse(set(e['candidate_id'] for e in other['catalog']['entries']) &
                         set(e['candidate_id'] for e in self.prepared['catalog']['entries']))

    def test_d04_term_still_requires_explicit_selected_title_or_body(self):
        self.reject(self.payload((BODY,), '待核实推断：D04的EDR摘要原始数据是否需要核查？'),'evidence_validation_failed')

    def test_explicit_d04_title_restores_without_automatic_context_insertion(self):
        result=self.run_selection(self.payload((BODY,TITLE),'待核实推断：D04的EDR摘要原始数据是否需要核查？'))
        refs=result['resolved_pending_evidence'][0]['sources']
        self.assertEqual([r['quote'] for r in refs],[self.entry(BODY)['quote'],self.entry(TITLE)['quote']])

    def test_dssad_is_not_authorized_by_edr(self):
        error=self.reject(self.payload((BODY,TITLE),'待核实推断：DSSAD字段是否需要核对？'),'evidence_validation_failed')
        self.assertEqual(error.diagnostic['rule'],'unsupported_data_term')
        self.assertEqual(error.diagnostic['unsupported_terms'],['DSSAD'])

    def test_asserted_existence_is_still_rejected(self):
        error=self.reject(self.payload((EDR,), '待核实推断：EDR必然存在的原始数据是否需要核查？'),'evidence_validation_failed')
        self.assertEqual(error.diagnostic['rule'],'asserted_data_existence')

    def test_reasoning_prefix_and_question_requirement_remain(self):
        for reasoning in ('请核查原始数据？','待核实推断：日志缺失。'):
            with self.subTest(reasoning=reasoning):self.reject(self.payload(reasoning=reasoning),'evidence_validation_failed')

    def test_unsupported_reasoning_time_remains_rejected(self):
        self.reject(self.payload(reasoning='待核实推断：2026年11月09日是否发生事故？'),'evidence_validation_failed')

    def test_legacy_d01_d04_summary_counterexample_is_rejected(self):
        raw=self.legacy((SITE,EDR),'现场与EDR时间不同，需要核对。',QUESTION)
        with self.assertRaises(m.MultiAIError) as error:m.validate_case_output(self.store,self.cid,self.prepared['batch'],raw)
        self.assertEqual(error.exception.diagnostic['rule'],'text_not_in_quote')

    def test_legacy_d01_d03_summary_counterexample_is_rejected(self):
        q='待核实推断：D01口述时间与D03日志材料来源是否需要核对？'
        raw=self.legacy((SITE,COMPANY),'现场记录与企业说明的原始数据需要核查。',q)
        with self.assertRaises(m.MultiAIError) as error:m.validate_case_output(self.store,self.cid,self.prepared['batch'],raw)
        self.assertEqual(error.exception.diagnostic['rule'],'text_not_in_quote')

    def test_subject_prefix_negation_semicolon_and_newline_are_kept(self):
        result=self.run_selection(self.payload((CLAIM,), '待核实推断：企业关于收到提示的主张是否有独立证据支持？'))
        self.assertEqual(result['resolved_pending_evidence'][0]['text'],self.entry(CLAIM)['quote'])
        self.assertTrue(result['resolved_pending_evidence'][0]['text'].startswith('企业主张：'))
        result=self.run_selection(self.payload((EDR,), '待核实推断：相对触发摘要的时钟基准是否需要核查？'))
        self.assertEqual(result['resolved_pending_evidence'][0]['text'],self.entry(EDR)['quote'])

    def test_wrong_selection_can_pass_binding_but_is_not_semantic_success(self):
        # 故意不相关的选择；文法/绑定正确不代表问题有依据。
        result=self.run_selection(self.payload((SITE,COMPANY), '待核实推断：D03制动开关记录是否能证明驾驶人踩下踏板？'))
        self.assertEqual(result['validation']['evidence_status'],'passed')
        self.assertEqual(result['validation']['semantic_status'],'pending_human_review')
        self.assertFalse(result['production_import_allowed'])
        self.assertEqual(self.store.get_case(self.cid).facts,[])

    def test_wrong_subject_attribution_is_not_claimed_as_verified(self):
        result=self.run_selection(self.payload((CLAIM,), '待核实推断：驾驶人已收到提示的自述是否需要核实？'))
        self.assertEqual(result['validation']['semantic_status'],'pending_human_review')
        self.assertEqual(result['resolved_pending_evidence'][0]['verification'],'待人工核验')

    def test_legal_responsibility_assertion_and_authority_guard_remain(self):
        self.reject(self.payload(reasoning='待核实推断：根据民法典是否应认定驾驶人承担全部责任？'),'evidence_validation_failed')

    def test_overreach_is_exposed_as_unreviewed_not_claimed_solved(self):
        result=self.run_selection(self.payload((SITE,), '待核实推断：驾驶人是否因未踩刹车造成追尾并应承担全部责任？'))
        self.assertEqual(result['validation']['semantic_status'],'pending_human_review')
        self.assertFalse(result['production_import_allowed'])
        self.assertEqual(self.store.get_case(self.cid).facts,[])

    def test_whole_batch_fails_if_one_item_fails_without_mutation(self):
        raw=self.payload();bad=deepcopy(raw['pending_evidence'][0]);bad['reasoning']='待核实推断：DSSAD是否记录事故？'
        raw['pending_evidence'].append(bad)
        self.reject(raw,'evidence_validation_failed')

    def test_no_sdk_quota_secret_or_import_entrypoint_is_called(self):
        with patch('multidoc_ai.invoke',side_effect=AssertionError('no model')),\
             patch('model_runtime.call_sdk',side_effect=AssertionError('no SDK')),\
             patch('security.QuotaStore',side_effect=AssertionError('no quota')),\
             patch('multidoc_ai.import_case_analysis',side_effect=AssertionError('no import')):
            result=self.run_selection(self.payload())
        self.assertEqual(result['validation']['provider_status'],'not_called')

    def test_legacy_workspace_roundtrip_is_unchanged_and_prototype_not_attachable(self):
        import workspace_bundle as w
        result=self.run_selection(self.payload())
        raw=w.export_workspace(self.store,self.cid)
        restored=CaseStore();w.restore_workspace(restored,raw)
        self.assertEqual(restored.get_case(self.cid).documents.keys(),self.store.get_case(self.cid).documents.keys())
        with self.assertRaises(w.WorkspaceError):w.export_workspace(self.store,self.cid,analysis=result)

    def test_budget_bounds_and_no_api_ready_request(self):
        self.assertLessEqual(self.prepared['budget']['prototype_envelope_bytes'],128000)
        self.assertLessEqual(self.prepared['budget']['input_chars'],16000)
        self.assertNotIn('model',self.prepared['model_input'])
        self.assertNotIn('api_key',json.dumps(self.prepared['model_input']))
        self.assertTrue(self.prepared['required_acknowledgements'])

    def test_low_budget_does_not_truncate_catalog(self):
        with self.assertRaises(self.p.PrototypeError) as e:
            self.p.prepare_selection(self.store,self.cid,list(self.ids.values()),Settings(provider='deepseek',max_request_bytes=1024))
        self.assertEqual(e.exception.code,'prototype_budget_exceeded')

    def test_long_line_chunks_are_reported_not_promoted_to_independent_sources(self):
        store=CaseStore();cid=store.create_case('虚构超长行')
        dids=[store.attach_document(cid,'模拟长行.docx',document('企业主张：'+'甲'*1005+'；未收到提示。')),
              store.attach_document(cid,'模拟正常.docx',document('车辆发生碰撞。'))]
        context=self.p.prepare_selection(store,cid,dids,self.settings)
        self.assertTrue(context['catalog']['excluded'])
        self.assertTrue(all(e['rule']=='physical_line_split' for e in context['catalog']['excluded']))
        self.assertTrue(all(e['document_id']==dids[1] for e in context['catalog']['entries']))

    def test_whitespace_punctuation_are_never_rewritten(self):
        for e in self.prepared['catalog']['entries']:
            source=next(s for s in self.prepared['batch']['sources'] if s['source_id']==e['source_id'])
            self.assertEqual(e['quote'],source['text'])

    def test_stale_or_unknown_protocol_is_not_silently_migrated(self):
        raw=self.payload();raw['schema_version']=m.CANDIDATE_SCHEMA_VERSION
        self.reject(raw,'selection_schema_invalid')

    def test_demo_is_reproducible_and_does_not_read_secrets_or_call_providers(self):
        from tools.run_pending_selection_prototype import run_demo
        with patch('security.Settings.from_secrets',side_effect=AssertionError('no Secrets')),\
             patch('security.QuotaStore',side_effect=AssertionError('no quota')),\
             patch('multidoc_ai.invoke',side_effect=AssertionError('no model')),\
             patch('model_runtime.call_sdk',side_effect=AssertionError('no SDK')):
            first=run_demo();second=run_demo()
        self.assertEqual(first,second)
        self.assertEqual(first['real_model_calls'],0)
        self.assertEqual(len(first['examples']),3)
        self.assertEqual(len(first['expected_rejections']),2)
        self.assertFalse(first['production_import_allowed'])

    def test_demo_has_no_live_or_paid_call_option(self):
        import contextlib,io
        from tools.run_pending_selection_prototype import main
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as caught:
            main(['--run-live'])
        self.assertEqual(caught.exception.code,2)

    def test_selected_claim_compound_line_keeps_all_negative_qualifiers(self):
        store=CaseStore();cid=store.create_case('虚构完整复句')
        text='企业主张：系统未发出提示；驾驶人未收到提示。'
        dids=[store.attach_document(cid,'模拟复句.docx',document(text)),
              store.attach_document(cid,'模拟现场.docx',document('车辆发生碰撞。'))]
        context=self.p.prepare_selection(store,cid,dids,self.settings)
        entry=next(e for e in context['catalog']['entries'] if e['document_id']==dids[0])
        raw={'schema_version':self.p.SCHEMA_VERSION,'prompt_version':self.p.PROMPT_VERSION,'case_id':cid,
             'batch_sha256':context['batch']['batch_sha256'],'catalog_sha256':context['catalog']['sha256'],
             'pending_evidence':[{'anchor_id':entry['candidate_id'],'evidence_ids':[entry['candidate_id']],
                                  'reasoning':'待核实推断：企业关于未发出提示和未收到提示的主张是否需要分别核查？'}]}
        result=self.p.validate_selection(store,cid,context,raw)
        self.assertEqual(result['resolved_pending_evidence'][0]['text'],text)
        self.assertEqual(entry['quote'],text)

    def test_repeated_text_in_one_document_has_distinct_locatable_anchors(self):
        store=CaseStore();cid=store.create_case('虚构同文不同位置')
        dids=[store.attach_document(cid,'模拟重复.docx',document('未收到提示。','未收到提示。')),
              store.attach_document(cid,'模拟现场.docx',document('车辆发生碰撞。'))]
        context=self.p.prepare_selection(store,cid,dids,self.settings)
        entries=[e for e in context['catalog']['entries'] if e['document_id']==dids[0]]
        self.assertEqual(len(entries),2)
        self.assertEqual(entries[0]['quote'],entries[1]['quote'])
        self.assertNotEqual(entries[0]['candidate_id'],entries[1]['candidate_id'])
        self.assertNotEqual(entries[0]['evidence_span_id'],entries[1]['evidence_span_id'])

    def test_catalog_raw_source_id_collision_tamper_is_rejected(self):
        raw=self.payload()
        self.prepared['batch']['sources'][1]['source_id']=self.prepared['batch']['sources'][0]['source_id']
        self.reject(raw,'prepared_context_changed')

    def test_selected_other_case_id_never_falls_back_to_same_text(self):
        raw=self.payload()
        cid=self.store.create_case('其他案件副本')
        ids=[self.store.attach_document(cid,*v) for v in self.materials.values()]
        other=self.p.prepare_selection(self.store,cid,ids,self.settings)
        foreign=next(e for e in other['catalog']['entries'] if e['quote'].rstrip('\r\n')==EDR)
        raw['pending_evidence'][0]['evidence_ids'][1]=foreign['candidate_id']
        self.reject(raw,'candidate_not_in_catalog')

    def test_only_full_lines_are_catalogued_no_unselected_extra_support(self):
        raw=self.payload((SITE,), '待核实推断：EDR原始数据是否需要核查？')
        error=self.reject(raw,'evidence_validation_failed')
        self.assertEqual(error.diagnostic['rule'],'unsupported_data_term')
        self.assertEqual(error.diagnostic['document_ids'],[self.ids['D01']])
