"""Excel 清洗与基础统计。与网页分开，方便检查计算结果。"""

import io
from datetime import datetime
import re
from zipfile import ZipFile, BadZipFile
from deployment import public_mode

import pandas as pd
from note_schema import FIELD_ALIASES, normalize_note, COUNT_FIELDS, publication_dates
from performance import add_ratios

METRICS = ["点赞", "收藏", "评论"]
GROUP_COLUMNS = ["内容主题", "产品系列", "产品系列/内容主题", "内容主题/产品系列"]
TYPE_COLUMNS = ["图文/视频", "内容类型"]
ALIASES = {
    "笔记标题": "标题", "内容标题": "标题",
    "发布日期": "发布时间", "发布时刻": "发布时间", "前台日期": "发布时间",
    "内容形式": "图文/视频", "笔记类型": "图文/视频",
    "点赞数": "点赞", "点赞量": "点赞", "获赞数": "点赞",
    "收藏数": "收藏", "收藏量": "收藏", "评论数": "评论", "评论量": "评论",
    "笔记正文": "正文", "内容正文": "正文", "笔记内容": "正文", "文案": "正文",
    "简介": "账号简介", "博主简介": "账号简介", "账号昵称": "账号名称", "博主名称": "账号名称",
    "笔记地址": "笔记链接", "笔记URL": "笔记链接", "选题编号": "对应选题",
}


def canonical_column(value):
    label = re.sub(r"\s+", "", str(value)).replace("／", "/") if pd.notna(value) else ""
    return FIELD_ALIASES.get(label, ALIASES.get(label, label))


def _excel_file(source):
    if isinstance(source, bytes):
        if public_mode():
            validate_upload(source)
        source = io.BytesIO(source)
    elif hasattr(source, "seek"):
        source.seek(0)
    return pd.ExcelFile(source, engine="openpyxl")


def validate_upload(contents):
    if len(contents) > 10 * 1024 * 1024:
        raise ValueError('公开演示支持最大10MB的Excel文件，请拆分后上传。')
    try:
        with ZipFile(io.BytesIO(contents)) as book:
            entries = book.infolist()
            if len(entries) > 500 or sum(item.file_size for item in entries) > 40 * 1024 * 1024:
                raise ValueError('Excel解压内容过大，请减少工作表或拆分数据。')
    except BadZipFile:
        raise ValueError('文件不是有效的xlsx工作簿，请重新另存为.xlsx。') from None


def inspect_workbook(source):
    """识别笔记标题或完整原始互动字段；排除带聚合字段的透视表。"""
    candidates = []
    with _excel_file(source) as book:
        for name in book.sheet_names:
            preview = pd.read_excel(book, sheet_name=name, header=None, nrows=30)
            for row_index, row in preview.iterrows():
                columns = [canonical_column(value) for value in row]
                aggregate = any(re.search('平均值项|求和项|计数项|汇总|总计', col) for col in columns)
                if not aggregate and ('标题' in columns or set(METRICS).issubset(columns)):
                    candidates.append({"sheet": name, "header_row": int(row_index) + 1,
                                       "has_title": "标题" in columns})
                    break
        return {"sheets": book.sheet_names, "candidates": sorted(candidates, key=lambda item: not item["has_title"])}


