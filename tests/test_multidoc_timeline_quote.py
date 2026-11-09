"""固定虚构材料与人工反例；只运行本地验证及注入响应，不调用模型。"""
from copy import deepcopy
from pathlib import Path
import unittest
from pydantic import ValidationError
import test_multidoc_ai as fixtures
from test_case_store import document
from ai_analysis import SENTENCE_END


class MultiTimelineQuote(unittest.TestCase):
    def setUp(self):
        self.b = fixtures.MultiAI()
        self.b.setUp()
        self.addCleanup(self.b.tmp.cleanup)

    def samples(self):
        b = self.b
        root = Path(__file__).resolve().parents[1] / 'samples_multidoc'
        b.ids = [b.store.attach_document(b.cid, p.name, p.read_bytes()) for p in sorted(root.iterdir())]
        b.batch = b.m.prepare_case(b.store, b.cid, b.ids, b.settings)

    def synthetic(self, text):
        b = self.b
        did = b.store.attach_document(b.cid, '模拟_分句反例.docx', document(text))
        b.ids = [b.ids[0], did]
        b.batch = b.m.prepare_case(b.store, b.cid, b.ids, b.settings)
        return next(s for s in b.batch['sources'] if s['document_id'] == did and text in s['text'])

    def source(self, part):
        return next(s for s in self.b.batch['sources'] if part in s['text'])

    def event(self, source, quote, time=None, kind='事实'):
        ref = {'source_id': source['source_id'], 'quote': quote}
        return {'kind': kind, 'text': quote, 'reasoning': '', 'sources': [deepcopy(ref)],
                'event_source': deepcopy(ref), 'time_source': deepcopy(ref) if time else None,
                'time_state': 'explicit' if time else 'unknown', 'time_precision': 'minute' if time else 'unknown',
                'time_text': time or '未知'}

    def payload(self, rows):
        payload = self.b.payload()
        payload.update(facts=[], relations=[], timeline=rows)
        return payload

    def validate(self, rows):
        b = self.b
        return b.m.validate_case_output(b.store, b.cid, b.batch, self.payload(rows))

    def rejected(self, rows, rule):
        before = self.b.store.export_json(self.b.cid)
        original = deepcopy(rows)
        with self.assertRaises(self.b.m.MultiAIError) as caught:
            self.validate(rows)
        self.assertEqual(caught.exception.diagnostic['rule'], rule)
        self.assertEqual(caught.exception.diagnostic['section'], 'timeline')
        self.assertEqual(caught.exception.diagnostic['item_index'], 0)
        self.assertEqual(self.b.store.export_json(self.b.cid), before)
        self.assertEqual(rows, original)

    def test_prompt_explicit_boundary_and_semantic_preservation(self):
        prompt = self.b.m.PROMPT
        for text in ('内部句段分隔符', '分号（；;）', '换行（CR/LF）', '末尾换行也不能包含',
                     '陈述主体、否定词、限定语和完整时间信息', '不能安全独立拆分',
                     '不得自动拼接、删除内部标点、合并行或改写原文'):
            with self.subTest(requirement=text):
                self.assertIn(text, prompt)

    def test_separator_set_matches_existing_rule(self):
        for char in '。！？!?；;\r\n':
            self.assertIsNotNone(SENTENCE_END.fullmatch(char))
        for char in '，,：:、':
            self.assertIsNone(SENTENCE_END.fullmatch(char))

    def test_actual_four_materials_full_body_quotes_rejected(self):
        self.samples()
        for fragment in ('现场记录：', '驾驶人未收到', '系统已发出', '摘要：'):
            with self.subTest(fragment=fragment):
                source = self.source(fragment)
                self.rejected([self.event(source, source['text'])], 'timeline_multi_sentence')

    def test_actual_single_segments_preserve_independent_sources_and_times(self):
        self.samples()
        expected = [('现场记录：', '现场记录：2026年11月1日08:30车辆发生碰撞。', '2026年11月1日08:30', '事实'),
                    ('驾驶人未收到', '驾驶人未收到接管提示。', None, '主张'),
                    ('系统已发出', '系统已发出接管提示。', None, '主张'),
                    ('摘要：', '摘要：2026年11月1日08:31车辆发生碰撞。', '2026年11月1日08:31', '事实')]
        rows = [self.event(self.source(part), quote, time, kind) for part, quote, time, kind in expected]
        result = self.validate(rows)
        self.assertEqual(len(result['timeline']), 4)
        self.assertEqual(len({row['document_id'] for row in result['timeline']}), 4)
        for row in result['timeline']:
            source = self.source(row['text'])
            self.assertEqual(row['event_source']['source_id'], source['source_id'])
            self.assertEqual(row['event_source']['quote'], row['text'])
            self.assertEqual(row['event_source']['document_sha256'], source['file_sha256'])
            unit = self.b.batch['records'][source['document_id']]['units'][source['unit_index']]['text']
            ref = row['event_source']
            self.assertEqual(unit[ref['start']:ref['end']], ref['quote'])
        self.assertEqual({r['normalized_time'] for r in result['timeline'] if r['time_state'] == 'explicit'},
                         {'2026-11-01T08:30', '2026-11-01T08:31'})
        self.assertEqual(sum(r['time_state'] == 'unknown' for r in result['timeline']), 2)

    def test_actual_electronic_summary_multiple_sentences_rejected(self):
        self.samples()
        quote = '摘要：2026年11月1日08:31车辆发生碰撞。原始日志未提供。'
        self.rejected([self.event(self.source('摘要：'), quote)], 'timeline_multi_sentence')

    def test_internal_semicolon_both_widths_rejected(self):
        for delimiter in ('；', ';'):
            text = '车辆发生碰撞' + delimiter + '随后停车。'
            source = self.synthetic(text)
            self.rejected([self.event(source, text)], 'timeline_multi_sentence')

    def test_internal_sentence_punctuation_rejected(self):
        for delimiter in ('。', '！', '？', '!', '?'):
            text = '车辆发生碰撞' + delimiter + '随后停车。'
            self.rejected([self.event(self.synthetic(text), text)], 'timeline_multi_sentence')

    def test_internal_newlines_rejected(self):
        # 单测下层绑定规则；生产来源按行分块，跨行引用可能更早被拒绝。
        from ai_analysis import _timeline_binding, TimelineItem, AIError
        for delimiter in ('\n', '\r', '\r\n'):
            with self.subTest(delimiter=repr(delimiter)):
                text = '车辆发生碰撞' + delimiter + '随后停车。'
                source = {'source_id': 'S001'}
                row = TimelineItem.model_validate(self.event(source, text))
                ref = {'unit_index': 0, 'start': 0, 'end': len(text), 'quote': text}
                with self.assertRaises(AIError) as caught:
                    _timeline_binding(row, [ref], {}, {'units': [{'text': text}]})
                self.assertEqual(str(caught.exception), '事件引文跨句或跨行，请拆为独立原文事件；不能合并多个事件的时间。')

    def test_cross_line_join_rejected_before_timeline_binding(self):
        text = '车辆发生碰撞\n随后停车。'
        b = self.b
        did = b.store.attach_document(b.cid, '模拟_跨行.docx', document(text))
        b.ids = [b.ids[0], did]
        b.batch = b.m.prepare_case(b.store, b.cid, b.ids, b.settings)
        source = next(s for s in b.batch['sources'] if s['document_id'] == did)
        self.rejected([self.event(source, text)], 'quote_not_found')

    def test_trailing_newline_is_not_ignored_by_validator(self):
        text = '车辆发生碰撞。\n'
        self.rejected([self.event(self.synthetic(text), text)], 'timeline_multi_sentence')

    def test_terminal_punctuation_and_no_punctuation_allowed_at_unit_end(self):
        for suffix in ('。', '；', ';', '！', '?', ''):
            text = '车辆发生碰撞' + suffix
            result = self.validate([self.event(self.synthetic(text), text)])
            self.assertEqual(result['timeline'][0]['text'], text)

    def test_complete_claim_subject_negation_qualifier_and_time_preserved(self):
        text = '驾驶人主张：2026年11月1日08:30尚未收到有效接管提示。'
        result = self.validate([self.event(self.synthetic(text), text, '2026年11月1日08:30', '主张')])
        self.assertEqual(result['timeline'][0]['text'], text)
        self.assertEqual(result['timeline'][0]['kind'], '主张')

    def test_cutting_claim_or_negation_prefix_rejected(self):
        text = '驾驶人主张：2026年11月1日08:30尚未收到有效接管提示。'
        source = self.synthetic(text)
        for quote in ('2026年11月1日08:30尚未收到有效接管提示。', '收到有效接管提示。'):
            self.rejected([self.event(source, quote, kind='主张')], 'timeline_incomplete_sentence')

    def test_cutting_time_from_sentence_rejected(self):
        text = '2026年11月1日08:30车辆发生碰撞。'
        self.rejected([self.event(self.synthetic(text), '车辆发生碰撞。')], 'timeline_incomplete_sentence')

    def test_borrowed_time_source_and_lost_precision_rejected(self):
        self.samples()
        quote = '现场记录：2026年11月1日08:30车辆发生碰撞。'
        row = self.event(self.source('现场记录：'), quote, '2026年11月1日08:30')
        row['time_source'] = {'source_id': self.source('摘要：')['source_id'], 'quote': '摘要：2026年11月1日08:31车辆发生碰撞。'}
        self.rejected([row], 'reference_crosses_document')
        row = self.event(self.source('现场记录：'), quote, '2026年11月1日08:30')
        row['time_precision'] = 'date'
        self.rejected([row], 'time_precision_mismatch')

    def test_deleting_internal_punctuation_is_not_valid_quote(self):
        text = '车辆发生碰撞；随后停车。'
        self.rejected([self.event(self.synthetic(text), text.replace('；', ''))], 'quote_not_found')

    def test_mock_failure_keeps_receipt_and_does_not_import_or_rewrite(self):
        self.samples()
        b = self.b
        source = self.source('现场记录：')
        payload = self.payload([self.event(source, source['text'])])
        before = deepcopy(payload)
        case_before = b.store.export_json(b.cid)
        with self.assertRaises(b.m.MultiAIError) as err:
            b.run_ai(payload, coverage_acknowledged=b.batch['required_ack'])
        receipt = err.exception.receipt
        self.assertEqual(receipt['validation_diagnostic']['rule'], 'timeline_multi_sentence')
        self.assertEqual(receipt['token_usage']['total_tokens'], 121)
        self.assertEqual(receipt['format_status'], 'passed')
        self.assertEqual(receipt['evidence_status'], 'failed')
        self.assertEqual(payload, before)
        self.assertEqual(b.store.export_json(b.cid), case_before)

    def test_cannot_safely_split_does_not_manufacture_timeline(self):
        text = '驾驶人主张；尚未收到提示，随后发生碰撞。'
        source = self.synthetic(text)
        payload = self.payload([])
        payload['facts'] = [{'kind': '主张', 'text': text, 'reasoning': '',
                             'sources': [{'source_id': source['source_id'], 'quote': text}]}]
        result = self.b.m.validate_case_output(self.b.store, self.b.cid, self.b.batch, payload)
        self.assertEqual(result['timeline'], [])
        self.assertEqual(result['facts'][0]['text'], text)

    def test_facts_reasoning_empty_contract_retained(self):
        row = self.b.row()
        row['reasoning'] = '不应出现说明'
        with self.assertRaises(ValidationError):
            self.b.m.FactItem.model_validate(row)
