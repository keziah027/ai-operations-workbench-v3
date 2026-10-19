from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
from unittest.mock import patch
import unittest
from streamlit.testing.v1 import AppTest
import excel_export
from project_store import list_projects,load_project
from cross_account_cases import CASES,case_notes

class ProjectUITests(unittest.TestCase):
    def test_save_new_session_restore_and_partial_refresh(self):
        captured={}; original=excel_export.public_workbook
        def export(snapshot,analysis):
            captured.update(snapshot=snapshot,analysis=analysis)
            return original(snapshot,analysis)
        def widget(app,kind,label): return next(item for item in getattr(app,kind) if item.label==label)
        source=Path(__file__).parents[1]/'app.py'
        snapshot={'name':'测试存档账号','url':'https://www.xiaohongshu.com/user/profile/'+'c'*24,
                  'bio':'帮助职场新人','profile_text':'测试资料','notes':case_notes(CASES[2]),'captured_at':'2026-09-29T10:00:00','stop_reason':'测试'}
        with TemporaryDirectory() as root,patch('project_ui.STORE_ROOT',Path(root)),patch('excel_export.public_workbook',side_effect=export):
            app=AppTest.from_file(str(source),default_timeout=60).run()
            app.button('cover-start').click().run()
            app.session_state['public_snapshot']={'input':snapshot['url'],'data':snapshot}
            app.radio[0].set_value('公开账号').run()
            widget(app,'text_area','你的账号定位结论').set_value('保存后应恢复的定位').run()
            widget(app,'multiselect','本次分析重点（可多选）').set_value(['收藏沉淀']).run()
            widget(app,'button','保存项目').click().run()
            self.assertFalse(app.exception,app.exception)
            entries=list_projects(root); self.assertEqual(len(entries),1)
            stored=load_project(entries[0]['id'],root)
            self.assertEqual(stored['state']['settings']['position'],'保存后应恢复的定位')
            fresh=AppTest.from_file(str(source),default_timeout=60).run()
            fresh.button('cover-start').click().run()
            widget(fresh,'selectbox','选择已保存项目').set_value(entries[0]['id']).run()
            widget(fresh,'button','打开项目').click().run()
            self.assertFalse(fresh.exception,fresh.exception)
            self.assertEqual(widget(fresh,'text_area','你的账号定位结论').value,'保存后应恢复的定位')
            self.assertEqual(widget(fresh,'multiselect','本次分析重点（可多选）').value,['收藏沉淀'])
            self.assertFalse(fresh.session_state['project_dirty'])
            widget(fresh,'button','返回数据入口，读取或上传新数据').click().run()
            updated=deepcopy(snapshot); updated['captured_at']='2026-09-29T11:00:00'; updated['notes']=updated['notes'][:3]
            updated['notes'][0]['点赞']=999
            fresh.session_state['public_snapshot']={'input':updated['url'],'data':updated}
            fresh.radio[0].set_value('公开账号').run()
            self.assertFalse(fresh.exception,fresh.exception)
            self.assertEqual(widget(fresh,'text_area','你的账号定位结论').value,'保存后应恢复的定位')
            self.assertEqual(len(captured['analysis']['detail']),3)
            self.assertEqual(captured['analysis']['detail'].iloc[0]['点赞'],999)
            widget(fresh,'button','保存项目').click().run()
            reloaded=load_project(entries[0]['id'],root)
            self.assertEqual(len(reloaded['history']),8)
            self.assertEqual(len(reloaded['current_ids']),3)
