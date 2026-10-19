"""Synthetic test fixtures only. No real account is claimed by these tests."""
from copy import deepcopy
from unittest.mock import patch
import unittest
from streamlit.testing.v1 import AppTest
from pathlib import Path
from real_cases import validate_case, case_snapshot, list_cases


def fixture():
    return dict(id='synthetic-test-only', name='虚构测试夹具（不公开展示）',
                data_kind='real_public_snapshot',
                url='https://www.xiaohongshu.com/user/profile/'+'1'*24,
                captured_at='2026-10-12T12:00:00+08:00', scope='仅为单元测试构造的 3 条记录',
                collection_method='synthetic test fixture', bio='个人创作者，分享职场知识',
                profile_text='测试夹具，无实际账号数据',
                notes=[{'标题':'虚构测试笔记'+str(i), '笔记链接':'https://www.xiaohongshu.com/explore/'+str(i)*24,
                        '点赞':i*10, '收藏':None, '评论':None} for i in range(1,4)])


class CaseTests(unittest.TestCase):
    def test_page_dates_have_evidence_without_inventing_first_publication(self):
        from datetime import date
        count = 0
        for case in list_cases():
            for note in case['notes']:
                date.fromisoformat(note['页面日期'])
                self.assertTrue(note['页面日期原文'])
                self.assertTrue(note['页面日期采集时间'])
                self.assertTrue(note['页面日期依据'])
                self.assertIsNone(note.get('发布时间'))
                if '编辑' in note['页面日期原文']:
                    self.assertEqual(note['页面日期性质'], '编辑日期')
                count += 1
        self.assertEqual(count, 72)

    def test_media_review_matches_verified_counts_and_preserves_unknown(self):
        from collections import Counter
        expected = {'telado-2026-10-12': {'图文':11, '视频':7},
                    'xiaolin-2026-10-12': {'视频':17, '':1},
                    'fangqi-2026-10-12': {'图文':1, '视频':17},
                    'jiangchenglan-2026-10-19': {'图文':4, '视频':14}}
        total = 0
        for case in list_cases():
            self.assertEqual(dict(Counter(n.get('内容形式', '') for n in case['notes'])), expected[case['id']])
            for note in case['notes']:
                if note.get('内容形式'):
                    total += 1
                    self.assertEqual(note['内容形式'], note['图文/视频'])
                    self.assertEqual(note['内容形式核验日期'], '2026-10-19' if case['id']=='jiangchenglan-2026-10-19' else '2026-10-18')
                    self.assertIn('data-type=', note['内容形式依据'])
                else:
                    self.assertIn('404', note['内容形式核验状态'])
            self.assertTrue(case['captured_at'].startswith('2026-10-19' if case['id']=='jiangchenglan-2026-10-19' else '2026-10-12'))
        self.assertEqual(total, 71)

    def test_published_case_keeps_missing_data_and_provenance(self):
        cases=list_cases()
        self.assertEqual(len(cases),4)
        case=next(case for case in cases if case['id']=='telado-2026-10-12')
        snapshot=case_snapshot(case)
        self.assertEqual(len(snapshot['notes']),18)
        self.assertEqual([sum(n[m] for n in snapshot['notes']) for m in ('点赞','收藏','评论')],[10541,2537,3239])
        from note_schema import normalize_notes
        for note in normalize_notes(snapshot['notes']):
            self.assertEqual(note['正文'],'')
            self.assertTrue(note['内容概述（整理）'])
            for metric in ('曝光','观看','涨粉'):
                self.assertIsNone(note[metric])
            self.assertIsNone(note['发布时间'])
            self.assertNotIn('?',note['笔记链接'])
        for case in cases:
            for note in normalize_notes(case['notes']):
                for metric in ('点赞','收藏','评论'):
                    if note[metric+'精度'] in ('近似','下界'):
                        self.assertIsNone(note[metric])
                        self.assertTrue(note[metric+'原文'])
        replacement=next(case for case in cases if case['id']=='jiangchenglan-2026-10-19')
        self.assertTrue(replacement['exclude_pinned'])
        self.assertEqual(len(replacement['notes']),18)
        self.assertTrue(all(note['是否置顶'] is False for note in replacement['notes']))

    def test_requires_provenance_and_rejects_credentials(self):
        source=fixture()
        snapshot=case_snapshot(source)
        self.assertFalse(snapshot['is_demo'])
        self.assertTrue(snapshot['is_case_study'])
        self.assertIsNone(snapshot['notes'][0]['收藏'])
        self.assertNotIn('数据性质', source['notes'][0])
        for key in ['url','captured_at','scope','collection_method']:
            invalid=deepcopy(source); invalid.pop(key)
            with self.assertRaises(ValueError): validate_case(invalid)
        invalid=deepcopy(source); invalid['cookie']='test-placeholder'
        with self.assertRaises(ValueError): validate_case(invalid)
        invalid=deepcopy(source); invalid['notes'][0]['笔记链接']+='?xsec_token=test-placeholder'
        with self.assertRaises(ValueError): validate_case(invalid)

    def test_case_flows_through_existing_analysis(self):
        with patch('real_cases.list_cases', return_value=[fixture()]):
            app=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=90).run()
            self.assertFalse(app.exception)
            app.button('cover-start').click().run()
            app.button('source-card-1').click().run()
            next(b for b in app.button if b.label=='加载真实账号案例').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len([t for t in app.tabs if '账号画像' in t.label]),1)
            self.assertTrue(any(b.label=='导出V3数据与分析（Excel）' for b in app.get('download_button')))


if __name__=='__main__': unittest.main()
