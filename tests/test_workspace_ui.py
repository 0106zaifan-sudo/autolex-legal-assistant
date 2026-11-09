"""页面真保存→新AppTest会话→离线恢复；uploader用内存文件，不调用AI。"""
import sys
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from case_store import CaseStore
from ui_isolation import IsolatedUITestCase
import test_workspace_bundle as fixtures

ROOT=Path(__file__).resolve().parents[1]

class Upload:
    def __init__(self,name,data):self.name=name;self.data=data;self.size=len(data)
    def getvalue(self):return self.data

class WorkspaceUI(IsolatedUITestCase):
    def setUp(self):
        super().setUp();main=sys.modules['__main__'];self.addCleanup(sys.modules.__setitem__,'__main__',main)
        self.f=fixtures.WorkspaceBundle();self.f.setUp();self.addCleanup(self.f.b.tmp.cleanup)

    def app(self,store=None,analysis=None):
        app=AppTest.from_string("from case_ui import render_case_workspace\nrender_case_workspace({},"+repr(str(ROOT))+")",default_timeout=30)
        app.session_state['_case_store']=store if store is not None else CaseStore()
        if analysis is not None:app.session_state['_md_result']=analysis
        return app

    def test_generate_clear_session_restore_and_display_full_four_document_case(self):
        source=self.app(self.f.store,self.f.analysis).run();cid=self.f.cid
        self.assertFalse(source.exception)
        source.checkbox(key='workspace_include_'+cid).check().run()
        source.button(key='workspace_generate_'+cid).click().run();self.assertFalse(source.exception)
        package=source.session_state['_workspace_download']['data']
        self.assertTrue(any(e.proto.label=='下载案件工作包' for e in source.get('download_button')))
        # 新AppTest代表已清空的会话，不传旧store/认证/分析缓存。
        restored=self.app()
        def uploader(*args,**kwargs):return Upload('模拟工作包.zip',package) if kwargs['key']=='workspace_zip_upload' else ([] if kwargs.get('accept_multiple_files') else None)
        with patch('workspace_ui.st.file_uploader',side_effect=uploader):
            restored.run();self.assertFalse(restored.session_state['_case_store'].list_cases())
            restored.checkbox(key='workspace_import_open').check().run()
            restored.checkbox(key='workspace_import_consent').check().run();restored.button(key='workspace_import').click().run()
        self.assertFalse(restored.exception)
        store=restored.session_state['_case_store'];self.assertEqual(store.export_json(cid),self.f.store.export_json(cid))
        self.assertFalse(restored.session_state['md_consent'])
        self.assertNotIn('_md_result',restored.session_state)
        self.assertEqual(restored.session_state['_workspace_analysis'][cid],self.f.analysis)
        self.assertEqual(len(store.get_case(cid).timeline),4);self.assertEqual(len(store.get_case(cid).relation_reviews),2)
        self.assertEqual(restored.selectbox(key='active_case').value,cid)
        self.assertTrue(any('历史记录' in w.value for w in restored.warning))
        self.assertTrue(any('time_text' in df.value.columns and set(df.value['time_text'])>={'2026年11月1日08:30','2026年11月1日08:31'} for df in restored.dataframe))
        for did in self.f.b.ids:self.assertEqual(store.get_original(cid,did),self.f.store.get_original(cid,did))
        self.assertTrue(restored.json)  # 历史回执和显式附件可查看。
        self.assertFalse(restored.checkbox(key='workspace_include_'+cid).disabled)
        restored.checkbox(key='workspace_include_'+cid).check().run()
        restored.button(key='workspace_generate_'+cid).click().run();self.assertFalse(restored.exception)
        from workspace_bundle import restore_workspace
        next_store=CaseStore();again=restore_workspace(next_store,restored.session_state['_workspace_download']['data'])
        self.assertEqual(again['analysis'],self.f.analysis)
        self.assertEqual(next_store.export_json(cid),self.f.store.export_json(cid))

    def test_download_requires_explicit_generation_and_absent_cache_is_disabled(self):
        app=self.app(self.f.store).run();cid=self.f.cid
        self.assertTrue(app.checkbox(key='workspace_include_'+cid).disabled)
        self.assertNotIn('_workspace_download',app.session_state)
        app.button(key='workspace_generate_'+cid).click().run();self.assertFalse(app.exception)
        self.assertIn('_workspace_download',app.session_state)
        self.f.store.record_missing(cid,'模拟新事项',self.f.b.ids)
        app.run();self.assertNotIn('_workspace_download',app.session_state)

    def test_failed_ui_import_does_not_pollute_existing_store(self):
        app=self.app(self.f.store);before=self.f.store.export_json(self.f.cid)
        with patch('workspace_ui.st.file_uploader',side_effect=lambda *a,**k:Upload('模拟损坏.zip',b'bad') if k['key']=='workspace_zip_upload' else ([] if k.get('accept_multiple_files') else None)):
            app.run();app.checkbox(key='workspace_import_open').check().run();app.checkbox(key='workspace_import_consent').check().run();app.button(key='workspace_import').click().run()
        self.assertFalse(app.exception);self.assertTrue(app.error)
        self.assertEqual(self.f.store.export_json(self.f.cid),before)
        self.assertEqual(len(self.f.store.list_cases()),1)

    def test_legacy_ui_rejects_duplicate_names_before_mapping(self):
        app=self.app();doc=next(iter(self.f.store.get_case(self.f.cid).documents.values()))
        def upload(*a,**k):
            if k['key']=='workspace_legacy_json':return Upload('AutoLex_案件结构化.json',self.f.store.export_json(self.f.cid).encode())
            if k['key']=='workspace_legacy_files':return [Upload(doc.file_name,doc.original_bytes)]*2
            return None
        with patch('workspace_ui.st.file_uploader',side_effect=upload):
            app.run();app.checkbox(key='workspace_import_open').check().run();app.checkbox(key='workspace_legacy_consent').check().run();app.button(key='workspace_legacy_import').click().run()
        self.assertFalse(app.exception);self.assertTrue(app.error);self.assertFalse(app.session_state['_case_store'].list_cases())

    def test_clear_session_also_removes_package_and_history_caches(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30);app.secrets['APP_MODE']='local'
        app.session_state['_case_store']=self.f.store
        app.session_state['_workspace_histories']={self.f.cid:'imported_unverified_identity'}
        app.session_state['_workspace_analysis']={self.f.cid:self.f.analysis}
        app.run();self.assertFalse(app.exception)
        app.button(key='workspace_generate_'+self.f.cid).click().run();self.assertIn('_workspace_download',app.session_state)
        next(b for b in app.sidebar.button if b.label=='清空本会话资料').click().run()
        self.assertFalse(app.exception)
        for key in ('_workspace_download','_workspace_histories','_workspace_analysis'):
            self.assertNotIn(key,app.session_state)
        self.assertFalse(app.session_state['_case_store'].list_cases())
