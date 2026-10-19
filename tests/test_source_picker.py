"""Exercise the real app's selection routes, availability, and return state."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

APP = Path(__file__).parents[1] / 'app.py'


class SourcePickerTests(unittest.TestCase):
    def app(self):
        app = AppTest.from_file(str(APP), default_timeout=60).run()
        return app.button('cover-start').click().run()

    def clean(self, app):
        self.assertFalse(app.exception, app.exception)

    @patch.dict(os.environ, {'APP_MODE': 'public'})
    def test_public_routes_keep_real_availability_messages(self):
        app = self.app()
        self.clean(app)
        self.assertEqual([b.label for b in app.button if b.key and b.key.startswith('source-card-')],
                         ['Excel 文件', '真实账号案例', '公开账号', '我的账号后台'])
        for index, expected in [(2, '此功能需要本机浏览器登录'), (3, '后台同步需要账号所有者在本机浏览器登录')]:
            app.button(f'source-card-{index}').click().run()
            self.clean(app)
            self.assertTrue(any(expected in message.value for message in app.info))
            self.assertFalse(app.session_state['source-picker-open'])
            app.button('source-back').click().run()
            self.assertTrue(app.session_state['source-picker-open'])
        app.button('source-card-0').click().run()
        self.clean(app)
        self.assertTrue(any(item.label == '选择演示账号类型' for item in app.selectbox))

    @patch.dict(os.environ, {'APP_MODE': 'public'})
    @patch('real_cases.list_cases', return_value=[])
    def test_missing_cases_show_truthful_empty_state(self, _cases):
        app = self.app()
        app.button('source-card-1').click().run()
        self.clean(app)
        self.assertTrue(any('暂无可用的真实案例快照' in message.value for message in app.info))
        self.assertFalse(any(b.label == '加载真实账号案例' for b in app.button))

    @patch.dict(os.environ, {'APP_MODE': 'public'})
    def test_non_default_case_and_analysis_session_survive_return(self):
        app = self.app()
        app.button('source-card-1').click().run()
        choice = app.selectbox('source-case-choice')
        from real_cases import list_cases
        selected = list_cases()[1]['id']
        choice.select(selected).run()
        case_id = app.session_state['source-case-choice']
        app.session_state['active-real-case-id'] = case_id
        app.session_state['editor-state-regression-sentinel'] = {'annotations': ['retained']}
        app.button('source-back').click().run()
        app.button('source-card-1').click().run()
        self.clean(app)
        self.assertEqual(app.session_state['source-case-choice'], case_id)
        self.assertEqual(app.session_state['active-real-case-id'], case_id)
        self.assertEqual(app.session_state['editor-state-regression-sentinel'], {'annotations': ['retained']})


if __name__ == '__main__':
    unittest.main()
