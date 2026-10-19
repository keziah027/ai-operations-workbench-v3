import unittest
import pandas as pd
from glass_ui import efficiency_data, observations, trend_data, interaction_ratios, content_formats, dashboard_topics
from pathlib import Path
import json
from unittest.mock import patch
from note_schema import normalize_notes
from smart_topics import discover_smart_topics


class DashboardDataTests(unittest.TestCase):
    def test_rates_are_mean_of_valid_per_note_values(self):
        frame = pd.DataFrame({'观看': [100, 200, 0, None], '收藏': [10, 10, 99, 20], '评论': [1, 4, 99, 20]})
        rates = efficiency_data(frame)
        self.assertAlmostEqual(rates['收藏率'].mean(), .075)
        self.assertAlmostEqual(rates['评论率'].mean(), .015)
        self.assertTrue(rates.iloc[2:].isna().all().all())

    def test_missing_views_never_substitutes_likes(self):
        frame = pd.DataFrame({'点赞': [100], '收藏': [30], '评论': [20]})
        self.assertTrue(efficiency_data(frame).isna().all().all())

    def test_scope_and_precision_must_match(self):
        frame = pd.DataFrame({'观看': [100, 100, 100], '收藏': [10, 10, 10], '评论': [1, 1, 1],
                              '观看精度': ['精确', '近似', '精确'], '收藏精度': ['精确'] * 3,
                              '观看统计周期': ['7天'] * 3, '收藏统计周期': ['7天', '7天', '30天']})
        rates = efficiency_data(frame)
        self.assertEqual(rates['收藏率'].count(), 1)
        self.assertAlmostEqual(rates['收藏率'].iloc[0], .1)
        self.assertEqual(rates['评论率'].count(), 0)  # only denominator has a declared period

    def test_observations_use_actual_groups_and_values(self):
        frame = pd.DataFrame({'标题': ['甲1', '甲2', '乙1', '乙2'], '内容主题': ['甲', '甲', '乙', '乙'],
                              '点赞': [10, 20, 50, 70], '收藏': [1, 2, 3, 10], '评论': [1, 2, 3, 4],
                              '观看': [100] * 4})
        notes = observations(frame, efficiency_data(frame))
        self.assertIn('「乙」平均点赞最高，为 60', notes[0])
        self.assertIn('10.0%', notes[1])
        self.assertIn('4.0%', notes[1])
        self.assertIn('4 条', notes[2])

    def test_missing_metrics_do_not_invent_observations(self):
        frame = pd.DataFrame({'标题': ['文本'], '点赞': [float('nan')], '收藏': [float('nan')], '评论': [float('nan')]})
        self.assertEqual(observations(frame, efficiency_data(frame)), [])

    def test_case_uses_reviewed_broad_themes_and_real_ratios(self):
        snapshot = json.loads((Path(__file__).parents[1] / 'case_studies/telado-2026-10-12.json').read_text(encoding='utf-8'))
        snapshot['is_case_study'] = True
        frame = pd.DataFrame(normalize_notes(snapshot['notes']))
        with patch('content_ui_v2.cached_topics', side_effect=discover_smart_topics):
            result = dashboard_topics(frame, snapshot)
        self.assertEqual(set(result['内容支柱']), {'新品预告与上新', '产品场景与玩法', '互动活动与结果', '产品合集与工具'})
        self.assertEqual(len(result), 18)
        trend = trend_data(frame, '点赞')
        self.assertFalse(trend.empty)
        self.assertEqual(trend['发布日期'].min(), pd.Timestamp('2026-08-29'))
        self.assertEqual(trend['发布日期'].max(), pd.Timestamp('2026-10-12'))
        self.assertTrue(trend['日期性质'].str.contains('编辑日期').any())
        self.assertEqual(len(trend_data(frame, '点赞', False)), 18)
        self.assertTrue(efficiency_data(frame).isna().all().all())
        ratios = interaction_ratios(frame)
        self.assertEqual(ratios['藏赞比'].count(), 18)
        self.assertAlmostEqual(ratios['藏赞比'].iloc[0], 133/583)
        self.assertEqual(content_formats(frame).value_counts().to_dict(), {'图文': 11, '视频': 7})
        self.assertTrue(frame['内容形式核验日期'].eq('2026-10-18').all())

    def test_final_manual_theme_wins_over_automatic_theme(self):
        snapshot = {'notes': [{'标题': '甲'}, {'标题': '乙'}]}
        frame = pd.DataFrame(snapshot['notes'])
        with patch('content_ui_v2.cached_topics', return_value={'assignments': ['自动甲', '自动乙']}), patch('content_ui_v2.analysis_key', return_value='test'), patch('glass_ui.st.session_state', {'editor-state-test': {'annotations': [{'主支柱': '合并主题'}, {'主支柱': '合并主题'}]}}):
            self.assertEqual(dashboard_topics(frame, snapshot)['内容支柱'].tolist(), ['合并主题', '合并主题'])

    def test_formats_use_explicit_aliases_and_keep_missing_unknown(self):
        frame = pd.DataFrame([{'图文/视频': '', '内容形式': '图片'}, {'内容类型': 'video'},
                              {'图文/视频': '未分类', '笔记类型': '视频笔记'}, {'标题': '这是一篇视频教程'}, {'内容形式': '图文笔记'}])
        self.assertEqual(content_formats(frame).tolist(), ['图文', '视频', '视频', '', '图文'])

    def test_trend_groups_dates_and_preserves_sample_sequence_gaps(self):
        frame = pd.DataFrame({'标题': ['甲', '乙', '丙'], '发布时间': ['2026-10-01', '2026-10-01', None], '点赞': [10, 20, 30], '点赞精度': ['精确', '近似', '精确']})
        self.assertEqual(trend_data(frame, '点赞')['点赞'].tolist(), [10])
        self.assertEqual(trend_data(frame, '点赞', False)['样本序号'].tolist(), [1, 3])

    def test_ratios_exclude_zero_denominator_and_mismatched_scopes(self):
        frame = pd.DataFrame({'点赞': [0, 100, 100], '收藏': [10, 20, 30], '评论': [1, 2, 3],
                              '点赞统计周期': ['7天'] * 3, '收藏统计周期': ['7天', '30天', '7天']})
        ratios = interaction_ratios(frame)
        self.assertEqual(ratios['藏赞比'].count(), 1)
        self.assertAlmostEqual(ratios['藏赞比'].iloc[2], .3)

    def test_page_dates_group_values_and_keep_date_kind(self):
        frame = pd.DataFrame({'发布时间': [None] * 3, '页面日期': ['2026-10-01', '2026-10-01', None],
                              '页面日期性质': ['编辑日期', '发布日期（页面显示）', ''], '点赞': [10, 30, 999]})
        trend = trend_data(frame, '点赞')
        self.assertEqual(trend['点赞'].tolist(), [20])
        self.assertIn('编辑日期', trend.iloc[0]['日期性质'])
        self.assertIn('发布日期（页面显示）', trend.iloc[0]['日期性质'])

    def test_publication_dates_take_priority_without_mixing_page_dates(self):
        frame = pd.DataFrame({'发布时间': ['2025-12-31', None], '页面日期': ['2026-10-01', '2026-10-02'], '点赞': [10, 99]})
        trend = trend_data(frame, '点赞')
        self.assertEqual(trend['发布日期'].tolist(), [pd.Timestamp('2025-12-31')])
        self.assertEqual(trend['点赞'].tolist(), [10])
        self.assertNotIn('日期性质', trend)
