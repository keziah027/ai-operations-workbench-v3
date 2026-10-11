import unittest
from content_analysis import build_annotations, build_detail, pillar_summary
from account_diagnosis import diagnose
from profile_axes import IDENTITIES


class DiagnosisTests(unittest.TestCase):
    def test_manual_type_routes_focus_without_reclassifying_topics(self):
        notes = [{'标题': 'MBTI原理与认知方法', '正文': '解读人格心理学知识', '点赞': 10, '收藏': 5, '评论': 2}] * 8
        frame = build_detail(notes, build_annotations(notes))
        summary = pillar_summary(frame)
        knowledge = diagnose(frame, {'identity':'个人创作者','domains':['MBTI','知识'],'goals':['收藏沉淀']}, summary)
        brand = diagnose(frame, {'identity':'个人创作者','domains':['MBTI','知识'],'goals':['销售']}, summary)
        self.assertIn('知识价值线索',knowledge['分析重点'].tolist())
        self.assertIn('商品承接',brand['分析重点'].tolist())
        self.assertNotIn('商品承接', knowledge.to_string())
        self.assertIn('当前数据不足，暂无法判断', brand['观察结论'].tolist())
        self.assertIn('当前数据不足，暂无法判断', knowledge['观察结论'].tolist())

    def test_one_note_never_generates_operational_conclusions(self):
        notes = [{'标题': '新品推荐产品店铺购买', '点赞': 5, '收藏': 1, '评论': 0}]
        frame = build_detail(notes, build_annotations(notes))
        for kind in IDENTITIES:
            results = diagnose(frame, {'identity':kind,'domains':['知识'],'goals':['销售']}, pillar_summary(frame))
            self.assertTrue(results['观察结论'].eq('当前数据不足，暂无法判断').all())


if __name__ == '__main__':
    unittest.main()
