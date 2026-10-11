import unittest
from account_profile import identify_account


class ProfileTests(unittest.TestCase):
    def test_mbti_and_work_are_not_commerce(self):
        notes = [{"标题": f"MBTI人格解读 INFP 情绪{i}", "正文": "心理学知识科普"} for i in range(10)]
        result = identify_account(notes, "MBTI心理学科普，了解人格与认知")
        self.assertIn('MBTI',result['domains'])
        self.assertIn('知识',result['domains'])
        self.assertEqual(result['goals'], [])
        self.assertTrue(result['candidates'].loc[result['candidates']['候选'].eq('MBTI'),'例证'].iloc[0])
        result = identify_account([{"标题": "面试简历求职"}] * 8, "职场求职，分享面试经验")
        self.assertIn('职场',result['domains'])

    def test_brand_and_insufficient(self):
        self.assertEqual(identify_account([{"标题": "新品预售，下单到店铺"}] * 8, "官方品牌旗舰店")['identity'], '品牌')
        self.assertEqual(identify_account([{"标题": "你好"}])['identity'], '待确认')
        self.assertEqual(identify_account([])['identity_confidence'], '低')
        self.assertEqual(identify_account([{"标题": "MBTI"}])['identity_confidence'], '低')


if __name__ == '__main__':
    unittest.main()
