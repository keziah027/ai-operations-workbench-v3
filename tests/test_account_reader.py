import unittest
from unittest.mock import patch

from account_reader import AccountReadError, collect_public_profile, exact_count, parse_visible_cards, validate_profile_url


class PublicAccountTests(unittest.TestCase):
    def test_share_text_and_profile_url(self):
        self.assertEqual(validate_profile_url("分享账号 https://xhslink.cn/o/synthetic-demo 复制打开"), "https://xhslink.cn/o/synthetic-demo")
        self.assertEqual(validate_profile_url("https://www.xiaohongshu.com/user/profile/aaaaaaaaaaaaaaaaaaaaaaaa"), "https://www.xiaohongshu.com/user/profile/aaaaaaaaaaaaaaaaaaaaaaaa")

    def test_unrelated_and_note_urls_are_rejected(self):
        for url in ["https://localhost/", "https://www.xiaohongshu.com.evil.test/", "https://www.xiaohongshu.com@evil.test/", "https://xhslink.cn:123/abc", "https://www.xiaohongshu.com/explore/123", "http://xhslink.cn/o/abc"]:
            with self.subTest(url=url), self.assertRaises(AccountReadError):
                validate_profile_url(url)

    def test_unknown_and_rounded_counts_stay_unknown(self):
        self.assertEqual(exact_count("1,234"), 1234)
        self.assertEqual(exact_count("0"), 0)
        for text in ["", "赞", "1.2万", "1千+", "10+", "—"]:
            self.assertIsNone(exact_count(text))

    def test_cards_keep_missing_metrics_and_do_not_duplicate_notes(self):
        cards = [{"title": "第一篇", "likes": "12", "href": "https://www.xiaohongshu.com/explore/1"},
                 {"title": "第二篇", "likes": "1千+", "href": "https://www.xiaohongshu.com/explore/2"}]
        notes = parse_visible_cards(cards + cards[:1])
        self.assertEqual(len(notes), 2)
        self.assertEqual(notes[0]["点赞"], 12)
        self.assertIsNone(notes[1]["点赞"])
        self.assertTrue(all(note["收藏"] is None and note["评论"] is None for note in notes))

    def test_identical_titles_without_links_are_not_silently_merged(self):
        self.assertEqual(len(parse_visible_cards([{"title": "同标题", "likes": "1"}, {"title": "同标题", "likes": "2"}])), 2)

    def test_access_restriction_returns_no_partial_stats(self):
        with patch("playwright.sync_api.sync_playwright") as engine:
            browser = engine.return_value.__enter__.return_value.chromium.launch.return_value
            page = browser.new_page.return_value
            page.url = "https://www.xiaohongshu.com/website-login/error?error_code=300012"
            page.locator.return_value.inner_text.return_value = "IP存在风险"
            with self.assertRaisesRegex(AccountReadError, "限制"):
                collect_public_profile("https://xhslink.cn/o/synthetic-demo")
            page.locator.return_value.evaluate_all.assert_not_called()
            browser.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
