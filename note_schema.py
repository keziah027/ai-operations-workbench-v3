"""三个入口共用的笔记字段与数字精度。原文/估计值与精确统计值分开保存。"""
import math
import re
import pandas as pd

COUNT_FIELDS = ['点赞', '收藏', '评论', '曝光', '观看', '涨粉', '分享', '弹幕']
THEME_FIELDS = ['内容主题', '产品系列', '产品系列/内容主题', '内容主题/产品系列', '正文话题']
PLACEHOLDERS = {'', '未分类', '未填写', '待填写', '待补', '待确认', '待判定', '其他/待确认', '未知', '未显示', '未确认', '未读取', '无', '暂无', 'nan', 'none', 'null', 'n/a', '—', '--', '-'}
FIELD_ALIASES = {
    '笔记标题':'标题', '内容标题':'标题', '笔记正文':'正文', '内容正文':'正文', '笔记内容':'正文', '文案':'正文',
    '发布日期':'发布时间', '发布时刻':'发布时间', '前台日期':'发布时间',
    '内容形式':'图文/视频', '笔记类型':'图文/视频', '内容类型':'图文/视频',
    '简介':'账号简介', '博主简介':'账号简介', '账号昵称':'账号名称', '博主名称':'账号名称',
    '笔记地址':'笔记链接', '笔记URL':'笔记链接',
    **{name+suffix:name for name in COUNT_FIELDS for suffix in ['数','量']}, '获赞数':'点赞',
}


PLACEHOLDERS.update({'未命名笔记', '未命名', '暂无内容', '待标注'})


def content_text(value):
    if isinstance(value, (list, tuple)):
        return ' '.join(filter(None, (content_text(item) for item in value)))
    value = value.strip() if isinstance(value, str) else ''
    return '' if value.lower() in PLACEHOLDERS else value


def count_info(value):
    if value is None or (not isinstance(value, (str, list, dict)) and pd.isna(value)):
        return {'raw':'', 'number':None, 'precision':'缺失', 'exact':None}
    raw = str(value).strip()
    if raw.lower() in PLACEHOLDERS:
        return {'raw':raw, 'number':None, 'precision':'缺失', 'exact':None}
    compact = re.sub(r'[,，\s]', '', raw).lower()
    match = re.fullmatch(r'(约|≈|~)?(\d+(?:\.\d+)?)(万|千|亿|w|k)?(\+|以上)?', compact)
    if not match:
        return {'raw':raw, 'number':None, 'precision':'无效', 'exact':None}
    estimate = float(match[2]) * {'万':10000,'千':1000,'亿':10**8,'w':10000,'k':1000,None:1}[match[3]]
    if not math.isfinite(estimate) or estimate > 10**12 or estimate % 1:
        return {'raw':raw, 'number':None, 'precision':'无效', 'exact':None}
    precision = '下界' if match[4] else '近似' if match[1] or match[3] else '精确'
    return {'raw':raw, 'number':int(estimate), 'precision':precision, 'exact':int(estimate) if precision=='精确' else None}


def normalize_note(original):
    note = dict(original)
    for field, value in original.items():
        key = re.sub(r'\s+', '', str(field)).replace('／','/')
        canonical = FIELD_ALIASES.get(key, key)
        if canonical not in note or not content_text(note.get(canonical)) and isinstance(value, str):
            note[canonical] = value
    if '原始文本字段' not in note:
        note['原始文本字段'] = {field:value for field,value in original.items()
                            if FIELD_ALIASES.get(field,field) in ['标题','正文','账号简介',*THEME_FIELDS]}
    for field in ['标题','正文','账号简介']:
        note[field] = content_text(note.get(field))
    for field in THEME_FIELDS:
        note.setdefault(field, '')
    note['主题文本'] = '；'.join(dict.fromkeys(filter(None, (content_text(note[field]) for field in THEME_FIELDS))))
    note['图文/视频'] = content_text(note.get('图文/视频'))
    note['内容形式'] = note['图文/视频']
    for metric in COUNT_FIELDS:
        raw = note.get(metric)
        for field in [metric+'原文', '后台'+metric+'显示', '前台'+metric+'显示']:
            if field in note and isinstance(note[field],str) and note[field].strip():
                raw = note[field]
                break
        info = count_info(raw)
        hint = content_text(note.get(metric+'精度'))
        if hint in ['近似','下界','缺失','无效'] and info['precision']=='精确':
            info.update(precision=hint, exact=None)
        note[metric+'原文'], note[metric+'数值'], note[metric+'精度'] = info['raw'], info['number'], info['precision']
        note[metric] = info['exact']
    return note


def normalize_notes(notes):
    return [normalize_note(note) for note in notes]


def publication_dates(values):
    values = pd.Series(values)
    edited = values.astype('string').str.contains('编辑|修改|更新', na=False)
    # 保留来源的本地日历日期，不把午夜的东八区日期转换到前一天。
    def parse(value):
        try:
            stamp=pd.Timestamp(value)
            return stamp.tz_localize(None) if stamp.tzinfo else stamp
        except (ValueError,TypeError):
            return pd.NaT
    return pd.to_datetime(values.mask(edited).map(parse),errors='coerce')
