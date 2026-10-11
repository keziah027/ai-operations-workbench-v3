"""按字段完整度计算表现；只采用同篇、同口径的精确分子分母。"""
import pandas as pd
from note_schema import COUNT_FIELDS, publication_dates

RATIOS = {'藏赞比':('收藏','点赞',1), '评赞比':('评论','点赞',1),
          '观看曝光比':('观看','曝光',1), '每千次观看涨粉':('涨粉','观看',1000)}


def scope_matches(frame, numerator, denominator):
    mask = pd.Series(True, index=frame.index)
    for suffix in ['统计周期','统计口径']:
        left, right = numerator+suffix, denominator+suffix
        if left in frame or right in frame:
            a = frame.get(left,pd.Series('',index=frame.index)).fillna('').astype(str)
            b = frame.get(right,pd.Series('',index=frame.index)).fillna('').astype(str)
            mask &= a.eq(b)
    return mask


def add_ratios(frame):
    for name,(numerator,denominator,multiple) in RATIOS.items():
        if numerator not in frame or denominator not in frame:
            frame[name]=float('nan')
            continue
        frame[numerator]=pd.to_numeric(frame[numerator],errors='coerce')
        frame[denominator]=pd.to_numeric(frame[denominator],errors='coerce')
        eligible = frame[denominator].gt(0) & scope_matches(frame,numerator,denominator)
        frame[name] = multiple*frame[numerator]/frame[denominator].where(eligible)
    return frame


def sample_audit(frame, metric):
    fields = ['点赞','收藏','评论'] if metric=='互动总量' else list(RATIOS[metric][:2]) if metric in RATIOS else [metric]
    rows=[]
    for _,note in frame.iterrows():
        reasons=[]
        for field in fields:
            precision=note.get(field+'精度','缺失' if pd.isna(note.get(field)) else '精确')
            if precision!='精确' or pd.isna(note.get(field)):
                reasons.append(f"{field}：{precision}（原文：{note.get(field+'原文') or '空'}）")
        if metric in RATIOS:
            numerator,denominator,_=RATIOS[metric]
            if pd.notna(note[denominator]) and note[denominator]<=0:
                reasons.append(denominator+'为0，无有效分母')
            if not scope_matches(frame.loc[[note.name]],numerator,denominator).iloc[0]:
                reasons.append('分子分母的统计周期/口径不一致或只提供一侧')
        included=pd.notna(note.get(metric))
        rows.append({'序号':note['序号'],'标题':note['标题'],'比较指标':metric,'是否纳入':'是' if included else '否',
                     '纳入/排除依据':'所需数字精确，分母与口径有效' if included else '；'.join(reasons) or '该指标缺失',
                     '笔记链接':note.get('笔记链接','')})
    return pd.DataFrame(rows)


def coverage_table(frame):
    rows=[{'分析所需数据':'标题','有效篇数':int(frame['标题'].ne('').sum()),'本次篇数':len(frame),'可支持分析':'初步选题、标题表达；不能判断正文与完整运营链路'},
          {'分析所需数据':'正文','有效篇数':int(frame['正文'].ne('').sum()),'本次篇数':len(frame),'可支持分析':'补充主题、正文结构和表达分析'}]
    rows += [{'分析所需数据':'内容形式','有效篇数':int(frame['内容形式'].ne('').sum()),'本次篇数':len(frame),'可支持分析':'图文/视频等形式对比'},
             {'分析所需数据':'首发日期','有效篇数':int(publication_dates(frame['发布时间']).count()),'本次篇数':len(frame),'可支持分析':'按首发日期比较当前累计表现，不是每日新增'}]
    for metric in COUNT_FIELDS+list(RATIOS):
        rows.append({'分析所需数据':metric,'有效篇数':int(frame[metric].count()),'本次篇数':len(frame),
                     '可支持分析':'仅有效记录；原文中的近似、下界、缺失不参与精确比较'})
    return pd.DataFrame(rows)


def performance_groups(frame, field):
    if field not in frame:
        return pd.DataFrame()
    data=frame.copy()
    if field=='发布日期':
        data[field]=publication_dates(data['发布时间']).dt.date
    data=data[data[field].notna() & data[field].astype(str).str.strip().ne('')]
    rows=[]
    for label,group in data.groupby(field,sort=False):
        row={field:label,'篇数':len(group)}
        for metric in ['曝光','观看','涨粉',*RATIOS]:
            row['平均'+metric]=group[metric].mean()
            row[metric+'有效篇数']=int(group[metric].count())
        rows.append(row)
    return pd.DataFrame(rows)


def backend_tables(frame):
    return {'数据完整度':coverage_table(frame),
            '后台支柱表现':performance_groups(frame,'主支柱'),
            '内容形式表现':performance_groups(frame,'内容形式'),
            '发布时间表现':performance_groups(frame.assign(发布日期=publication_dates(frame['发布时间']).dt.date),'发布日期')}
