import unittest
import pandas as pd
from dynamic_topics import discover_topics,OTHER
from note_schema import normalize_notes
from topic_state import create_state,rename_topic,merge_topics,move_notes,undo_topic,review_topics
from content_analysis import build_detail,pillar_summary


class TopicOperationTests(unittest.TestCase):
    def setUp(self):
        self.notes=[{'标题':f'{topic}{i}','正文':f'#{topic} #共同话题','点赞':i,'收藏':2,'评论':1}
                    for topic in ['火山地质','海洋洋流','恒星演化'] for i in range(4)]
        self.state=create_state(self.notes,discover_topics(self.notes))
        self.state['annotations'][0]['封面观察']='保留观察'

    def test_placeholder_raw_and_combined_fields(self):
        raw=[{'标题':'未命名笔记','正文':'待确认','产品系列/内容主题':'未分类'}]
        normal=normalize_notes(raw)
        self.assertEqual(normal[0]['产品系列/内容主题'],'未分类')
        self.assertEqual(discover_topics(raw)['labels'],[])
        real=[{'产品系列/内容主题':'火山地质'}]*4
        self.assertIn('火山地质',discover_topics(real)['labels'])

    def test_common_hashtag_not_every_name(self):
        result=discover_topics(self.notes)
        self.assertNotIn('共同话题',result['labels'])
        self.assertEqual(len(discover_topics([self.notes[0]]*12)['labels']),1)

    def test_rename_identity_and_undo_preserve_other_edits(self):
        identity=self.state['annotations'][0]['主题ID']
        result=rename_topic(self.state,identity,'新主题名称')
        self.assertEqual(result['annotations'][0]['主题ID'],identity)
        self.assertEqual(result['annotations'][0]['主支柱'],'新主题名称')
        result['annotations'][0]['封面观察']='稍后补充'
        restored=undo_topic(result)
        self.assertEqual(restored['annotations'][0]['封面观察'],'稍后补充')
        self.assertEqual(restored['annotations'][0]['主支柱'],self.state['annotations'][0]['主支柱'])

    def test_merge_split_final_review_and_counts(self):
        ids=[topic['id'] for topic in self.state['topics'] if topic['id']!='other']
        merged=merge_topics(self.state,ids[:2],'合并主题')
        identity=next(t['id'] for t in merged['topics'] if t['name']=='合并主题')
        selected=next(row['序号'] for row in merged['annotations'] if row['主题ID']==identity)
        split=move_notes(merged,identity,[selected],new_name='人工新选题')
        frame=build_detail(self.notes,pd.DataFrame(split['annotations']))
        self.assertEqual(len(frame),12)
        self.assertEqual(pillar_summary(frame)['篇数'].sum(),12)
        self.assertEqual(frame['主题ID'].count(),12)
        self.assertEqual(frame.iloc[0]['封面观察'],'保留观察')
        self.assertEqual(frame['自动主支柱'].tolist(),[row['自动主支柱'] for row in self.state['annotations']])
        review=review_topics(frame).set_index('最终主题')
        self.assertEqual(review.loc['人工新选题','篇数'],1)
        self.assertIn(f'第{selected}篇',review.loc['人工新选题','代表笔记'])
        self.assertEqual(undo_topic(split)['annotations'],merged['annotations'])

