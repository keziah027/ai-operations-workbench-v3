"""Reviewed sources, uncertain semantic matches and preservation of manual edits."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import os
import unittest
from unittest.mock import patch
import numpy as np
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest
from real_cases import list_cases, case_snapshot
from smart_topics import discover_smart_topics, reviewed_topics
from topic_catalog import CATALOG
from topic_state import create_state, rename_topic
from project_state import new_project, collect_project, refresh_project
from dynamic_topics import OTHER


class SmartTopicTests(unittest.TestCase):
    def test_reviewed_cases_exact_coverage_and_evidence(self):
        count=0
        for case in list_cases():
            notes=case_snapshot(case)['notes']
            with patch('semantic_encoder.encode', side_effect=AssertionError('Case must not download a model')):
                result=discover_smart_topics(notes, case['id'])
            count+=len(notes)
            self.assertEqual(result['origin'],'案例预先复核')
            self.assertEqual(len(result['assignments']),len(notes))
            self.assertTrue(all(len(name)<=14 and '主题1' not in name for name in result['labels']))
            self.assertTrue(all('未推断视频全文' in value for value in result['evidence']))
            self.assertTrue(all(not note.get('正文') for note in notes))
        self.assertEqual(count,72)

    def test_changed_source_cannot_claim_reviewed_classification(self):
        case=list_cases()[0];notes=deepcopy(case['notes'])
        notes[0]['标题']='完全不同的新内容'
        self.assertIsNone(reviewed_topics(notes,case['id']))
        notes=deepcopy(case['notes']);notes[0]['内容概述（整理）']='内容更新'
        self.assertIsNone(reviewed_topics(notes,case['id']))

    @patch.dict(os.environ, {'TOPIC_ENGINE':'semantic'})
    def test_semantic_decision_uncertainty_and_explicit_source_topics(self):
        labels=list(CATALOG);scores=np.zeros((4,len(labels)))
        scores[0,labels.index('求职与职业发展')]=.7
        scores[1,:]=.2
        result=discover_smart_topics([{'标题':'准备换工作'}, {'标题':'随便说说'},
                                      {'标题':'第一篇','内容主题':'自有栏目'}, {'标题':'第二篇','内容主题':'自有栏目'}],
                                     encoder=lambda texts:scores,prototype_vectors=np.eye(len(labels)))
        self.assertEqual(result['assignments'],['求职与职业发展',OTHER,'自有栏目','自有栏目'])
        self.assertIn('不是准确率',result['evidence'][0])
        self.assertEqual(result['confidence'][1],'低')

    @patch.dict(os.environ, {'TOPIC_ENGINE':'semantic'})
    def test_model_failure_retains_usable_free_analysis(self):
        def unavailable(texts):raise OSError('offline')
        result=discover_smart_topics([{'标题':'化妆教程'}],encoder=unavailable)
        self.assertEqual(len(result['assignments']),1)
        self.assertIn('模型暂不可用',result['method'])
        self.assertEqual(result['origin'],'文本初判')

    def test_reviewed_theme_edits_survive_project_refresh(self):
        case=case_snapshot(list_cases()[0]);automatic=discover_smart_topics(case['notes'],case['id'])
        project=new_project(case,automatic)
        state=rename_topic(project['state']['editing'],automatic['topic_ids'][0],'人工主题名称')
        saved=collect_project(project,case,state,{}, {},'复核项目')
        restored=refresh_project(saved,case,automatic)
        self.assertEqual(restored['state']['editing']['annotations'][0]['主支柱'],'人工主题名称')
        self.assertEqual(restored['state']['editing']['annotations'][0]['自动主支柱'],automatic['assignments'][0])

    def test_page_sources_at_bottom_and_report_provenance(self):
        import excel_export
        original=excel_export.public_workbook;captured={}
        def export(snapshot,analysis):
            data=original(snapshot,analysis);captured.update(data=data,analysis=analysis);return data
        with patch('excel_export.public_workbook',side_effect=export):
            app=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=60).run()
            app.radio[0].set_value('真实账号案例').run()
            next(x for x in app.button if x.label=='加载真实账号案例').click().run()
        self.assertFalse(app.exception,app.exception)
        self.assertEqual(app.expander[-1].label,'数据来源与说明')
        self.assertFalse(app.expander[-1].proto.expanded)
        self.assertFalse(app.warning)
        analysis=captured['analysis']
        self.assertEqual(analysis['topic_origin'],'案例预先复核')
        self.assertTrue(analysis['annotations']['最终分类来源'].eq('案例预先复核').all())
        cells=[cell.value for row in load_workbook(BytesIO(captured['data']))['分析汇总'] for cell in row]
        self.assertIn('案例预先复核',cells)
        self.assertIn(analysis['topic_method'],cells)

if __name__=='__main__':unittest.main()
