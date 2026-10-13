import unittest
import pandas as pd
from analysis import prepare_data, account_comparison

class AccountComparisonTests(unittest.TestCase):
    def test_multiple_accounts_ratios_are_mean_of_valid_rows(self):
        raw=pd.DataFrame({'标题':list('abcdefghij'), '账号名称':['甲']*4+['乙']*4+[None,''],
                         '点赞':[0,10,20,30,100,200,300,'1.2万',999,888],
                         '收藏':[9,20,10,None,100,50,0,100,1,1], '评论':[1]*10})
        df,_=prepare_data(raw);r=account_comparison(df).set_index('账号')
        self.assertEqual(r.index.tolist(),['甲','乙'])
        self.assertEqual(r.loc['甲','篇数'],4)
        self.assertEqual(r.loc['甲','平均点赞'],15)
        self.assertEqual(r.loc['甲','藏赞比'],1.25)
        self.assertEqual(r.loc['甲','藏赞比有效篇数'],2)
        self.assertEqual(r.loc['甲','爆款率'],.25)
        self.assertTrue(pd.isna(r.loc['乙','爆款率']))
        self.assertEqual(r.loc['乙','点赞有效篇数'],3)
        self.assertEqual(len(df),10)

    def test_single_missing_and_empty_accounts_hidden(self):
        for df in [pd.DataFrame(),pd.DataFrame({'账号名称':['甲',None]}),pd.DataFrame({'账号名称':['甲','甲']})]:
            self.assertTrue(account_comparison(df).empty)

    def test_all_missing_keeps_counts_and_blank_metrics(self):
        r=account_comparison(pd.DataFrame({'账号名称':['甲','乙'],'点赞':[None,None]}))
        self.assertEqual(r['篇数'].tolist(),[1,1])
        self.assertTrue(r[['平均点赞','平均收藏','平均评论','藏赞比','评赞比','爆款率']].isna().all().all())
