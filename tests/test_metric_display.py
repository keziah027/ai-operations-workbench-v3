import unittest
from copy import deepcopy
import pandas as pd
from note_schema import normalize_notes
from metric_display import metric_text, display_values, display_total, display_ranking, display_table, export_display


class MetricDisplayTests(unittest.TestCase):
    def test_raw_abbreviations_and_missing_values_remain_distinct(self):
        frame=pd.DataFrame(normalize_notes([{'点赞':'10万+'},{'点赞':'4.1万'},{'点赞':1200},{'点赞':None}]))
        before=deepcopy(frame)
        self.assertEqual(display_table(frame)['点赞'].tolist(),['10万+','4.1万','1,200','—'])
        self.assertEqual(display_values(frame,'点赞').dropna().tolist(),[100000,41000,1200])
        self.assertEqual(display_total(frame,'点赞'),'约14.22万+')
        self.assertEqual(export_display(frame)['点赞'].iloc[0],'10万+')
        pd.testing.assert_frame_equal(frame,before)

    def test_capped_values_share_a_group_and_keep_source_order(self):
        frame=pd.DataFrame(normalize_notes([{'标题':'甲','点赞':'10万+'},{'标题':'乙','点赞':'10万+'},{'标题':'丙','点赞':'9.6万'}]))
        ranked=display_ranking(frame,'点赞')
        self.assertEqual(ranked['_显示分组'].tolist(),[1,1,3])
        self.assertEqual(ranked['标题'].tolist(),['甲','乙','丙'])
        self.assertTrue(frame['点赞'].isna().all())

    def test_zero_is_not_missing_and_all_lower_bounds_are_labelled(self):
        self.assertEqual(metric_text({'点赞':0},'点赞'),'0')
        frame=pd.DataFrame(normalize_notes([{'点赞':'10万+'},{'点赞':'10万+'}]))
        self.assertEqual(display_total(frame,'点赞'),'≥20万')
        self.assertEqual(display_total(frame,'点赞',mean=True),'≥10万')


if __name__=='__main__': unittest.main()
