import unittest
import pandas as pd
from pandas.testing import assert_frame_equal
from performance import backend_trends
from unittest.mock import patch

class BackendTrendTests(unittest.TestCase):
    def test_partial_zero_missing_precision_and_no_mutation(self):
        df=pd.DataFrame({'发布时间':['2026-10-01']*5,'曝光':[100,0,None,100,100],
            '观看':[200,20,20,20,20],'涨粉':[2,0,None,4,1],
            '观看精度':['精确','精确','精确','近似','下界']})
        original=df.copy(deep=True); result=backend_trends(df)
        self.assertEqual(result['观看曝光比']['观看曝光比'].tolist(),[2])
        self.assertEqual(result['涨粉效率']['涨粉效率'].tolist(),[10,0])
        assert_frame_equal(df,original)

    def test_empty_all_missing_and_zero_views(self):
        for df in [pd.DataFrame(),pd.DataFrame({'发布时间':[None],'曝光':[None]}),
                   pd.DataFrame({'发布时间':['2026-01-01'],'观看':[0],'涨粉':[1]})]:
            result=backend_trends(df)
            self.assertTrue(all(part.empty for part in result.values()))

    def test_percent_original_units_and_edited_dates(self):
        df=pd.DataFrame({'发布时间':['2026-10-01','2026-10-02','编辑于2026-10-03','2026-10-04','2026-10-05','2026-10-06'],
                         '视频完播率':['42.5%',50,'70%','约30%','101%','—']})
        self.assertEqual(backend_trends(df)['视频完播率']['视频完播率'].tolist(),[42.5,50])

    def test_extreme_single_and_scope_mismatch(self):
        df=pd.DataFrame({'发布时间':['2026-01-01'],'曝光':[1],'观看':[10**12],'涨粉':[1],
            '曝光统计周期':['本周'],'观看统计周期':['累计']})
        result=backend_trends(df)
        self.assertTrue(result['观看曝光比'].empty)
        self.assertTrue(result['涨粉效率'].empty)
        df=df.drop(columns=['曝光统计周期','观看统计周期'])
        self.assertEqual(backend_trends(df)['观看曝光比'].iloc[0]['观看曝光比'],10**12)

    def test_ui_three_charts_and_missing_guidance(self):
        from app import render_backend_trends
        with patch('app.st') as ui:
            render_backend_trends(pd.DataFrame({'发布时间':['2026-01-01'],'曝光':[100],'观看':[20],'涨粉':[1],'视频完播率':['42%']}))
            self.assertEqual(ui.line_chart.call_count,3)
            ui.info.assert_not_called()
        with patch('app.st') as ui:
            render_backend_trends(pd.DataFrame())
            ui.line_chart.assert_not_called(); self.assertEqual(ui.info.call_count,3)
