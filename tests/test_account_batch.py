import unittest
from account_reader import parse_visible_cards
from account_batch import merge_notes, note_identity, valid_note_url


class BatchTests(unittest.TestCase):
    def test_pinned_notes_are_deduplicated_across_urls(self):
        identifier = "1234567890abcdef12345678"
        first = "https://www.xiaohongshu.com/explore/" + identifier + "?xsec_token=one"
        second = "https://www.xiaohongshu.com/user/profile/aaaaaaaaaaaaaaaaaaaaaaaa/" + identifier + "?xsec_token=two"
        self.assertEqual(note_identity(first), note_identity(second))
        notes = []
        merge_notes(notes, parse_visible_cards([{"title": "置顶", "href": first, "likes": "10"}]), 100)
        merge_notes(notes, parse_visible_cards([{"title": "置顶", "href": second, "likes": "10"}]), 100)
        self.assertEqual(len(notes), 1)

    def test_detail_urls_are_bounded_to_notes(self):
        self.assertTrue(valid_note_url("https://www.xiaohongshu.com/explore/1234567890abcdef12345678?xsec_token=abc"))
        for url in ["https://example.com/explore/1234567890abcdef12345678", "file:///secret", "https://www.xiaohongshu.com/user/profile/1234567890abcdef12345678", "https://www.xiaohongshu.com@evil.test/explore/1234567890abcdef12345678"]:
            self.assertFalse(valid_note_url(url))

    def test_requested_limit_is_respected(self):
        added = parse_visible_cards([{"title": str(i), "href": f"https://www.xiaohongshu.com/explore/{i:024x}", "likes": "0"} for i in range(40)])
        notes = []
        merge_notes(notes, added, 35)
        self.assertEqual(len(notes), 35)
        self.assertTrue(all(note["点赞"] == 0 and note["收藏"] is None for note in notes))


if __name__ == "__main__":
    unittest.main()
