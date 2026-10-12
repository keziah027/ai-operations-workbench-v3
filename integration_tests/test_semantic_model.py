"""Opt-in real CPU model integration test; downloads pinned public weights once."""
import os
import unittest
from unittest.mock import patch
from smart_topics import discover_smart_topics

class RealModelTests(unittest.TestCase):
    @patch.dict(os.environ, {'TOPIC_ENGINE':'semantic'})
    def test_chinese_topics_paraphrases_and_uncertainty(self):
        titles=['跳槽面试之前要准备什么','换工作怎么提高录用机会','黄金涨价的宏观经济原因',
                '某集团斥资百亿收购竞争对手','教你画出自然干净的底妆','只用两个鸡蛋做松软蛋糕',
                '如何科学训练提高跑步耐力','简历如何呈现项目成果','没有什么想说的']
        expected=['求职与职业发展','求职与职业发展','宏观经济与国际财经','企业经营与资本运作',
                  '化妆与发型教程','烹饪与食谱','运动训练与健身','求职与职业发展','其他/待确认']
        result=discover_smart_topics([{'标题':title} for title in titles])
        self.assertEqual(result['origin'],'语义初判')
        self.assertEqual(result['assignments'],expected)
        self.assertFalse(result.get('retry_semantic'))

if __name__=='__main__':unittest.main()
