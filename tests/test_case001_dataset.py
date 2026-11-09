"""CASE-001资料/人工Gold/预算测试；没有模型输出或模型能力指标。"""
from copy import deepcopy
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from core import extract
from evidence import make_span,snapshot_hash
from security import Settings
from multidoc_ai import prepare_case,candidate_request_for

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'datasets'/'CASE-001';STANDARD=DATA/'standard'
spec=importlib.util.spec_from_file_location('case001_generator',ROOT/'tools'/'generate_case_001.py')
gen=importlib.util.module_from_spec(spec);spec.loader.exec_module(gen)


class Case001Dataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((STANDARD/'manifest.json').read_text())
        cls.gold=json.loads((STANDARD/'gold_standard.json').read_text())
        cls.gold_spec=json.loads((DATA/'gold_specs.json').read_text())
        cls.scenario=json.loads((DATA/'scenario.json').read_text())
        cls.batches=json.loads((STANDARD/'batches.json').read_text())
        cls.report=json.loads((STANDARD/'offline_report.json').read_text())
        cls.files={e['material_id']:(Path(e['path']).name,(STANDARD/e['path']).read_bytes()) for e in cls.manifest['documents']}
        cls.store,cls.ids=gen.build_store(cls.files)

    def test_exact_eight_fictional_files_parse_without_missing_body(self):
        self.assertEqual(len(self.files),8)
        self.assertEqual(sum(name.endswith('.pdf') for name,_ in self.files.values()),4)
        for item in self.manifest['documents']:
            name,data=self.files[item['material_id']];record=extract(name,data)
            self.assertEqual(hashlib.sha256(data).hexdigest(),item['sha256'])
            self.assertEqual(snapshot_hash(record['units']),item['parsed_text_sha256'])
            self.assertIn(record['parse_report']['status'],('parsed','partial'))
            text='\n'.join(u['text'] for u in record['units'])
            self.assertIn('完全虚构，仅用于软件测试',text)
            self.assertIn('CASE-001-E01',text);self.assertNotIn('08:30:20',text)
            self.assertTrue(text.strip());self.assertEqual(len(data),item['size'])

    def test_all_checksum_entries_match_exact_bytes(self):
        lines=(STANDARD/'SHA256SUMS').read_text().splitlines()
        self.assertEqual(len(lines),13)
        for line in lines:
            expected,name=line.split('  ',1)
            self.assertEqual(hashlib.sha256((STANDARD/name).read_bytes()).hexdigest(),expected)
        self.assertEqual(self.manifest['baseline_sha'],'2ff740104cdd334f33d085e8a90d7e8053b6a4f9')

    def test_all_gold_quotes_are_unique_exact_spans(self):
        self.assertEqual(len(self.gold['items']),26)
        self.assertIn('助手',self.gold['status'])
        for item in self.gold['items']:
            self.assertTrue(item['forbidden_inferences']);self.assertTrue(item['review_reason']);self.assertTrue(item['test_categories'])
            for ref in item['citations']:
                doc=self.store.get_case(gen.CASE_ID).documents[ref['document_id']]
                self.assertEqual(doc.units[ref['unit_index']]['text'][ref['start']:ref['end']],ref['quote'])
                self.assertEqual(sum(u['text'].count(ref['quote']) for u in doc.units),1)
                span=make_span(gen.CASE_ID,doc,ref['unit_index'],ref['start'],ref['end'],ref['quote'])
                self.assertEqual(span.evidence_id,ref['fixture_evidence_id'])
                self.assertEqual(span.location,ref['location'])
                self.assertEqual(hashlib.sha256(ref['quote'].encode()).hexdigest(),ref['quote_sha256'])

    def test_gold_judgments_are_independent_manual_spec_not_rule_outputs(self):
        expected={row['id']:row for row in self.gold_spec['items']}
        for row in self.gold['items']:
            for key in ('expected_judgment','review_reason','forbidden_inferences','test_categories','evaluation_mode','offline_rule_check'):
                self.assertEqual(row[key],expected[row['id']][key])
            self.assertEqual([(c['material_id'],c['quote']) for c in row['citations']],[(c['document_id'],c['quote']) for c in expected[row['id']]['citations']])
        self.assertEqual(len(self.report['limited_rule_checks']),3)
        self.assertEqual(len(self.report['manual_semantic_items_not_executed']),23)
        self.assertEqual(self.report['model_semantic_accuracy'],'not_measured')

    def test_rebuild_is_byte_identical_and_does_not_open_quota_or_model(self):
        with patch('security.QuotaStore',side_effect=AssertionError('no quota access')),patch('multidoc_ai.invoke',side_effect=AssertionError('no model')),patch('model_runtime.call_sdk',side_effect=AssertionError('no SDK calls')):
            first=gen.render_all();second=gen.render_all()
        self.assertEqual(first,second)
        for name,data in first.items():self.assertEqual((STANDARD/name).read_bytes(),data)

    def test_check_mode_does_not_write_files(self):
        with patch.object(Path,'write_bytes',side_effect=AssertionError('check must not write')):
            gen.generate(STANDARD,check=True)

    def test_missing_or_ambiguous_gold_quote_is_rejected(self):
        for quote in ('不存在的模拟句段XYZ','完全虚构'):
            with self.assertRaises(gen.DatasetError):gen.locate(self.store,self.ids,{'document_id':'D01','quote':quote})

    def test_all_batches_fit_backend_actual_request_limits(self):
        seen=set();gold_focus=set()
        for b in self.batches['batches']:
            self.assertTrue(2<=len(b['documents'])<=4);seen.update(b['documents']);gold_focus.update(b['gold_focus'])
            batch=prepare_case(self.store,gen.CASE_ID,[self.ids[d] for d in b['documents']],Settings(provider='deepseek',model='deepseek-flash'))
            _,budget=candidate_request_for(batch,Settings(provider='deepseek',model='deepseek-flash'))
            self.assertEqual(budget['request_bytes'],b['preflight']['request_bytes'])
            self.assertEqual(budget['input_chars'],b['preflight']['input_chars'])
            self.assertLessEqual(budget['input_chars'],16000);self.assertLessEqual(budget['request_bytes'],128000)
            self.assertLessEqual(b['preflight']['source_blocks'],96)
            for gid in b['gold_focus']:
                item=next(i for i in self.gold_spec['items'] if i['id']==gid)
                self.assertTrue({r['document_id'] for r in item['citations']}<=set(b['documents']))
        self.assertEqual(seen,set(self.files))
        self.assertTrue({r['id'] for r in self.gold_spec['items'] if r['evaluation_mode']!='offline_preflight'}<=gold_focus)
        with self.assertRaises(ValueError):prepare_case(self.store,gen.CASE_ID,list(self.ids.values()),Settings())

    def test_budget_windows_do_not_reset_or_assume_actual_allowance(self):
        self.assertEqual(len(self.batches['budget_windows']),2)
        for w in self.batches['budget_windows']:
            self.assertLessEqual(w['planned_calls'],5);self.assertLessEqual(w['request_bytes'],256000)
            self.assertTrue(w['budget_only_not_authorized'])
            self.assertGreaterEqual(w['minimum_between_calls_seconds'],30)
        self.assertGreater(sum(w['request_bytes'] for w in self.batches['budget_windows']),256000)

    def test_only_blind_materials_in_compiled_model_input(self):
        for b in self.batches['batches']:
            settings=Settings(provider='deepseek',model='deepseek-flash')
            batch=prepare_case(self.store,gen.CASE_ID,[self.ids[d] for d in b['documents']],settings)
            request,_=candidate_request_for(batch,settings);payload=json.loads(request['input'])
            for forbidden in ('gold_specs','gold_standard','T_REF','08:30:20','50毫秒真实传输'):
                self.assertNotIn(forbidden,request['input'])
            self.assertEqual({d['file_name'] for d in payload['documents']},set(b['file_names']))

    def test_reference_graph_has_no_future_document_reference(self):
        docs={d['id']:d for d in self.scenario['documents']}
        def compiled(d):return datetime.strptime(d['compiled_at'],'%Y年%m月%d日%H:%M')
        for edge in self.scenario['source_graph']['edges']:
            self.assertIn(edge['document'],docs)
            if edge['source'] in docs:self.assertGreaterEqual(compiled(docs[edge['document']]),compiled(docs[edge['source']]))
            else:self.assertIn(edge['source'],self.scenario['source_graph']['roots'])
        self.assertTrue(any(e['document']=='D04' and e['source']=='IN-01' for e in self.scenario['source_graph']['edges']))
        self.assertFalse(any(e['document']=='D04' and e['source']=='D08' for e in self.scenario['source_graph']['edges']))

    def test_shared_quote_keeps_distinct_files_and_anchors(self):
        item=next(i for i in self.gold['items'] if i['id']=='G018');refs=item['citations'][:2]
        self.assertEqual(refs[0]['quote'],refs[1]['quote'])
        self.assertNotEqual(refs[0]['document_id'],refs[1]['document_id'])
        self.assertNotEqual(refs[0]['file_sha256'],refs[1]['file_sha256'])
        self.assertNotEqual(refs[0]['fixture_evidence_id'],refs[1]['fixture_evidence_id'])

    def test_generated_output_never_overwrites_different_user_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp);(target/'manifest.json').write_bytes(b'USER_WORK_DO_NOT_REPLACE')
            with self.assertRaises(gen.DatasetError):gen.generate(target)
            self.assertEqual((target/'manifest.json').read_bytes(),b'USER_WORK_DO_NOT_REPLACE')
            self.assertEqual(len(list(target.iterdir())),1)

    def test_parser_risks_and_uncovered_semantics_are_explicit(self):
        pdfs=[d for d in self.manifest['documents'] if d['path'].endswith('.pdf')]
        self.assertTrue(all(d['status']=='partial' and d['requires_acknowledgement'] for d in pdfs))
        self.assertTrue(all(any(i['code']=='pdf_table_coverage_unverified' for i in d['issues']) for d in pdfs))
        self.assertEqual(self.report['real_model_calls'],0);self.assertEqual(self.report['mock_model_calls'],0)
        self.assertFalse(self.report['quota_database_opened']);self.assertTrue(self.report['known_limits'])
