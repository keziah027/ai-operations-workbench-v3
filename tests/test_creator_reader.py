import unittest
from unittest.mock import Mock

from account_reader import AccountReadError
from creator_reader import check_creator_login, parse_note_rows, parse_overview, OVERVIEW_METRICS


class CreatorLoginTests(unittest.TestCase):
    def page(self, url, text):
        page = Mock(url=url)
        page.locator.return_value.inner_text.return_value = text
        return page

    def test_login_page_does_not_count_as_authenticated(self):
        page = self.page("https://creator.xiaohongshu.com/login", "短信登录\n发送验证码")
        with self.assertRaisesRegex(AccountReadError, "尚未登录"):
            check_creator_login(page)

    def test_unknown_page_is_not_login_success(self):
        page = self.page("https://creator.xiaohongshu.com/", "加载中")
        with self.assertRaisesRegex(AccountReadError, "暂时无法确认"):
            check_creator_login(page)

    def test_restriction_takes_priority_over_dashboard_text(self):
        page = self.page("https://creator.xiaohongshu.com/creator/home", "数据中心\n安全验证")
        with self.assertRaisesRegex(AccountReadError, "要求验证"):
            check_creator_login(page)

    def test_unrelated_site_rejected(self):
        page = self.page("https://example.com/", "数据中心")
        with self.assertRaisesRegex(AccountReadError, "不是小红书"):
            check_creator_login(page)

    def test_dashboard_recognized(self):
        page = self.page("https://creator.xiaohongshu.com/creator/home", "笔记管理\n数据中心")
        self.assertEqual(check_creator_login(page)["status"], "已进入创作平台后台")

    def test_overview_keeps_units_and_ignores_recommended_accounts(self):
        body = "创作服务平台\n测试账号\n小红书账号: 123456\n笔记数据总览\n统计周期 09-17 至 09-23\n"
        for label in OVERVIEW_METRICS:
            body += f"{label}\n{'1.4万' if label == '曝光数' else '0'}\n环比-7%\n"
        body += "最新笔记\n曝光数\n999999\n推荐账号\n粉丝数\n999999"
        parsed = parse_overview(body)
        self.assertEqual(parsed["name"], "测试账号")
        self.assertEqual(parsed["metrics"][0]["后台显示"], "1.4万")
        self.assertEqual(len(parsed["metrics"]), 12)

    def test_note_columns_mapped_by_header_and_missing_is_not_zero(self):
        headers = ["笔记基础信息", "收藏", "评论", "点赞", "观看"]
        row = {"title": "测试笔记", "date": "发布于2026-09-23 20:25", "cells": ["测试笔记", "0", "--", "1.2万", "120"]}
        note = parse_note_rows(headers, [row])[0]
        self.assertEqual(note["收藏"], 0)
        self.assertIsNone(note["评论"])
        self.assertIsNone(note["点赞"])
        self.assertEqual(note["观看"], 120)
        self.assertEqual(note["发布时间"], "2026-09-23 20:25")

    def test_note_schema_and_edit_date_fail_closed(self):
        row = {"title": "测试笔记", "date": "编辑于2026-09-23 20:25", "cells": ["测试笔记", "0", "1", "2"]}
        with self.assertRaisesRegex(AccountReadError, "表头已变化"):
            parse_note_rows(["笔记基础信息", "收藏", "收藏", "点赞"], [row])
        with self.assertRaisesRegex(AccountReadError, "首次发布时间"):
            parse_note_rows(["笔记基础信息", "收藏", "评论", "点赞"], [row])
