import unittest
import itertools
from io import BytesIO
import pandas as pd
from analysis import prepare_data, read_excel
from note_schema import normalize_notes, THEME_FIELDS
from profile_axes import identify_account, commerce_context
from dynamic_topics import discover_topics
from content_analysis import build_annotations, build_detail, pillar_summary, high_interaction
from performance import sample_audit, backend_tables
from account_diagnosis import diagnose
from cross_account_cases import CASES, case_notes


class CrossAccountTests(unittest.TestCase):
    def test_title_only_excel_and_local_publication_date(self):
        buffer=BytesIO()
        pd.DataFrame({'笔记标题':['INFJ的独处日记','职场新人如何复盘'],
                      '发布时间':['2026-09-26T00:30:00+08:00','编辑于2026-09-26']}).to_excel(buffer,index=False)
        frame,_=read_excel(buffer.getvalue())
        self.assertEqual(len(frame),2)
        self.assertTrue(frame[['点赞','收藏','评论']].isna().all().all())
        self.assertEqual(frame.loc[0,'发布时间'],pd.Timestamp('2026-09-26 00:30'))
        detail=build_detail(frame.to_dict('records'),build_annotations(frame.to_dict('records')))
        self.assertEqual(str(backend_tables(detail)['发布时间表现'].iloc[0]['发布日期']),'2026-09-26')

    def test_narrative_cases_keep_identity_and_multiple_domains_separate(self):
        for case in CASES:
            with self.subTest(case=case['name']):
                notes=case_notes(case)
                profile=identify_account(notes,case['bio'])
                self.assertEqual(profile['identity'],case['identity'])
                self.assertTrue(set(case['domains']).issubset(profile['domains']),profile['domains'])
                self.assertEqual(profile['goals'],[])
                topics=discover_topics(notes)
                self.assertGreaterEqual(len(topics['labels']),3)
                self.assertLessEqual(len(topics['labels']),7)
                annotations=build_annotations(notes,topics)
                annotations.loc[0,'主支柱']='人工主题'
                frame=build_detail(notes,annotations)
                summary=pillar_summary(frame)
                self.assertEqual(int(summary['篇数'].sum()),len(notes))
                self.assertEqual(summary.set_index('主支柱').loc['人工主题','篇数'],1)
                context={'identity':case['identity'],'domains':case['domains'],'goals':case['goals']}
                diagnoses=diagnose(frame,context,summary)
                if case['name']=='美妆品牌':
                    self.assertIn('使用与测评',diagnoses['分析重点'].tolist())
                    self.assertIn('商品承接',diagnoses['分析重点'].tolist())
                if case['name']=='MBTI':
                    self.assertNotIn('商品承接',diagnoses['分析重点'].tolist())
                if case['name']=='本地生活机构':
                    self.assertIn('到店承接',diagnoses['分析重点'].tolist())

    def test_all_16_mbti_codes_and_no_false_ascii_substrings(self):
        for chars in itertools.product('IE','NS','TF','JP'):
            code=''.join(chars)
            self.assertIn('MBTI',identify_account([{'标题':code+'的日记'}]*2)['domains'],code)
        self.assertNotIn('MBTI',identify_account([{'标题':'xinfxj and infjextra'}]*4)['domains'])

    def test_sales_gate_uses_goals_or_actual_evidence(self):
        notes=case_notes(CASES[1])
        self.assertFalse(commerce_context(notes,[])['enabled'])
        self.assertTrue(commerce_context(notes,['销售'])['enabled'])
        self.assertTrue(commerce_context([{'标题':'领取课程以后可以到店铺购买练习册'}],[])['enabled'])
        self.assertFalse(commerce_context([{'标题':'我是一个美妆品牌'}],[])['enabled'])

    def test_all_old_theme_columns_and_placeholders(self):
        for column in THEME_FIELDS:
            raw=pd.DataFrame({'标题':['','', ''], '点赞':[1,2,3],'收藏':[0,0,0],'评论':[0,0,0],column:['未分类','待确认','火山地质']})
            data,_=prepare_data(raw)
            notes=normalize_notes(data.to_dict('records'))
            self.assertEqual(notes[0]['主题文本'],'')
            self.assertEqual(notes[1]['主题文本'],'')
            self.assertEqual(notes[2]['主题文本'],'火山地质')
            topics=discover_topics(notes)
            self.assertFalse(any('未分类' in label or '待确认' in label for label in topics['labels']))
            self.assertTrue(any('火山' in label for label in topics['labels']))

    def test_identical_precision_across_excel_public_creator(self):
        for raw,precision,estimate in [('1.2万','近似',12000),('1千+','下界',1000),('12000','精确',12000),('0','精确',0),('—','缺失',None)]:
            excel,_=prepare_data(pd.DataFrame({'点赞':[raw],'收藏':[1],'评论':[1]}))
            public=normalize_notes([{'点赞':None,'前台点赞显示':raw,'收藏':1,'评论':1}])[0]
            creator=normalize_notes([{'点赞':None,'后台点赞显示':raw,'收藏':1,'评论':1}])[0]
            for note in [excel.iloc[0].to_dict(),public,creator]:
                self.assertEqual(note['点赞精度'],precision)
                self.assertEqual(note['点赞数值'],estimate)
                if precision!='精确': self.assertTrue(pd.isna(note['点赞']))
            again=normalize_notes([public])[0]
            self.assertEqual(again,public)

    def test_excluded_rows_rates_and_metric_scope(self):
        notes=case_notes(CASES[2])
        notes[0]['点赞']='1.2万'
        notes[1]['点赞']=None
        notes[2]['曝光']=0
        notes[3].update({'观看统计周期':'近7日','曝光统计周期':'累计'})
        frame=build_detail(notes,build_annotations(notes))
        valid,_,_=high_interaction(frame,'点赞')
        audit=sample_audit(frame,'点赞')
        self.assertEqual(len(valid),6)
        self.assertEqual(audit['是否纳入'].eq('否').sum(),2)
        self.assertIn('近似',audit.iloc[0]['纳入/排除依据'])
        self.assertIn('缺失',audit.iloc[1]['纳入/排除依据'])
        self.assertTrue(pd.isna(frame.loc[2,'观看曝光比']))
        self.assertTrue(pd.isna(frame.loc[3,'观看曝光比']))
        self.assertIn('统计周期',sample_audit(frame,'观看曝光比').iloc[3]['纳入/排除依据'])
        self.assertAlmostEqual(frame.loc[4,'每千次观看涨粉'],5/220*1000)
        tables=backend_tables(frame)
        self.assertEqual(tables['内容形式表现']['篇数'].sum(),8)
        self.assertEqual(tables['发布时间表现']['篇数'].sum(),8)

    def test_title_only_and_all_missing_metrics_do_not_invent_body_or_performance(self):
        notes=[dict(note,正文='',点赞=None,收藏=None,评论=None,曝光=None,观看=None,涨粉=None) for note in case_notes(CASES[1])]
        frame=build_detail(notes,build_annotations(notes))
        self.assertTrue(frame['正文结构'].eq('未读取正文').all())
        self.assertTrue(high_interaction(frame,'互动总量')[0].empty)
        diagnosis=diagnose(frame,{'identity':'个人创作者','domains':['MBTI'],'goals':['涨粉','收藏沉淀']},pillar_summary(frame))
        body_diagnosis=diagnosis[~diagnosis['分析重点'].eq('选题结构')]
        self.assertTrue(body_diagnosis['观察结论'].eq('当前数据不足，暂无法判断').all())


if __name__=='__main__': unittest.main()
