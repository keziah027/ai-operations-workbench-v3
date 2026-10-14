import unittest
from copy import deepcopy
from unittest.mock import patch
import pandas as pd
from period_comparison import period_comparison, period_display, remember_period

def snapshot(name='测试账号', likes=(1,2,3,4), **extra):
    return dict(name=name,source_kind='Excel上传',notes=[{'标题':f'笔记{i}','账号名称':name,'点赞':v,'收藏':2,'评论':None} for i,v in enumerate(likes)],**extra)

class PeriodComparisonTests(unittest.TestCase):
    def test_both_periods_exact_means_and_percentage_points(self):
        prev=snapshot(likes=(1,2,3,4)); curr=snapshot(likes=(2,4,6,6))
        table=period_comparison(prev,curr).set_index('指标')
        self.assertEqual(table.loc['平均点赞','上期'],2.5)
        self.assertEqual(table.loc['平均点赞','变化'],2)
        self.assertEqual(table.loc['爆款率','变化'],25)
        display=period_display(table.reset_index())
        self.assertEqual(display.loc[3,'变化'],'+25.00 个百分点')
        self.assertEqual(display.loc[2,'变化'],'—')

    def test_no_previous_mismatch_empty_and_mixed_accounts(self):
        mixed=snapshot(); mixed['notes'][0]['账号名称']='另一账号'
        for prev,curr in [(None,snapshot()),(snapshot(),snapshot('另一账号')),(snapshot(likes=()),snapshot()),(mixed,snapshot())]:
            self.assertTrue(period_comparison(prev,curr).empty)

    def test_explicit_ids_override_name_and_conflicts_never_match(self):
        self.assertFalse(period_comparison(snapshot(account_id='a'),snapshot(account_id='a')).empty)
        self.assertTrue(period_comparison(snapshot(account_id='a'),snapshot(account_id='b')).empty)
        self.assertFalse(period_comparison(snapshot(account_id='a'),snapshot('新昵称',account_id='a')).empty)

    def test_mixed_precision_all_missing_small_sample_and_equal_quartiles(self):
        prev=snapshot(likes=(1,2,3,4)); curr=snapshot(likes=('1万','20+',None,8))
        table=period_comparison(prev,curr).set_index('指标')
        self.assertEqual(table.loc['平均点赞','本期'],8)
        self.assertTrue(pd.isna(table.loc['爆款率','本期']))
        self.assertTrue(pd.isna(period_comparison(prev,snapshot(likes=(1,1,1,1))).iloc[3]['变化']))
        curr=snapshot(likes=(None,)*4)
        self.assertTrue(pd.isna(period_comparison(prev,curr).iloc[0]['本期']))

    def test_loaded_baseline_is_immutable_and_save_does_not_replace_it(self):
        project={'snapshot':snapshot()}; state={}; remember_period(state,project)
        project['snapshot']['notes'][0]['点赞']=999
        state['active_project']=project
        self.assertEqual(state['period_baseline']['notes'][0]['点赞'],1)

    def test_excel_filename_is_not_an_account(self):
        prev=snapshot(); curr=snapshot()
        for value in [prev,curr]:
            for row in value['notes']: row.pop('账号名称')
        self.assertTrue(period_comparison(prev,curr).empty)

    def test_ui_shown_only_after_matching_loaded_project(self):
        from app import render_period_comparison
        with patch('app.st') as ui:
            ui.session_state={'period_baseline':snapshot()}
            render_period_comparison(snapshot(likes=(2,3,4,5)))
            ui.subheader.assert_called_once_with('多期环比（本期 vs 上期）')
            ui.dataframe.assert_called_once()
        with patch('app.st') as ui:
            ui.session_state={}; render_period_comparison(snapshot())
            ui.subheader.assert_not_called()
