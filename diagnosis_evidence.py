"""最终分类上的描述性比较；展示均值、中位数、样本与可复核实验。"""
import pandas as pd
from note_schema import publication_dates
from dynamic_topics import OTHER

INSUFFICIENT='当前数据不足，暂无法判断'
ANALYSIS_GOALS=['内容结构优化','收藏沉淀','评论互动','涨粉','商品承接']
FORMULAS={'点赞':'单篇精确点赞数','藏赞比':'单篇收藏÷点赞；点赞须为正，逐篇比值再取均值/中位数',
          '评赞比':'单篇评论÷点赞；点赞须为正，逐篇比值再取均值/中位数',
          '每千次观看涨粉':'单篇涨粉÷观看×1000；精确且同口径，观看须为正'}

def eligible_groups(frame,metric):
    valid=frame[~frame['主支柱'].isin([OTHER,'其他','待判定'])].dropna(subset=[metric])
    return [(name,group) for name,group in valid.groupby('主支柱',sort=False) if len(group)>=3]

def controlled_sample(frame,metric):
    data=frame.copy()
    data['_month']=publication_dates(data['发布时间']).dt.strftime('%Y-%m')
    data['_form']=data['内容形式'].replace('',None)
    for fields,description in [(['_month','_form'],'同首发月份、同内容形式'),(['_form'],'同内容形式'),(['_month'],'同首发月份')]:
        pools=[]
        for label,group in data.dropna(subset=fields).groupby(fields,sort=True):
            if len(eligible_groups(group,metric))>=2: pools.append((len(group),str(label),group))
        if pools:
            _,label,selected=max(pools,key=lambda item:(item[0],item[1]))
            return selected,description+'：'+label, '仍未控制选题难度、笔记存续时间及分发环境；不是因果或稳定规律。'
    return data,'本次全部样本中满足条件的记录','无法组成同形式/同月份的足量对照；发布时间、形式和分发差异可能影响结果。'

def metric_diagnosis(frame,metric):
    selected,scope,limitation=controlled_sample(frame,metric)
    groups=eligible_groups(selected,metric)
    base={'诊断主题':metric+'的支柱比较','观察类型':'指标描述性比较','观察结果':INSUFFICIENT,
          '证据笔记':'','样本范围与有效数量':f'本次{len(frame)}篇；{metric}有效{frame[metric].count()}篇；每组至少3篇',
          '比较指标和计算口径':FORMULAS[metric],'实际差异':'暂不可比较','局限或待确认因素':limitation,
          '下一步动作':'补充至少两个最终支柱、每组至少3篇有效记录，核对精确数字及分母口径。',
          '验证指标与复盘条件':'补齐后重新比较'+metric+'的均值、中位数和有效篇数。',
          '比较指标':metric,'甲组':'','乙组':'','甲组有效数':0,'乙组有效数':0,
          '甲组均值':None,'乙组均值':None,'甲组中位数':None,'乙组中位数':None,'均值差':None,'中位数差':None}
    if len(groups)<2: return base
    groups.sort(key=lambda pair:(pair[1][metric].mean(),str(pair[0])),reverse=True)
    (name_a,a),(name_b,b)=groups[0],groups[-1]
    mean_a,mean_b=float(a[metric].mean()),float(b[metric].mean())
    median_a,median_b=float(a[metric].median()),float(b[metric].median())
    mean_diff,median_diff=mean_a-mean_b,median_a-median_b
    base.update({'甲组':name_a,'乙组':name_b,'甲组有效数':len(a),'乙组有效数':len(b),
        '甲组均值':mean_a,'乙组均值':mean_b,'甲组中位数':median_a,'乙组中位数':median_b,'均值差':mean_diff,'中位数差':median_diff,
        '样本范围与有效数量':f'{scope}；本次{len(frame)}篇；比较子样本{len(selected)}篇；甲组{len(a)}篇、乙组{len(b)}篇；其他组未纳入这对比较。',
        '证据笔记':'；'.join(f"{row['主支柱']} 第{row['序号']}篇：{row['标题']} {row.get('笔记链接','')}" for _,row in pd.concat([a,b]).iterrows()),
        '实际差异':f'甲减乙均值差 {mean_diff:.4g}；中位数差 {median_diff:.4g}（比值按小数记录）',
        '观察结果':f'「{name_a}」均值{mean_a:.4g}、中位数{median_a:.4g}；「{name_b}」均值{mean_b:.4g}、中位数{median_b:.4g}。'})
    if mean_diff==0 and median_diff==0:
        base['观察结果']+='当前样本未观察到差异，不能据此确定优劣。'
        base['下一步动作']='继续补充同形式、相近发布时段的记录；当前不据此改变内容配比。'
    else:
        base['下一步动作']=f'小规模实验：围绕「{name_a}」与「{name_b}」各安排3篇；保持同形式、相近发布时段与观察时长，交替发布；先记录选题和包装差异。'
        base['验证指标与复盘条件']=f'两组都达到3篇且每篇发布满7天后，记录{metric}均值、中位数和样本量；同时核对赞藏评及异常高值。不能预先承诺增长。'
        base['局限或待确认因素']+=' 本次按均值挑选高低组，存在选择偏差，实验需使用新增样本验证。'
        if mean_diff*median_diff<=0:
            base['局限或待确认因素']+=' 均值与中位数方向不一致或中位数无差异，优先检查单篇高值。'
    return base

