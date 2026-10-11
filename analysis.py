"""Excel 清洗与基础统计。与网页分开，方便检查计算结果。"""

import io
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
    "笔记地址": "笔记链接", "笔记URL": "笔记链接",
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
