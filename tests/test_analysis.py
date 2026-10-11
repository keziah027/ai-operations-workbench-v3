import io
import unittest

import pandas as pd

from analysis import daily_trend, group_summary, inspect_workbook, prepare_data, read_excel, summarize


class AnalysisTests(unittest.TestCase):
    def sample(self):
        return pd.DataFrame({
            "标题": ["测试一", "测试二", "测试三"],
            "点赞": [100, 0, 200], "收藏": [20, 5, 30], "评论": [10, 1, 4],
            "发布时间": ["2026-09-01", "2026-09-01", "2026-09-02"],
            "内容主题": ["护肤", "护肤", "彩妆"],
        })

    def test_excel_roundtrip_and_metrics(self):
        buffer = io.BytesIO()
        self.sample().to_excel(buffer, index=False)
        buffer.seek(0)
        df, messages = read_excel(buffer)
        self.assertEqual(messages, [])
        self.assertEqual(summarize(df), {
            "总发布篇数": 3, "总点赞": 300, "平均点赞": 100.0,
            "总收藏": 55, "平均收藏": 55 / 3, "总评论": 15, "平均评论": 5.0,
        })
        self.assertAlmostEqual(df.loc[0, "藏赞比"], 0.2)
        self.assertAlmostEqual(df.loc[0, "评赞比"], 0.1)
        self.assertTrue(pd.isna(df.loc[1, "藏赞比"]))
        self.assertTrue(pd.isna(df.loc[1, "评赞比"]))
        grouped = group_summary(df, "内容主题").set_index("内容主题")
        self.assertEqual(grouped.loc["护肤", "内容数量"], 2)
        self.assertEqual(grouped.loc["护肤", "平均点赞"], 50)
        self.assertEqual(daily_trend(df)["平均点赞"].tolist(), [50, 200])

    def test_numeric_formats_and_blank_rows(self):
        raw = pd.DataFrame({" 点赞 ": ["1.2万", "1,200", None, " "],
                            "收藏": ["2千", 10, 2, None], "评论": [2, 1, None, None]})
        df, messages = prepare_data(raw)
        self.assertTrue(pd.isna(df['点赞'].iloc[0]))
        self.assertEqual(df['点赞数值'].iloc[0],12000)
        self.assertEqual(df['点赞精度'].iloc[0],'近似')
        self.assertEqual(df['点赞'].iloc[1],1200)
        self.assertTrue(pd.isna(df["点赞"].iloc[2]))
        self.assertEqual(summarize(df)["平均点赞"], 1200)
        self.assertTrue(pd.isna(df['收藏'].iloc[0]))
        self.assertEqual(df['收藏数值'].iloc[0],2000)
        self.assertEqual(df['收藏'].iloc[1:].tolist(),[10,2])
        self.assertEqual(len(df), 3)
        self.assertTrue(messages)

    def test_missing_is_not_zero_and_all_missing_is_unavailable(self):
        df, _ = prepare_data(pd.DataFrame({"标题": ["A", "B", "C"], "点赞": [10, None, 0],
                                          "收藏": [None, None, None], "评论": [2, None, 0], "内容主题": ["同组"] * 3}))
        summary = summarize(df)
        self.assertEqual(summary["总发布篇数"], 3)
        self.assertEqual(summary["平均点赞"], 5)
        self.assertIsNone(summary["总收藏"])
        self.assertIsNone(summary["平均收藏"])
        self.assertTrue(df["藏赞比"].isna().all())
        self.assertEqual(group_summary(df, "内容主题").iloc[0]["内容数量"], 3)
        self.assertEqual(group_summary(df, "内容主题").iloc[0]["平均点赞"], 5)

    def test_edit_date_does_not_become_publication_date(self):
        raw = self.sample()
        raw["发布时间"] = ["编辑于 2026-09-01", "2026-09-01", "2026-09-02"]
        df, messages = prepare_data(raw)
        self.assertTrue(pd.isna(df.loc[0, "发布时间"]))
        self.assertEqual(df.loc[0, "原始日期"], "编辑于 2026-09-01")
        self.assertEqual(daily_trend(df)["平均点赞"].tolist(), [0, 200])
        self.assertTrue(any("编辑日期" in message for message in messages))

    def test_multisheet_workbook_with_offset_header_and_aliases(self):
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame({"核心指标": ["发布篇数"], "数值": [3]}).to_excel(writer, sheet_name="账号总览", index=False)
            rows = self.sample().rename(columns={"标题": "笔记标题", "发布时间": "前台日期", "点赞": "点赞数"})
            rows["内容形式"] = ["图文", "视频", "图文"]
            rows.to_excel(writer, sheet_name="历史笔记库", index=False, startrow=2)
            pd.DataFrame({"主题": ["A"], "平均值项:点赞": [100], "平均值项:收藏": [10], "平均值项:评论": [2]}).to_excel(writer, sheet_name="透视表", index=False)
        contents = buffer.getvalue()
        structure = inspect_workbook(contents)
        self.assertEqual(structure["candidates"], [{"sheet": "历史笔记库", "header_row": 3, "has_title": True}])
        df, _ = read_excel(contents)
        self.assertEqual(summarize(df)["总点赞"], 300)
        self.assertEqual(df.attrs["source"]["header_row"], 3)
        self.assertEqual(df["图文/视频"].tolist(), ["图文", "视频", "图文"])

    def test_error_reports_actual_excel_row_after_header(self):
        buffer = io.BytesIO()
        raw = self.sample()
        raw.loc[1, "点赞"] = -1
        raw.to_excel(buffer, index=False, startrow=2)
        with self.assertRaisesRegex(ValueError, "第 5 行"):
            read_excel(buffer.getvalue())

    def test_alias_collision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "重复"):
            prepare_data(pd.DataFrame([[1, 2, 3, 4]], columns=["点赞", "点赞数", "收藏", "评论"]))

    def test_reject_invalid_counts(self):
        for invalid in ["很多", -1, 2.5, "inf", 10**15]:
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "第 2 行"):
                    prepare_data(pd.DataFrame({"点赞": [invalid], "收藏": [0], "评论": [0]}))

    def test_missing_empty_and_duplicate_columns(self):
        with self.assertRaisesRegex(ValueError, "无法识别笔记明细"):
            prepare_data(pd.DataFrame({"账号总览": ["测试"]}))
        with self.assertRaisesRegex(ValueError, "没有内容数据"):
            prepare_data(pd.DataFrame(columns=["点赞", "收藏", "评论"]))
        with self.assertRaisesRegex(ValueError, "重复"):
            prepare_data(pd.DataFrame([[1, 2, 3, 4]], columns=["点赞", " 点赞 ", "收藏", "评论"]))

    def test_optional_fields_and_invalid_dates(self):
        raw = self.sample()
        raw["发布时间"] = ["2026-09-01", "错误日期", 45292]
        df, messages = prepare_data(raw)
        self.assertEqual(df["发布时间"].isna().sum(), 1)
        self.assertEqual(df.loc[2, "发布时间"], pd.Timestamp("2024-01-01"))
        self.assertEqual(summarize(df)["总发布篇数"], 3)
        self.assertEqual(len(daily_trend(df)), 2)
        self.assertTrue(messages)


if __name__ == "__main__":
    unittest.main()