def prepare_data(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    df = raw.copy()
    df.columns = [canonical_column(column) for column in df.columns]
    if df.columns.duplicated().any():
        raise ValueError("表头有重复列名，请确保每个字段只有一列。")
    if '标题' not in df and not set(METRICS).issubset(df.columns):
        raise ValueError('无法识别笔记明细：请提供“标题”列，或完整的点赞、收藏、评论三列。')
    df = df.map(lambda value: pd.NA if isinstance(value, str) and not value.strip() else value).dropna(how="all")
    if df.empty:
        raise ValueError("表格没有内容数据，请在表头下方至少填写一篇笔记。")
    messages = []
    missing = [column for column in METRICS if column not in df]
    for column in missing:
        df[column] = pd.NA
    if missing:
        messages.append('未提供“'+'、'.join(missing)+'”；仍可分析现有文本，对应表现比较暂无法判断。')
    normalized = pd.DataFrame([normalize_note(note) for note in df.to_dict('records')], index=df.index)
    df['原始文本字段'] = normalized['原始文本字段']
    for column in [name for name in COUNT_FIELDS if name in df]:
        invalid = normalized[column+'精度'].eq('无效')
        if invalid.any():
            rows = '、'.join(str(int(index)+2) for index in df.index[invalid][:5])
            raise ValueError(f'“{column}”列在 Excel 第 {rows} 行有无效数据，请填写非负整数或原始缩略显示。')
        for field in [column, column+'原文', column+'数值', column+'精度']:
            df[field] = normalized[field]
        df[column] = pd.to_numeric(df[column], errors='coerce')
        imprecise = normalized[column+'精度'].isin(['近似','下界']).sum()
        missing_count = normalized[column+'精度'].eq('缺失').sum()
        if imprecise or missing_count:
            messages.append(f'“{column}”有 {imprecise} 篇缩略/下界数字、{missing_count} 篇缺失；原文和估计值保留，但不参加精确合计、均值和排行。')
    if "标题" not in df:
        df["标题"] = [f"笔记 {index + 1}" for index in range(len(df))]
        messages.append("没有“标题”列，已自动生成笔记编号。")
    else:
        df["标题"] = df["标题"].astype("string").fillna("未命名笔记")
    for column in GROUP_COLUMNS + TYPE_COLUMNS:
        if column in df:
            df[column] = df[column].astype("string").str.strip().fillna("未分类")
    if '对应选题' in df:
        df['对应选题'] = idea_labels(df['对应选题'])
    if "发布时间" in df:
        original = df["发布时间"]
        df["原始日期"] = original.astype("string")
        edited = original.astype("string").str.contains("编辑|修改|更新", na=False)
        dates = publication_dates(original).copy()
        # 部分 Excel 导出的日期是序列号，而不是带日期格式的单元格。
        numeric = original.map(lambda value: isinstance(value, (int, float)) and not isinstance(value, bool))
        if numeric.any():
            serials = pd.to_numeric(original[numeric], errors="coerce")
            dates.loc[numeric] = pd.to_datetime(serials.where(serials.between(1, 100000)), unit="D", origin="1899-12-30", errors="coerce")
        df["发布时间"] = dates
        if edited.any():
            messages.append(f"有 {int(edited.sum())} 篇仅提供编辑日期，不能代表首次发布；已保留原始日期，并从发布趋势中排除。")
        invalid_dates = dates.isna() & ~edited
        if invalid_dates.any():
            messages.append(f"有 {int(invalid_dates.sum())} 条发布时间为空或无效，仅从时间趋势图中排除，其他统计仍保留。")
    df = add_ratios(df)
    return df.reset_index(drop=True), messages


def read_excel(source, sheet_name=None, header_row=None):
    """自动识别明细工作表和前 30 行中的表头，也允许指定（行号从 1 开始）。"""
    if sheet_name is None or header_row is None:
        structure = inspect_workbook(source)
        candidates = [item for item in structure["candidates"] if sheet_name is None or item["sheet"] == sheet_name]
        if not candidates:
            raise ValueError('未找到包含标题或完整赞藏评字段的笔记明细表。请在读取设置中选择工作表和表头行。')
        sheet_name = candidates[0]["sheet"] if sheet_name is None else sheet_name
        header_row = candidates[0]["header_row"] if header_row is None else header_row
    with _excel_file(source) as book:
        content = pd.read_excel(book, sheet_name=sheet_name, header=None,
                               nrows=int(header_row) + 1001 if public_mode() else None)
    if public_mode() and len(content) - header_row > 1000:
        raise ValueError('公开演示每次最多分析1000行笔记，请拆分后上传；本地模式不受此限制。')
    if not 1 <= header_row <= len(content):
        raise ValueError("表头行超出了工作表范围，请重新选择。")
    headers = content.iloc[header_row - 1]
    populated = headers.notna() & headers.astype("string").str.strip().ne("")
    raw = content.iloc[header_row:, populated.to_numpy(dtype=bool)].copy()
    original_headers = headers[populated].tolist()
    raw.columns = original_headers
    # prepare_data 的行号计算是 index + 2，保留真实 Excel 行号供错误提示。
    raw.index = range(header_row - 1, header_row - 1 + len(raw))
    frame, messages = prepare_data(raw)
    frame.attrs["source"] = {"sheet": sheet_name, "header_row": header_row,
                             "mappings": {str(name): canonical_column(name) for name in original_headers if str(name) != canonical_column(name)}}
    return frame, messages


def summarize(df):
    result = {"总发布篇数": len(df)}
    for metric in METRICS:
        total = df[metric].sum(min_count=1)
        result[f"总{metric}"] = None if pd.isna(total) else int(total)
        result[f"平均{metric}"] = None if pd.isna(df[metric].mean()) else float(df[metric].mean())
    return result


def group_summary(df, column):
    return df.groupby(column, dropna=False).agg(
        内容数量=("标题", "size"),
        平均点赞=("点赞", "mean"),
        平均收藏=("收藏", "mean"),
        平均评论=("评论", "mean"),
    ).sort_values("平均点赞", ascending=False).reset_index()


def daily_trend(df):
    valid = df.dropna(subset=["发布时间", "点赞"])
    return valid.groupby(valid["发布时间"].dt.normalize())["点赞"].mean().rename("平均点赞").reset_index()


WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
HOUR_BANDS = ['凌晨（00–05时）', '上午（06–11时）', '中午（12–13时）',
              '下午（14–17时）', '晚间（18–21时）', '深夜（22–23时）']


def _metric_frame(df):
    """沿用清洗后的精确数值；不读取估计值，也不填补零。"""
    result = df.copy()
    for metric in METRICS:
        result[metric] = pd.to_numeric(result.get(metric, pd.Series(index=result.index, dtype=float)), errors='coerce')
        if metric+'精度' in result:
            result[metric] = result[metric].where(result[metric+'精度'].eq('精确'))
    return result


def _time_pattern(df, dimension, order):
    columns = [dimension, '篇数', *[f'{m}有效篇数' for m in METRICS], *[f'平均{m}' for m in METRICS]]
    if '发布时间' not in df or df.empty:
        return pd.DataFrame(columns=columns)
    valid = _metric_frame(df)
    valid['发布时间'] = publication_dates(valid['发布时间'])
    if '原始日期' in valid:
        edited = valid['原始日期'].astype('string').str.contains('编辑|修改|更新', na=False)
        valid.loc[edited, '发布时间'] = pd.NaT
    valid = valid.dropna(subset=['发布时间']).copy()
    if valid.empty:
        return pd.DataFrame(columns=columns)
    if dimension == '时段':
        # 日期字符串无时分时，不能把解析出的午夜当成真实发布时刻。
        original = valid.get('原始日期', df['发布时间'].reindex(valid.index))
        def has_clock(value):
            if isinstance(value, str):
                if re.fullmatch(r'\d+\.\d+', value.strip()):
                    return 1 <= float(value) <= 100000 and float(value) % 1 != 0
                return bool(re.search(r'(?:T|\s)\d{1,2}:\d{2}|\d{1,2}时', value))
            if isinstance(value, (int, float)):
                return pd.notna(value) and float(value) % 1 != 0
            return isinstance(value, (pd.Timestamp, datetime)) and pd.notna(value)
        valid = valid[original.map(has_clock)].copy()
        hours = valid['发布时间'].dt.hour
        valid[dimension] = pd.cut(hours, [-1,5,11,13,17,21,23], labels=order)
    else:
        valid[dimension] = pd.Categorical(valid['发布时间'].dt.dayofweek.map(dict(enumerate(order))), categories=order, ordered=True)
    if valid.empty:
        return pd.DataFrame(columns=columns)
    grouped = valid.groupby(dimension, observed=True, sort=True)
    result = grouped.size().rename('篇数').to_frame()
    for metric in METRICS:
        result[f'{metric}有效篇数'] = grouped[metric].count()
        result[f'平均{metric}'] = grouped[metric].mean()
    return result.reset_index()[columns]


def weekly_pattern(df):
    """按周一至周日比较首发笔记当前累计互动，排除编辑日期。"""
    return _time_pattern(df, '星期', WEEKDAYS)


def hourly_pattern(df):
    """按六个互不重叠时段比较；仅有日期、没有时刻的文本不参与。"""
    return _time_pattern(df, '时段', HOUR_BANDS)


def performance_tiers(df, metric='点赞'):
    """本账号当前精确样本的相对分层，不预测未来，也不把缺失值算作长尾。"""
    if metric not in METRICS:
        raise ValueError('分层指标须为点赞、收藏或评论。')
    frame = _metric_frame(df)
    valid = frame[metric].dropna()
    columns = ['表现层级', '篇数', '占比', *[f'{m}有效篇数' for m in METRICS], *[f'平均{m}' for m in METRICS]]
    labels = pd.Series('未参与', index=frame.index, dtype='string')
    result = {'metric':metric, 'valid_count':len(valid), 'median':valid.median(),
              'p25':valid.quantile(.25), 'p75':valid.quantile(.75), 'viral_rate':float('nan'),
              'status':'样本不足', 'summary':pd.DataFrame(columns=columns), 'labels':labels}
    if len(valid) < 4:
        return result
    mask = frame[metric].notna()
    labels.loc[mask] = '中坚'
    if result['p25'] == result['p75']:
        result['status'] = '四分位重合'
    else:
        labels.loc[mask & frame[metric].lt(result['p25'])] = '长尾'
        labels.loc[mask & frame[metric].ge(result['p75'])] = '爆款'
        result['status'] = '可分层'
        result['viral_rate'] = float(labels.eq('爆款').sum()/len(valid))
    rows = []
    for name in ['爆款','中坚','长尾']:
        part = frame[labels.eq(name)]
        if result['status']=='四分位重合' and name!='中坚':
            continue
        row = {'表现层级':name,'篇数':len(part),'占比':len(part)/len(valid)}
        for item in METRICS:
            row[f'{item}有效篇数'] = int(part[item].count())
            row[f'平均{item}'] = part[item].mean()
        rows.append(row)
    result['summary'] = pd.DataFrame(rows, columns=columns)
    return result


def account_comparison(df):
    """同一表中已命名账号的精确互动与逐篇比值均值。"""
    columns = ['账号','篇数',*[f'平均{m}' for m in METRICS], '藏赞比','评赞比',
               '点赞中位数','爆款率',*[f'{m}有效篇数' for m in METRICS], '藏赞比有效篇数','评赞比有效篇数']
    if '账号名称' not in df:
        return pd.DataFrame(columns=columns)
    frame = add_ratios(_metric_frame(df))
    names = frame['账号名称'].astype('string').str.strip()
    frame = frame[names.notna() & names.ne('') & ~names.isin(['未填写账号','未分类'])].copy()
    frame['账号名称'] = names.loc[frame.index]
    if frame['账号名称'].nunique() < 2:
        return pd.DataFrame(columns=columns)
    rows=[]
    for name, group in frame.groupby('账号名称', sort=False):
        tiers=performance_tiers(group)
        row={'账号':name,'篇数':len(group),'点赞中位数':tiers['median'],'爆款率':tiers['viral_rate']}
        for metric in METRICS:
            row[f'平均{metric}']=group[metric].mean()
            row[f'{metric}有效篇数']=int(group[metric].count())
        for ratio in ['藏赞比','评赞比']:
            row[ratio]=group[ratio].mean()
            row[ratio+'有效篇数']=int(group[ratio].count())
        rows.append(row)
    return pd.DataFrame(rows,columns=columns)


UNLINKED_IDEA = '未关联'


def idea_labels(values):
    labels = values.astype('string').str.strip()
    return labels.mask(labels.isna() | labels.str.lower().isin(
        ['', '未关联', '未分类', '待填写', '待确认', '无', 'none', 'nan', 'null', '—', '-']), UNLINKED_IDEA)


def idea_effects(df):
    """人工关联选题的表现；上四分位来自同账号全部有效笔记，避免每题自定基准。"""
    columns=['账号','对应选题','关联篇数','精确点赞篇数',*[f'平均{m}' for m in METRICS],
             '爆款篇数','爆款率','账号有效篇数','账号上四分位','分层说明']
    field=next((name for name in ['对应选题','选题编号'] if name in df),None)
    if field is None or df.empty:
        return pd.DataFrame(columns=columns)
    frame=_metric_frame(df)
    frame['对应选题']=idea_labels(frame[field])
    frame['_账号']=frame['账号名称'].astype('string').str.strip().fillna('未填写账号').replace('', '未填写账号') if '账号名称' in frame else '当前账号'
    rows=[]
    for account, sample in frame.groupby('_账号',sort=False):
        baseline=performance_tiers(sample)
        linked=sample[sample['对应选题'].ne(UNLINKED_IDEA)]
        for label, group in linked.groupby('对应选题',sort=False):
            values=group['点赞'].dropna()
            enough=baseline['status']=='可分层' and len(values)>=4
            hits=int(values.ge(baseline['p75']).sum()) if enough else float('nan')
            row={'账号':account,'对应选题':label,'关联篇数':len(group),'精确点赞篇数':len(values),
                 '爆款篇数':hits,'爆款率':hits/len(values) if enough else float('nan'),
                 '账号有效篇数':baseline['valid_count'],'账号上四分位':baseline['p75'],
                 '分层说明':'按账号统一基准' if enough else '账号无法分层或本选题精确点赞不足4篇'}
            row.update({f'平均{metric}':group[metric].mean() for metric in METRICS})
            rows.append(row)
    return pd.DataFrame(rows,columns=columns)
