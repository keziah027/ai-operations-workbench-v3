import unittest
import pandas as pd
from topic_state import create_state
from dynamic_topics import discover_topics
from content_analysis import build_detail,high_interaction,body_structure
from packaging_analysis import change_cover_type,setup_packaging,packaging_tables

class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.notes=[{'标题':f'日常观察{i}','正文':'一段日常记录','点赞':i,'收藏':0,'评论':1} for i in range(12)]
        self.state=setup_packaging(create_state(self.notes,discover_topics(self.notes)))

    def test_custom_rename_delete_and_old_types(self):
        state=change_cover_type(self.state,'add',name='白板讲解')
        state['annotations'][0]['封面类型']='白板讲解'
        state['annotations'][1]['封面类型']='产品主体'
        state=change_cover_type(state,'rename',old='白板讲解',name='手绘讲解')
        self.assertEqual(state['annotations'][0]['封面类型'],'手绘讲解')
        self.assertEqual(state['annotations'][1]['封面类型'],'产品主体')
        with self.assertRaisesRegex(ValueError,'替代'): change_cover_type(state,'delete',old='手绘讲解')
        state=change_cover_type(state,'delete',old='手绘讲解',replacement='待标注')
        self.assertEqual(state['annotations'][0]['封面类型'],'待标注')

    def test_custom_comparison_and_overlapping_reviewed_tags(self):
        for index in [0,1,9,10]:
            self.state['annotations'][index].update({'封面类型':'自定义白板','封面辅助标签':'文字密集，有人物','辅助标签已复核':True})
        frame=build_detail(self.notes,pd.DataFrame(self.state['annotations']))
        comparison=high_interaction(frame,'点赞')[2].set_index('特征')
        self.assertEqual(comparison.loc['封面：自定义白板','高互动组有效篇数'],2)
        self.assertEqual(comparison.loc['辅助标签：有人物','其余组有效篇数'],2)
        table=packaging_tables(frame)['封面辅助标签（可重叠）']
        self.assertEqual(table['占已复核（%）'].sum(),200)
        self.assertEqual(body_structure('普通文字未匹配特定结构')[0],'未识别特定结构')