def enrich_diagnoses(frame,selection,legacy):
    goals=list(dict.fromkeys(selection.get('analysis_goals',[])+selection.get('goals',[])))
    wanted=[]
    mapping={'内容结构优化':'点赞','收藏沉淀':'藏赞比','评论互动':'评赞比','涨粉':'每千次观看涨粉'}
    for goal in goals:
        if goal in mapping: wanted.append(mapping[goal])
    rows=[metric_diagnosis(frame,metric) for metric in dict.fromkeys(wanted)]
    for record in legacy.to_dict('records'):
        insufficient=record['观察结论']==INSUFFICIENT
        rows.append({'诊断主题':record['分析重点'],'观察类型':'数据待补' if insufficient else '文本线索观察' if record['分析重点'] not in ['选题结构','涨粉表现','收藏倾向'] else '指标描述性观察',
                     '观察结果':record['观察结论'],'证据笔记':record['依据与范围'],
                     '样本范围与有效数量':f'本次{len(frame)}篇；正文{frame["正文"].ne("").sum()}篇；'+record['依据与范围'],
                     '比较指标和计算口径':'见观察中的有效样本口径；文字线索不能证明效果',
                     '实际差异':'未进行组间量化比较','局限或待确认因素':'只描述已读内容；未读正文/封面不作为无特征；不能据此推断信任、因果或成交。',
                     '下一步动作':('补数/核对：'+record['依据与范围']) if insufficient else record['建议核对'],
                     '验证指标与复盘条件':'补齐对应字段并逐篇复核原文后重新判断；没有足量对照不做效果承诺。'})
    if '商品承接' in goals or '销售' in goals:
        rows.append({'诊断主题':'商品效果数据缺口','观察类型':'数据待补','观察结果':INSUFFICIENT,
                     '证据笔记':'当前明细仅有内容与可见承接线索','样本范围与有效数量':f'本次{len(frame)}篇；缺少同口径商品点击、订单或核销明细',
                     '比较指标和计算口径':'未定义成交率分母时不计算','实际差异':'暂不可比较','局限或待确认因素':'存在入口不等于成交',
                     '下一步动作':'先核对商品入口是否可达，再补充同周期点击与成交记录。','验证指标与复盘条件':'取得明确分子、分母和时间范围后再评估商品承接效果。'})
    for row in rows:
        row.update({'分析重点':row['诊断主题'],'观察结论':row['观察结果'],'依据与范围':row['样本范围与有效数量'],'建议核对':row['下一步动作']})
    return pd.DataFrame(rows)
