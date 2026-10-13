import unittest
import pandas as pd
from analysis import prepare_data, performance_tiers

class PerformanceTiersTests(unittest.TestCase):
    def test_empty_all_nan_and_fewer_than_four(self):
        for values in [[],[None,None],[0,1,2,None]]:
            r=performance_tiers(pd.DataFrame({'点赞':values}))
            self.assertTrue(r['summary'].empty)
            self.assertTrue(pd.isna(r['viral_rate']))
            self.assertEqual(r['status'],'样本不足')

    def test_exact_precision_median_and_denominators(self):
        df,_=prepare_data(pd.DataFrame({'标题':list('abcdefgh'),
            '点赞':[0,10,20,100,'1.2万','5千+',None,30],
            '收藏':[0,20,40,None,50,60,70,80], '评论':[0,1,2,3,4,5,6,7]}))
        r=performance_tiers(df)
        self.assertEqual(r['valid_count'],5)
        self.assertEqual(r['median'],20)
        self.assertEqual(r['p25'],10)
        self.assertEqual(r['p75'],30)
        self.assertEqual(r['viral_rate'],.4)
        self.assertEqual(r['labels'].tolist(),['长尾','中坚','中坚','爆款','未参与','未参与','未参与','爆款'])
        high=r['summary'].set_index('表现层级').loc['爆款']
        self.assertEqual(high['平均收藏'],80)
        self.assertEqual(high['收藏有效篇数'],1)
        self.assertAlmostEqual(r['summary']['占比'].sum(),1)

    def test_uniform_or_collapsed_quartiles(self):
        for values in [[0]*4,[10]*6,[10]*7+[100]]:
            r=performance_tiers(pd.DataFrame({'点赞':values}))
            self.assertEqual(r['status'],'四分位重合')
            self.assertEqual(r['summary']['表现层级'].tolist(),['中坚'])
            self.assertEqual(r['summary']['占比'].tolist(),[1.])
            self.assertTrue(pd.isna(r['viral_rate']))

    def test_ties_at_upper_threshold_and_no_mutation(self):
        df=pd.DataFrame({'点赞':[1,2,3,3,3,3], '收藏':[None]*6})
        before=df.copy(deep=True);r=performance_tiers(df)
        self.assertEqual(r['viral_rate'],4/6)
        pd.testing.assert_frame_equal(before,df)
        self.assertTrue(r['summary']['平均收藏'].isna().all())
