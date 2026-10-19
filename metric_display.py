"""Show platform abbreviations without replacing the exact analysis inputs."""
import pandas as pd
from note_schema import count_info

METRICS = ['点赞', '收藏', '评论']
NOTICE = '按页面显示值折算；“万”为约数，“10万+”按10万作为绘图基数，实际更高。同显示值不区分高低。'


def display_info(note, metric):
    raw = note.get(metric+'原文')
    info = count_info(raw)
    if info['number'] is None:
        info = count_info(note.get(metric))
    hint = note.get(metric+'精度')
    if info['precision']=='精确' and hint in ('近似','下界'):
        info.update(precision=hint, exact=None)
    return info


def metric_text(note, metric):
    info = display_info(note, metric)
    if info['number'] is None:
        return '—'
    return info['raw'] if info['precision'] != '精确' else f"{info['number']:,}"


def display_values(frame, metric):
    return pd.Series([display_info(row, metric)['number'] for row in frame.to_dict('records')], index=frame.index, dtype=float)


def has_abbreviations(frame, metric):
    return any(display_info(row, metric)['precision'] in ('近似', '下界') for row in frame.to_dict('records'))


def display_table(frame):
    result = frame.copy()
    for metric in METRICS:
        if metric in frame:
            result[metric] = [metric_text(row, metric) for row in frame.to_dict('records')]
    return result


def export_display(frame):
    result = frame.copy()
    for metric in METRICS:
        if metric in frame and has_abbreviations(frame, metric):
            result[metric+'（精确值）'] = frame[metric]
            result[metric] = [info['raw'] if info['precision'] in ('近似','下界') else row.get(metric)
                              for row in frame.to_dict('records') for info in [display_info(row,metric)]]
    return result


def display_total(frame, metric, mean=False):
    values = display_values(frame, metric).dropna()
    if values.empty:
        return '—'
    value = values.mean() if mean else values.sum()
    infos = [display_info(row, metric) for row in frame.to_dict('records')]
    approximate = any(info['precision']=='近似' for info in infos)
    lower = any(info['precision']=='下界' for info in infos)
    if value >= 10000 and (approximate or lower):
        number = f'{value/10000:.2f}'.rstrip('0').rstrip('.')+'万'
    else:
        number = f'{value:,.1f}' if mean else f'{value:,.0f}'
    return ('约' if approximate else '≥' if lower else '') + number + ('+' if lower and approximate else '')


def display_ranking(frame, metric, limit=10):
    result = frame.copy()
    result['_显示折算值'] = display_values(frame, metric)
    result = result.dropna(subset=['_显示折算值']).sort_values('_显示折算值',ascending=False,kind='stable')
    result['_显示分组'] = result['_显示折算值'].rank(method='min',ascending=False).astype(int)
    return result.head(limit)
