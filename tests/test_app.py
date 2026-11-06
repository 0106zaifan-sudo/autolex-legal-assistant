from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest

class AppTests(unittest.TestCase):
    def test_load_search_review_export_and_clear(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=30)
        app.secrets['APP_MODE'] = 'local'
        app.run()
        self.assertFalse(app.exception)
        app.sidebar.button[1].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['records']), 6)
        self.assertEqual(app.metric[0].value, '6')
        app.sidebar.button[1].click().run()
        self.assertEqual(len(app.session_state['records']), 6)
        app.text_input[0].set_value('消费者 宣传').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 2)
        app.selectbox[2].set_value('已人工核验')
        app.text_input[1].set_value('演示核验人')
        app.text_area[0].set_value('仅核对模拟原文一致性')
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(sum(len(r['audit']) for r in app.session_state['records'].values()), 1)
        app.text_input[0].set_value('完全不存在关键词').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe), 0)
        app.sidebar.button[2].click().run()
        self.assertEqual(len(app.session_state['records']), 0)
        self.assertFalse(app.exception)

if __name__ == '__main__':
    unittest.main()
