import unittest
import pandas as pd
from content_analysis import build_annotations,build_detail,pillar_summary
from account_diagnosis import diagnose
from diagnosis_evidence import metric_diagnosis,INSUFFICIENT

class DiagnosticEvidenceTests(unittest.TestCase):
    def frame(self):
        notes=[{'标题':f'记录{i}','正文':'给新手的复盘方法','点赞':10,'收藏':i+1,'评论':i,
                '发布时间':'2026-09-02','图文/视频':'图文'} for i in range(8)]
        labels=build_annotations(notes)
        labels['主支柱']=['甲主题']*4+['乙主题']*4
        return build_detail(notes,labels)

    def test_numbers_recomputable_with_control_and_median(self):
        frame=self.frame()
        result=metric_diagnosis(frame,'藏赞比')
        self.assertEqual(result['甲组'],'乙主题')
        self.assertAlmostEqual(result['甲组均值'],.65)
        self.assertAlmostEqual(result['乙组中位数'],.25)
        self.assertAlmostEqual(result['均值差'],.4)
        self.assertIn('同首发月份、同内容形式',result['样本范围与有效数量'])
        self.assertIn('各安排3篇',result['下一步动作'])
        self.assertIn('第8篇',result['证据笔记'])

    def test_missing_zero_single_group_small_equal_degrade(self):
        frame=self.frame()
        self.assertEqual(metric_diagnosis(frame.head(5),'藏赞比')['观察结果'],INSUFFICIENT)
        frame['主支柱']='合并主题'
        self.assertEqual(metric_diagnosis(frame,'藏赞比')['观察结果'],INSUFFICIENT)
        frame=self.frame(); frame['藏赞比']=None
        self.assertEqual(metric_diagnosis(frame,'藏赞比')['观察结果'],INSUFFICIENT)
        frame=self.frame(); frame['藏赞比']=1
        self.assertIn('未观察到差异',metric_diagnosis(frame,'藏赞比')['观察结果'])
        self.assertNotIn('各安排',metric_diagnosis(frame,'藏赞比')['下一步动作'])

    def test_manual_reclassification_changes_evidence(self):
        frame=self.frame(); before=metric_diagnosis(frame,'评赞比')
        frame.loc[[0,7],'主支柱']=['乙主题','甲主题']
        after=metric_diagnosis(frame,'评赞比')
        self.assertNotEqual(before['均值差'],after['均值差'])
        result=diagnose(frame,{'identity':'个人创作者','domains':[],'goals':[],
                              'analysis_goals':['评论互动','涨粉','商品承接']},pillar_summary(frame))
        self.assertIn('评赞比的支柱比较',result['诊断主题'].tolist())
        missing=result[result['诊断主题'].eq('每千次观看涨粉的支柱比较')].iloc[0]
        self.assertEqual(missing['观察结果'],INSUFFICIENT)
        self.assertIn('商品效果数据缺口',result['诊断主题'].tolist())
