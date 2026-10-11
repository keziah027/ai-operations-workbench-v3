import unittest
from dynamic_topics import discover_topics, OTHER


class TopicTests(unittest.TestCase):
    def test_labels_come_from_current_corpus(self):
        notes = []
        for title, body in [('情绪调节', '内耗焦虑与情绪调节'), ('亲密关系', '恋爱关系边界与亲密关系'), ('认知功能', '八维认知功能心理学')]:
            notes += [{'标题': f'MBTI {title} {i}', '正文': f'{body} #{title}'} for i in range(6)]
        result = discover_topics(notes)
        self.assertGreaterEqual(len(result['labels']), 3)
        self.assertLessEqual(len(result['labels']), 7)
        self.assertEqual(result['assignments'], discover_topics(notes)['assignments'])
        self.assertTrue(all(label != OTHER for label in result['assignments']))
        self.assertTrue(any('情绪' in label for label in result['labels']))
        self.assertFalse(set(result['labels']) & {'新品', '场景', 'IP故事', '教程', '用户共创'})
        # Each repeated theme should stay together, without a brand-specific taxonomy.
        for start in (0, 6, 12):
            self.assertEqual(len(set(result['assignments'][start:start+6])), 1)

    def test_unseen_domain_and_missing_text(self):
        notes = [{'标题': f'{theme}{i}', '正文': f'#{theme}'} for theme in ['火山地质', '海洋洋流', '恒星演化'] for i in range(5)]
        result = discover_topics(notes + [{'点赞': 100}])
        self.assertTrue(any('火山' in label for label in result['labels']))
        self.assertEqual(result['assignments'][-1], OTHER)
        self.assertEqual(discover_topics([])['labels'], [])

    def test_duplicate_content_does_not_invent_categories(self):
        result = discover_topics([{'标题': '完全相同的天文科普'}] * 20)
        self.assertEqual(len(result['labels']), 1)


if __name__ == '__main__':
    unittest.main()
