from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest
from document_parser import parse_document

ROOT=Path(__file__).resolve().parents[1]


class CaseWorkspaceUITests(unittest.TestCase):
    def app(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30)
        app.secrets['APP_MODE']='local'
        return app.run()

    def create(self,app,title='模拟案件A'):
        app.text_input(key='case_title').set_value(title)
        app.button(key='create_case_submit').click().run()
        self.assertFalse(app.exception)
        return app.selectbox(key='active_case').value

    def test_create_case_and_import_explicit_offline_demo(self):
        app=self.app();cid=self.create(app)
        self.assertFalse(app.session_state['_case_store'].get_case(cid).documents)
        app.button(key='case_add_demo').click().run()
        self.assertFalse(app.exception)
        case=app.session_state['_case_store'].get_case(cid)
        self.assertEqual(len(case.documents),1)
        self.assertEqual(len(case.timeline),3)
        self.assertTrue(all(s.kind=='documented_fact' and s.verification=='unverified' for s in case.facts))
        self.assertTrue(all(s.origin=='simulation' for s in case.inferences))
        self.assertTrue(app.button(key='run_ai').disabled)

    def test_selected_documents_attach_only_to_active_case_and_quote_is_saved(self):
        app=self.app();app.sidebar.button[1].click().run()
        cid=self.create(app)
        rid=next(k for k,r in app.session_state['records'].items() if r['文件名']=='模拟_辅助驾驶责任.docx')
        self.assertFalse(app.session_state['_case_store'].get_case(cid).documents)
        app.multiselect(key='case_documents_'+cid).set_value([rid])
        app.button(key='attach_documents').click().run()
        self.assertFalse(app.exception)
        case=app.session_state['_case_store'].get_case(cid)
        self.assertEqual(list(case.documents),[rid])
        app.selectbox(key='case_unit_'+cid+'_'+rid).set_value(5).run()
        app.selectbox(key='case_kind_'+cid+'_'+rid+'_5').set_value('party_claim')
        app.button(key='save_case_quote').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['_case_store'].get_case(cid).claims),1)
        other=self.create(app,'模拟案件B')
        self.assertNotEqual(other,cid)
        self.assertFalse(app.session_state['_case_store'].get_case(other).documents)
        self.assertFalse(app.session_state['_case_store'].get_case(other).claims)
        self.assertTrue(app.button(key='case_import_analysis').disabled)

    def test_missing_item_does_not_fill_fact_and_clear_removes_case_documents(self):
        app=self.app();cid=self.create(app)
        app.button(key='case_add_demo').click().run()
        case=app.session_state['_case_store'].get_case(cid);did=next(iter(case.documents))
        app.text_area(key='case_missing_text_'+cid+'_'+did).set_value('模拟问题：原始日志完整性待核实')
        app.button(key='save_case_missing').click().run()
        self.assertFalse(app.exception)
        case=app.session_state['_case_store'].get_case(cid)
        missing=[p for p in case.pending_items if p.kind=='missing_information']
        self.assertEqual(len(missing),1);self.assertIsNone(missing[0].value)
        self.assertFalse(case.reviews)
        app.sidebar.button[2].click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.session_state['_case_store'].list_cases())
        self.assertFalse(app.session_state['records'])

    def test_failed_file_report_is_visible_and_can_be_explicitly_archived(self):
        app=self.app();cid=self.create(app)
        raw=b'SIMULATED CORRUPT FILE';name='模拟损坏.pdf'
        report=parse_document(name,raw).report
        app.session_state['_parse_failures']={'failed-test-id':{'name':name,'data':raw,'report':report}}
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any('读取失败文件的解析报告'==x.label for x in app.expander))
        app.multiselect(key='case_documents_'+cid).set_value(['failed-test-id'])
        app.button(key='attach_documents').click().run()
        self.assertFalse(app.exception)
        case=app.session_state['_case_store'].get_case(cid)
        self.assertEqual(len(case.documents),1)
        self.assertFalse(case.facts)
        self.assertTrue(any(p.kind=='coverage_gap' for p in case.pending_items))

    def test_old_session_record_without_coverage_report_prompts_reread(self):
        from core import extract
        app=self.app()
        path=ROOT/'samples_ai'/'模拟_AI事故材料.docx'
        record=extract(path.name,path.read_bytes())
        for field in ('parse_report','parser_version','original_bytes'):
            record.pop(field,None)
        app.session_state['records']={record['id']:record}
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any('旧解析版本' in x.value for x in app.warning))
