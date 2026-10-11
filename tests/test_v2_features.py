import unittest
from content_features import detect_features
from content_analysis import build_annotations, build_detail, pillar_summary, high_interaction


class FeatureTests(unittest.TestCase):
    def test_extended_features_have_evidence(self):
        examples = {'身份标签': 'INFP打工人', '痛点表达': '内耗怎么办', '结果导向': '拿到面试机会',
                    '情绪表达': '今天好开心', '反常识': '你以为努力就够了', '故事型': '有一次我迷路了',
                    '经历型': '我曾经转行', '干货清单': '书单合集', '强观点': '我认为别再讨好',
                    '人群指向': '写给应届生', '场景化表达': '下班以后'}
        for label, title in examples.items():
            self.assertIn(label, detect_features(title))
            self.assertIn('标题', detect_features(title)[label])
        self.assertEqual(detect_features(''), {})

    def test_rates_use_paired_valid_notes_and_zero_is_excluded(self):
        notes = [{'标题': '共同主题', '点赞': like, '收藏': save, '评论': comment}
                 for like, save, comment in [(10, 2, 1), (100, 50, 20), (0, 4, 3), (None, 90, 5), (10, None, None)]]
        frame = build_detail(notes, build_annotations(notes))
        group = pillar_summary(frame).iloc[0]
        self.assertAlmostEqual(group['藏赞比'], .35)
        self.assertAlmostEqual(group['评赞比'], .15)
        self.assertEqual(group['藏赞比有效篇数'], 2)
        self.assertEqual(group['篇数'], 5)

    def test_missing_bodies_are_not_feature_absence(self):
        notes = [{'标题': '主题'+str(i), '点赞': i, '收藏': i, '评论': i,
                  '正文': '内耗焦虑' if i in [0, 1, 9, 10] else ''} for i in range(12)]
        frame = build_detail(notes, build_annotations(notes))
        comparison = high_interaction(frame, '点赞')[2]
        pain = comparison[comparison['特征'].eq('正文：痛点表达')].iloc[0]
        self.assertEqual(pain['高互动组有效篇数'], 2)
        self.assertEqual(pain['其余组有效篇数'], 2)
        self.assertEqual(pain['占比差（百分点）'], 0)


if __name__ == '__main__':
    unittest.main()
