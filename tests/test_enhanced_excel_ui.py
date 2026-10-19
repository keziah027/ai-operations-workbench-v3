from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import unittest
import pandas as pd
from streamlit.testing.v1 import AppTest
from ai_client import AIConfig

class EnhancedExcelUITests(unittest.TestCase):
    def test_time_tiers_comparison_and_linked_ideas_without_api(self):
        for multi in [True,False]:
            raw=pd.DataFrame({'标题':[f'求职面试技巧{i}' for i in range(8)],
                '账号名称':['甲']*4+(['乙']*4 if multi else ['甲']*4),
                '发布时间':[f'2026-10-{12+i%2} {8+i:02d}:00' for i in range(8)],
                '点赞':[10,20,30,40,100,200,300,400], '收藏':[1,2,3,4]*2, '评论':[1]*8,
                '对应选题':['XT-test']*8})
            upload=BytesIO();raw.to_excel(upload,index=False);upload.name='功能验收（模拟）.xlsx'
            with patch('streamlit.file_uploader',return_value=upload),patch('ai_ui.load_config',return_value=AIConfig()),patch('ai_ui.ask_ai') as api:
                app=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=60).run()
                app.button('cover-start').click().run()
                app.button('source-card-0').click().run()
                self.assertFalse(app.exception,app.exception)
                api.assert_not_called()
                self.assertTrue(any(x.label=='爆款率' for x in app.metric))
                self.assertTrue(any(x.label=='点赞中位数' for x in app.metric))
                headings=[x.value for x in app.subheader]
                self.assertEqual('多账号横向对比' in headings,multi)
                self.assertIn('选题效果',headings)
                time_tables=[x.value for x in app.dataframe if '星期' in x.value or '时段' in x.value]
                self.assertEqual(len(time_tables),2)
                self.assertEqual(next(x.value for x in app.metric if x.label=='总发布篇数'),'8')
                account=next((x for x in app.selectbox if x.label=='选择需要进行V2分析的账号'),None)
                self.assertEqual(account is not None,multi)
                effects=next(x.value for x in app.dataframe if '对应选题' in x.value and '关联篇数' in x.value)
                self.assertEqual(effects.iloc[0]['关联篇数'],4 if multi else 8)
