import unittest

from content_analysis import (infer_pillar, build_annotations, build_detail, pillar_summary,
                              high_interaction, audience_signals, body_structure, safe_link)


class ContentAnalysisTests(unittest.TestCase):
    def notes(self, count=8):
        return [{"标题": f"新品{i}", "正文": "欢迎看我们的贴纸。\n到店铺购买", "点赞": i,
                 "收藏": 0, "评论": 1, "笔记链接": f"https://www.xiaohongshu.com/explore/{i:024x}"} for i in range(count)]

    def test_missing_text_remains_unknown(self):
        self.assertEqual(infer_pillar("", "")[0], "其他/待确认")

    def test_manual_correction_recomputes_shares_and_keeps_missing(self):
        notes = self.notes()
        notes[0]["收藏"] = None
        annotations = build_annotations(notes)
        annotations.loc[0, "主支柱"] = "用户共创"
        frame = build_detail(notes, annotations)
        summary = pillar_summary(frame).set_index("主支柱")
        self.assertEqual(summary.loc["用户共创", "占比（%）"], 12.5)
        self.assertEqual(summary["篇数"].sum(), 8)
        self.assertEqual(summary["占比（%）"].sum(), 100)
        self.assertTrue(frame.loc[0, ["收藏", "互动总量"]].isna().all())
        self.assertEqual(frame.loc[1, "收藏"], 0)

    def test_high_interaction_requires_complete_metrics_and_enough_samples(self):
        notes = self.notes()
        notes[7]["评论"] = None
        frame = build_detail(notes, build_annotations(notes))
        valid, _, comparison = high_interaction(frame, "互动总量")
        self.assertEqual(len(valid), 7)
        self.assertTrue(comparison.empty)
        valid, top, comparison = high_interaction(frame, "点赞")
        self.assertEqual(len(top), 2)
        self.assertEqual(top.iloc[0]["点赞"], 7)
        self.assertFalse(comparison.empty)

    def test_uniform_interactions_do_not_generate_pattern(self):
        notes = self.notes()
        for note in notes:
            note["点赞"] = 10
        frame = build_detail(notes, build_annotations(notes))
        self.assertTrue(high_interaction(frame, "点赞")[2].empty)

    def test_cover_comparison_does_not_treat_unlabelled_as_other_styles(self):
        notes = self.notes(12)
        annotations = build_annotations(notes)
        annotations.loc[[9, 10, 0, 1], "封面类型"] = "产品主体"
        frame = build_detail(notes, annotations)
        comparison = high_interaction(frame, "点赞")[2]
        cover = comparison[comparison["特征"] == "封面：产品主体"].iloc[0]
        self.assertEqual(cover["高互动组有效篇数"], 2)
        self.assertEqual(cover["其余组有效篇数"], 2)
        self.assertEqual(cover["占比差（百分点）"], 0)

    def test_body_structure_and_audience_have_evidence(self):
        structure, opening, ending = body_structure("这样制作\n1. 剪下纸片\n到店铺购买\n#手账")
        self.assertEqual(structure, "内容段落 → 步骤/清单 → 行动/承接提示 → 话题标签")
        notes = self.notes()
        signals = audience_signals(build_detail(notes, build_annotations(notes)), "原创文创")
        self.assertEqual(signals.iloc[0]["命中笔记数"], 8)
        self.assertIn("来自当前内容支柱", signals.iloc[0]["关键词依据"])
        self.assertEqual(body_structure("")[0], "未读取正文")

    def test_unsafe_links_and_cover_hosts_rejected(self):
        for link in ["javascript:alert(1)", "file:///C:/secret", "https://user:pass@example.com/x", "https://x.test:wrong/x"]:
            self.assertEqual(safe_link(link), "")
        self.assertEqual(safe_link("https://evil.example/cover.jpg", image=True), "")
        self.assertTrue(safe_link("https://sns-webpic-qc.xhscdn.com/a.jpg", image=True))
