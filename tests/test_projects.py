from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest
from dynamic_topics import discover_topics
from project_state import new_project,collect_project,refresh_project,note_keys,compatible
from project_store import save_project,load_project,ProjectError
from topic_state import merge_topics,undo_topic

class ProjectTests(unittest.TestCase):
    def test_partial_history_merge_then_undo_preserves_membership(self):
        snapshot=self.snapshot()
        snapshot['notes']=[{'标题':f'{theme}{i}','正文':'#'+theme,'笔记ID':f'{j}-{i}'}
                           for j,theme in enumerate(['火山地质','海洋洋流','恒星演化']) for i in range(4)]
        project=self.project(snapshot)
        original=[r['主支柱'] for r in project['state']['editing']['annotations']]
        partial=deepcopy(snapshot);partial['notes']=partial['notes'][:6];partial['captured_at']='next'
        refreshed=refresh_project(project,partial,discover_topics(partial['notes']))
        ids=[project['state']['editing']['annotations'][i]['主题ID'] for i in [0,4]]
        editing=merge_topics(refreshed['state']['editing'],ids,'合并观察')
        merged=collect_project(refreshed,partial,editing,{}, {},'测试项目')
        full=refresh_project(merged,snapshot,discover_topics(snapshot['notes']))
        self.assertEqual([r['主支柱'] for r in full['state']['editing']['annotations'][:8]],['合并观察']*8)
        restored=collect_project(merged,partial,undo_topic(editing),{}, {},'测试项目')
        full=refresh_project(restored,snapshot,discover_topics(snapshot['notes']))
        self.assertEqual([r['主支柱'] for r in full['state']['editing']['annotations']],original)

    def snapshot(self,account='a',ids=True):
        notes=[{'标题':'同标题','正文':f'这是正文{i}','点赞':i,'收藏':1,'评论':0,
                **({'笔记链接':'https://www.xiaohongshu.com/explore/'+str(i).zfill(24)+'?xsec_token=one'} if ids else {})} for i in range(4)]
        return {'name':'测试账号','url':'https://www.xiaohongshu.com/user/profile/'+account*24,'captured_at':'2026-09-29','notes':notes}

    def project(self,snapshot):
        project=new_project(snapshot,discover_topics(snapshot['notes']))
        project['state']['editing']['annotations'][0]['封面观察']='保留人工修改'
        return collect_project(project,snapshot,project['state']['editing'],{'position':'人工定位','analysis_goals':['涨粉']},{},'测试项目')

    def test_roundtrip_restore_and_secret_exclusion(self):
        project=self.project(self.snapshot()); project['snapshot']['cookie']='secret'
        with TemporaryDirectory() as root:
            saved=save_project(project,root); restored=load_project(saved['id'],root)
            self.assertNotIn('cookie',restored['snapshot'])
            self.assertEqual(restored['state']['settings']['position'],'人工定位')
            self.assertEqual(restored['state']['editing']['annotations'][0]['封面观察'],'保留人工修改')
            self.assertNotEqual(save_project(restored,root,as_new=True)['id'],saved['id'])

    def test_metrics_signature_text_partial_and_new(self):
        original=self.snapshot(); project=self.project(original)
        current=deepcopy(original); current['captured_at']='2026-09-30'
        current['notes'][0]['点赞']=500
        current['notes'][0]['笔记链接']=current['notes'][0]['笔记链接'].replace('one','two')
        current['notes'][1]['正文']='改写后的内容'
        current['notes']=current['notes'][:2]+[{'标题':'新增内容','笔记ID':'new-id','点赞':1}]
        refreshed=refresh_project(project,current,discover_topics(current['notes']))
        rows=refreshed['state']['editing']['annotations']
        self.assertEqual(rows[0]['封面观察'],'保留人工修改')
        self.assertFalse(rows[0]['内容变更待复核'])
        self.assertTrue(rows[1]['内容变更待复核'])
        result=collect_project(refreshed,current,refreshed['state']['editing'],{}, {},'测试项目')
        self.assertEqual(len(result['current_ids']),3)
        self.assertEqual(len(result['history']),5)
        self.assertEqual(result['history'][result['current_ids'][0]]['note']['点赞'],500)

    def test_cross_account_no_id_titles_and_manual_scope(self):
        project=self.project(self.snapshot())
        with self.assertRaises(ProjectError): refresh_project(project,self.snapshot('b'),discover_topics(self.snapshot('b')['notes']))
        no_ids=self.snapshot(ids=False)
        self.assertEqual(len(set(note_keys(no_ids))),4)
        excel=deepcopy(no_ids); excel.update(url='Excel：file-one.xlsx / sheet',source_kind='Excel上传')
        other=deepcopy(excel); other['url']='Excel：file-two.xlsx / sheet'
        project=self.project(excel)
        self.assertFalse(compatible(project,other))
        with self.assertRaises(ProjectError): refresh_project(project,other,discover_topics(other['notes']))
        matches={note_keys(other)[0]:note_keys(excel)[0]}
        matched=refresh_project(project,other,discover_topics(other['notes']),matches,confirm_scope=True)
        self.assertEqual(matched['state']['editing']['annotations'][0]['封面观察'],'保留人工修改')

    def test_identical_no_id_rows_require_manual_matching_on_new_snapshot(self):
        snapshot=self.snapshot(ids=False);snapshot['notes']=[deepcopy(snapshot['notes'][0])]*2
        before=note_keys(snapshot)
        self.assertEqual(len(set(before)),2)
        snapshot['captured_at']='later'
        self.assertFalse(set(before)&set(note_keys(snapshot)))

    def test_atomic_failure_corrupt_version_and_path_boundary(self):
        project=self.project(self.snapshot())
        with TemporaryDirectory() as root:
            saved=save_project(project,root); path=Path(root)/(saved['id']+'.json'); before=path.read_bytes()
            changed=deepcopy(saved); changed['name']='未成功保存'
            with patch('project_store.os.replace',side_effect=OSError('disk full')):
                with self.assertRaisesRegex(ProjectError,'上一份'): save_project(changed,root)
            self.assertEqual(path.read_bytes(),before)
            with self.assertRaises(ProjectError): load_project('../outside',root)
            path.write_text('{broken',encoding='utf-8')
            with self.assertRaisesRegex(ProjectError,'损坏'): load_project(saved['id'],root)
            saved['format_version']=99; path.write_text(json.dumps(saved),encoding='utf-8')
            with self.assertRaisesRegex(ProjectError,'版本'): load_project(saved['id'],root)
