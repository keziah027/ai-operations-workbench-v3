import unittest
import pandas as pd
from audience_analysis import audience_candidates,final_audience

class AudienceTests(unittest.TestCase):
    def frame(self,notes):
        return pd.DataFrame([dict({'序号':i+1,'标题':'','正文':'','主支柱':'其他/待确认'},**note) for i,note in enumerate(notes)])

    def test_self_description_past_and_negative_not_audience(self):
        frame=self.frame([{'标题':'学生时代的经历','正文':'我是设计师，这个方法不适合新手。'}])
        self.assertTrue(audience_candidates(frame,'我是设计师').empty)
        self.assertTrue(audience_candidates(frame,'并非面向学生').empty)

    def test_bio_updates_explicit_target_and_notes_work_without_bio(self):
        frame=self.frame([{'标题':'给应届生：如何准备面试','正文':'下班后复盘问题'}])
        result=audience_candidates(frame,'帮助刚入职的新人')
        self.assertIn('刚入职的新人',result['自动假设'].tolist())
        self.assertIn('应届生',audience_candidates(frame,'')['自动假设'].tolist())
        self.assertNotIn('刚入职的新人',audience_candidates(frame,'面向独居者')['自动假设'].tolist())
        self.assertIn('问题/需求候选',result['假设类别'].tolist())
        self.assertIn('使用/生活场景',result['假设类别'].tolist())

    def test_dedupe_signed_links_and_row_locator(self):
        link='https://www.xiaohongshu.com/explore/'+'a'*24
        frame=self.frame([{'标题':'给新手的清单','笔记链接':link+'?xsec_token=a'},
                          {'标题':'给新手的清单','笔记链接':link+'?xsec_token=b'},
                          {'标题':'给新手的清单'}])
        result=audience_candidates(frame,'').iloc[0]
        self.assertEqual(result['命中笔记数'],2)
        self.assertEqual(result['有效文本样本数'],2)
        self.assertIn('row:3',result['例证笔记标识/链接'])

    def test_manual_priority_delete_and_auto_evidence_kept(self):
        auto=audience_candidates(self.frame([{'标题':'给新手的学习清单'}]),'')
        identity=auto.iloc[0]['假设ID']
        result=final_audience(auto,{identity:{'最终假设':'经访谈补充的需求','状态':'人工确认'}})
        self.assertEqual(result.iloc[0]['最终假设'],'经访谈补充的需求')
        self.assertEqual(result.iloc[0]['自动假设'],'新手')
        self.assertEqual(final_audience(auto,{identity:{'状态':'已删除'}}).iloc[0]['状态'],'已删除')
