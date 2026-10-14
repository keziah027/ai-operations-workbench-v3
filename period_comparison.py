"""两次导入快照的本地对比；基线只在用户打开存档时捕获。"""
from copy import deepcopy
import pandas as pd
from note_schema import normalize_notes, content_text
from project_state import account_identity
from analysis import performance_tiers


def remember_period(state, project):
    # active_project 会随编辑/保存更新，必须另存上期，不能持有可变引用。
    state['period_baseline'] = deepcopy(project['snapshot'])


def _name(snapshot):
    notes = snapshot.get('notes', [])
    if any('账号名称' in row for row in notes):
        names = {content_text(row.get('账号名称')) for row in notes}
        if len(names) != 1 or not next(iter(names), ''): return ''
        return next(iter(names))
    # Excel 文件名不当成账号身份；旧存档仍可通过逐篇账号名称匹配。
    if 'Excel' in snapshot.get('source_kind', '') or str(snapshot.get('url', '')).startswith('Excel：'):
        return ''
    return content_text(snapshot.get('name'))


def matching_period_accounts(previous, current):
    if not previous or not current or not previous.get('notes') or not current.get('notes'): return False
    # 混合账号/明确ID冲突时不能仅靠相同显示名称自动比较。
    for snapshot in [previous, current]:
        for field in ['账号名称', '账号ID', 'account_id']:
            values = {content_text(row.get(field)) for row in snapshot['notes'] if field in row}
            if len(values) > 1: return False
    left, right = account_identity(previous), account_identity(current)
    if left['stable'] and right['stable']: return left['key'] == right['key']
    a, b = _name(previous), _name(current)
    return bool(a and b and a == b)


def period_comparison(previous, current):
    columns = ['指标', '上期', '本期', '变化']
    if not matching_period_accounts(previous, current): return pd.DataFrame(columns=columns)
    frames = [pd.DataFrame(normalize_notes(snapshot['notes'])) for snapshot in [previous, current]]
    values = []
    for frame in frames:
        values.append([pd.to_numeric(frame[metric], errors='coerce').mean() for metric in ['点赞','收藏','评论']]
                      + [performance_tiers(frame)['viral_rate']])
    return pd.DataFrame([{'指标': metric, '上期': old, '本期': new,
                          '变化': (new-old)*(100 if metric=='爆款率' else 1)}
                         for metric, old, new in zip(['平均点赞','平均收藏','平均评论','爆款率'], *values)], columns=columns)


def period_display(table):
    display = table.copy()
    for index, row in table.iterrows():
        for column in ['上期','本期','变化']:
            value = row[column]
            if pd.isna(value): text = '—'
            elif row['指标']=='爆款率':
                text = f'{value:+.2f} 个百分点' if column=='变化' else f'{value:.2%}'
            else: text = f'{value:+,.2f}' if column=='变化' else f'{value:,.2f}'
            display[column] = display[column].astype(object)
            display.at[index,column] = text
    return display
