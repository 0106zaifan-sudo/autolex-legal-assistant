import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from ai_ui import demo_analysis
from security import hash_password

ROOT=Path(__file__).resolve().parents[1]

class UIAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password='simulation-access-password'
        cls.password_hash=hash_password(cls.password)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def app(self, **secrets):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30)
        for k,v in secrets.items():app.secrets[k]=v
        app.secrets['AI_LIMIT_DB']=str(Path(self.tmp.name)/'limits.sqlite3')
        return app

    def test_public_without_access_config_is_locked(self):
        app=self.app().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('应用已锁定' in e.value for e in app.error))
        self.assertEqual(len(app.get('file_uploader')),0)
        self.assertNotIn('records',app.session_state)

    def test_wrong_login_correct_login_and_logout_clear_data(self):
        app=self.app(APP_PASSWORD_HASH=self.password_hash).run()
        self.assertEqual(len(app.get('file_uploader')),0)
        app.text_input(key='_login_password').set_value('wrong')
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('不正确' in e.value for e in app.error))
        app.text_input(key='_login_password').set_value(self.password)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get('file_uploader')),1)
        self.assertNotIn('_login_password',app.session_state)
        app.session_state['records']={'private':{'not_displayed':'test'}}
        app.button(key='logout').click().run()
        self.assertFalse(app.exception)
        self.assertNotIn('records',app.session_state)
        self.assertNotIn('_auth_principal',app.session_state)

    def test_local_no_key_ai_disabled_but_demo_works(self):
        with patch('ai_ui.analyze_record') as analyze:
            app=self.app(APP_MODE='local').run()
            self.assertFalse(app.exception)
            self.assertTrue(app.button(key='run_ai').disabled)
            self.assertTrue(any('OPENAI_API_KEY' in x.value for x in app.info))
            app.button(key='show_ai_demo').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('离线模拟结果' in x.value for x in app.info))
            analyze.assert_not_called()
        result=demo_analysis(ROOT)
        self.assertIn('非 AI 调用',result['mode'])
        self.assertEqual(len(result['sections']['timeline']),3)

    def test_authenticated_key_and_consent_are_required(self):
        app=self.app(APP_PASSWORD_HASH=self.password_hash,OPENAI_API_KEY='mock-key-not-real',AI_SINGLE_INSTANCE=True).run()
        app.text_input(key='_login_password').set_value(self.password)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        app.sidebar.button[2].click().run() # logout is sidebar[0], upload[1], samples[2]
        self.assertEqual(len(app.session_state['records']),6)
        self.assertTrue(app.button(key='run_ai').disabled)
        app.checkbox(key='ai_consent').check().run()
        self.assertFalse(app.button(key='run_ai').disabled)
        choices = app.selectbox[0].options
        if len(choices) > 1:
            # 更换资料后不得沿用之前的发送许可。
            values = list(app.session_state['records'])
            current = app.selectbox[0].value
            other = next(v for v in values if v != current)
            app.selectbox[0].set_value(other).run()
            self.assertFalse(app.checkbox(key='ai_consent').value)
            self.assertTrue(app.button(key='run_ai').disabled)
            app.checkbox(key='ai_consent').check().run()
        result=demo_analysis(ROOT);result['mode']='测试模拟 SDK 响应'
        with patch('ai_ui.analyze_record',return_value=result) as analyze:
            app.button(key='run_ai').click().run()
            self.assertFalse(app.exception)
            analyze.assert_called_once()
            self.assertIn('_ai_result',app.session_state)
        with patch('ai_ui.analyze_record',side_effect=RuntimeError('SECRET-DO-NOT-DISPLAY')):
            app.button(key='run_ai').click().run()
            self.assertFalse(app.exception)
            self.assertNotIn('_ai_result',app.session_state)
            self.assertTrue(any('分析暂不可用' in x.value for x in app.error))
            self.assertFalse(any('SECRET' in x.value for x in app.error))

    def test_rotating_password_invalidates_existing_session(self):
        app=self.app(APP_PASSWORD_HASH=self.password_hash).run()
        app.text_input(key='_login_password').set_value(self.password)
        app.button[0].click().run()
        app.secrets['APP_PASSWORD_HASH']=hash_password('new-simulation-password')
        app.run()
        self.assertFalse(app.exception)
        self.assertNotIn('records',app.session_state)
        self.assertNotIn('_auth_principal',app.session_state)

    def test_invalid_secrets_fail_closed_without_traceback(self):
        app=self.app(APP_MODE='not-a-mode',OPENAI_API_KEY='mock-key-not-real').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('应用已锁定' in e.value for e in app.error))
        self.assertEqual(len(app.get('file_uploader')),0)
