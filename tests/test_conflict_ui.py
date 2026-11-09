"""实际AppTest筛选/复核交互；纯规则，不请求任何模型。"""
import json,sys
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from ui_isolation import IsolatedUITestCase
import test_conflict_review as fixtures
from conflict_review import build_workbench
from workspace_bundle import export_workspace,restore_workspace
from case_store import CaseStore

ROOT=Path(__file__).resolve().parents[1]

class ConflictUI(IsolatedUITestCase):
    def setUp(self):
        super().setUp();main=sys.modules['__main__'];self.addCleanup(sys.modules.__setitem__,'__main__',main)
        self.f=fixtures.ConflictReview();self.f.setUp()

    def app(self,store=None):
        app=AppTest.from_string("import streamlit as st\nfrom conflict_ui import render_conflict_workbench\nrender_conflict_workbench(st.session_state['store'],st.session_state['cid'])",default_timeout=30)
        app.session_state['store']=store if store is not None else self.f.store;app.session_state['cid']=self.f.cid
        return app.run()

    def open(self,app):return app.checkbox(key='cr_open_'+self.f.cid).check().run()

    def test_time_view_full_sources_and_no_truth_decision(self):
        app=self.open(self.app());cid=self.f.cid
        row=next(r for r in build_workbench(self.f.store,cid) if r['time']['literal_delta_seconds'] is not None and abs(r['time']['literal_delta_seconds'])==60)
        app.selectbox(key='cr_pair_'+cid).set_value(row['relation_id']).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('1分钟' in info.value for info in app.info))
        self.assertTrue(any('无法可靠比较' in warning.value for warning in app.warning))
        for side in ('left','right'):
            self.assertEqual(app.text_area(key='cr_quote_'+cid+'_'+row['relation_id']+'_'+side).value,row[side]['quote'])
            self.assertTrue(any(row[side]['file_sha256'] in caption.value for caption in app.caption))
        self.assertEqual(self.f.store.get_case(cid).reviews,[])

    def test_modify_reject_and_review_again_preserves_original_candidate(self):
        cid=self.f.cid;app=self.open(self.app());rid=app.selectbox(key='cr_pair_'+cid).value
        original=next(r.model_dump() for r in self.f.store.get_case(cid).relations if r.relation_id==rid)
        with patch.object(self.f.store,'confirm_fact',side_effect=AssertionError('must not confirm')):
            for i,status in enumerate(('modified','rejected','needs_review')):
                app.selectbox(key='cr_status').set_value(status);app.selectbox(key='cr_type').set_value('needs_verification')
                app.text_input(key='cr_reviewer').set_value('模拟审阅人'+str(i));app.text_area(key='cr_reason').set_value('核对当前材料的时钟与来源'+str(i))
                app.button(key='cr_save').click().run();self.assertFalse(app.exception)
        history=self.f.store.get_case(cid).relation_reviews
        self.assertEqual([r.status for r in history],['modified','rejected','needs_review'])
        self.assertEqual(history[2].previous_review_id,history[1].review_id)
        self.assertEqual(next(r.model_dump() for r in self.f.store.get_case(cid).relations if r.relation_id==rid),original)
        self.assertEqual(self.f.store.get_case(cid).reviews,[])
        self.assertTrue(any('needs_review' in item.value for item in app.json))

    def test_filters_and_target_switch_do_not_reuse_review_fields(self):
        app=self.open(self.app());cid=self.f.cid
        app.text_input(key='cr_reviewer').set_value('旧审阅人');app.text_area(key='cr_reason').set_value('旧理由');app.run()
        current=app.selectbox(key='cr_pair_'+cid).value
        other=next(r['relation_id'] for r in build_workbench(self.f.store,cid) if r['relation_id']!=current)
        app.selectbox(key='cr_pair_'+cid).set_value(other).run()
        self.assertEqual(app.text_input(key='cr_reviewer').value,'');self.assertEqual(app.text_area(key='cr_reason').value,'')
        app.selectbox(key='cr_category_'+cid).set_value('时间记载').run();self.assertFalse(app.exception)
        app.selectbox(key='cr_filter_'+cid).set_value('confirmed').run();self.assertFalse(app.exception)
        self.assertTrue(any('没有项目' in info.value for info in app.info))

    def test_workspace_roundtrip_view_and_latest_review_identical(self):
        cid=self.f.cid;row=build_workbench(self.f.store,cid)[0]
        self.f.store.review_relation(cid,row['relation_id'],'modified','related','模拟核验人','保留关联但不能确认矛盾')
        target=CaseStore();restore_workspace(target,export_workspace(self.f.store,cid))
        app=self.open(self.app(target));app.selectbox(key='cr_pair_'+cid).set_value(row['relation_id']).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('模拟核验人' in text.value for text in app.text))
        self.assertEqual(build_workbench(target,cid),build_workbench(self.f.store,cid))

    def test_actual_case_workspace_has_workbench_and_clear_removes_drafts(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30);app.secrets['APP_MODE']='local'
        app.session_state['_case_store']=self.f.store;app.run();self.assertFalse(app.exception)
        app.checkbox(key='cr_open_'+self.f.cid).check().run();self.assertFalse(app.exception)
        self.assertTrue(app.selectbox(key='cr_pair_'+self.f.cid))
        app.text_input(key='cr_reviewer').set_value('模拟草稿复核人').run()
        next(b for b in app.sidebar.button if b.label=='清空本会话资料').click().run()
        self.assertFalse(app.exception);self.assertNotIn('cr_reviewer',app.session_state)

    def test_invalid_evidence_blocks_view_and_empty_reason_blocks_review(self):
        app=self.open(self.app());before=self.f.store.export_json(self.f.cid)
        app.button(key='cr_save').click().run();self.assertFalse(app.exception);self.assertTrue(app.error)
        self.assertEqual(self.f.store.export_json(self.f.cid),before)
        eid=next(iter(self.f.store._cases[self.f.cid].evidence));self.f.store._cases[self.f.cid].evidence[eid].quote='PRIVATE_INVALID_QUOTE'
        app.run();self.assertFalse(app.exception)
        self.assertTrue(any('未生成有效结论' in error.value for error in app.error))
        self.assertTrue(all('PRIVATE_INVALID_QUOTE' not in error.value for error in app.error))
