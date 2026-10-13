import unittest
import pandas as pd
from analysis import prepare_data, weekly_pattern, hourly_pattern

class TimePatternsTests(unittest.TestCase):
    def test_empty_missing_dates_and_all_nat(self):
        for df in [pd.DataFrame(), pd.DataFrame({'发布时间':[pd.NaT], '点赞':[8]})]:
            self.assertTrue(weekly_pattern(df).empty)
            self.assertTrue(hourly_pattern(df).empty)

    def test_week_order_exact_denominators_and_edits(self):
        df,_=prepare_data(pd.DataFrame({'标题':['日','一','约','改'],
            '发布时间':['2026-10-11 10:00','2026-10-12 12:30','2026-10-12 13:00','编辑于 2026-10-12 18:00'],
            '点赞':[30,10,'1.2万',999], '收藏':[3,None,4,99], '评论':[1,2,3,99]}))
        weekly=weekly_pattern(df)
        self.assertEqual(weekly['星期'].tolist(),['周一','周日'])
        self.assertEqual(weekly['篇数'].tolist(),[2,1])
        self.assertEqual(weekly['平均点赞'].tolist(),[10,30])
        self.assertEqual(weekly['点赞有效篇数'].tolist(),[1,1])
        self.assertEqual(hourly_pattern(df)['篇数'].sum(),3)

    def test_hour_boundaries_and_date_only_exclusion(self):
        hours=[0,5,6,11,12,13,14,17,18,21,22,23]
        raw=pd.DataFrame({'标题':[str(h) for h in hours]+['只有日期'],
                         '发布时间':[f'2026-10-12 {h:02d}:00' for h in hours]+['2026-10-12'],
                         '点赞':list(range(12))+[1000]})
        df,_=prepare_data(raw)
        result=hourly_pattern(df)
        self.assertEqual(result['篇数'].tolist(),[2]*6)
        self.assertEqual(result['平均点赞'].tolist(),[.5,2.5,4.5,6.5,8.5,10.5])
        self.assertEqual(weekly_pattern(df)['篇数'].tolist(),[13])
        self.assertTrue(result['平均收藏'].isna().all())

    def test_excel_serial_time_and_single_weekday(self):
        df,_=prepare_data(pd.DataFrame({'标题':['时间','日期'],'发布时间':[45000.5,45000.0],'点赞':[12,90]}))
        result=hourly_pattern(df)
        self.assertEqual(result['时段'].tolist(),['中午（12–13时）'])
        self.assertEqual(result['平均点赞'].tolist(),[12])
        self.assertEqual(len(weekly_pattern(df)),1)
