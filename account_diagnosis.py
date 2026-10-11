"""按用户确认的账号类型选择诊断重点；观察与建议分列。"""
import re
import pandas as pd
from account_profile import INSUFFICIENT
from dynamic_topics import OTHER
from profile_axes import commerce_context

RULES = {
    "新品与产品展示": (r"新品|上新|新款|预售|产品|商品|材质|规格|试用|展示", "核对产品利益点与实际展示是否一致。"),
    "种草表达": (r"推荐|测评|试用|体验|实测|好用|对比|适合", "结合使用条件、优缺点和证据复核推荐理由。"),
    "商品承接": (r"下单|购买|商品链接|商品卡|店铺|橱窗", "人工核对笔记到商品的可达路径；需后台点击、订单数据才能评估转化。"),
    "人设与经历": (r"我曾|我在|我的经历|作为|从业|主理人|创始人|复盘|亲历|经历", "检查不同笔记的身份、经历与价值主张是否一致。"),
    "专业认知": (r"原理|分析|案例|研究|方法|复盘|数据|经验|观点", "核对论证、适用条件与真实案例，不把术语出现当作专业能力证明。"),
    "信任建立线索": (r"来源|参考|研究|案例|实测|过程|资质|从业|论文|对比|失败", "核实可追溯证据；是否建立信任还需用户反馈或长期行为数据。"),
    "知识价值线索": (r"原理|解释|方法|步骤|清单|案例|知识|科普|解读|参考|概念", "检查是否解决具体问题、说明边界并提供可核对的知识依据。"),
    "场景表达": (r"通勤|下班|上班|周末|独居|旅行|约会|在家|办公室|面试|聚会|睡前", "比较不同场景中的内容表现，再用相近选题验证。"),
    "情绪价值线索": (r"治愈|开心|难过|松弛|焦虑|孤独|快乐|幸福|共鸣|安慰", "结合评论反馈核对是否产生共鸣；情绪词本身不等于情绪价值。"),
    "使用与测评": (r"测评|使用|实测|试色|成分|肤质|妆容|对比", "检查肤质、条件、使用过程和结果证据是否完整。"),
    "风格与人群": (r"穿搭|搭配|风格|小个子|梨形|通勤|学生|身材|显瘦", "核对穿搭建议的适用人群与场景，不据此推测真实粉丝身材。"),
    "职场问题": (r"面试|简历|求职|领导|沟通|升职|汇报|跳槽|加薪|同事", "观察具体问题是否被解决，并补充行业、岗位和适用边界。"),
    "地点与体验": (r"探店|地址|路线|交通|体验|环境|价格|排队|营业", "检查地点、价格、体验条件是否充分，记录时效。"),
    "到店承接": (r"地址|导航|预约|到店|团购|门店|营业时间", "核对地点与预约路径；需要到店或核销数据才能判断效果。"),
    "行动引导": (r"关注|评论|收藏|私信|预约|咨询|阅读|下载", "先确认运营目标，再核对引导动作是否与内容价值一致。"),
    "咨询承接": (r"咨询|私信|预约|服务|方案|联系", "核对咨询入口和服务说明；线索数量与成交需单独提供数据。"),
}


def focus_for(selection, frame):
    identity, domains, goals = selection['identity'], selection['domains'], selection['goals']
    focus=['选题结构']
    if identity=='个人创作者':
        focus += ['人设与经历','专业认知','信任建立线索']
    domain_focus={'MBTI':['知识价值线索'],'知识':['知识价值线索'],'职场':['职场问题','专业认知'],
                  '美妆':['使用与测评','信任建立线索'],'穿搭':['风格与人群'],'生活方式':['场景表达','情绪价值线索'],
                  '本地生活':['地点与体验','场景表达'],'文创手作':['使用与测评']}
    for domain in domains:
        focus += domain_focus.get(domain,[])
    if '收藏沉淀' in goals: focus.append('收藏倾向')
    if '涨粉' in goals: focus.append('涨粉表现')
    if '咨询' in goals: focus.append('咨询承接')
    if '到店' in goals: focus.append('到店承接')
    if commerce_context(frame.to_dict('records'), goals)['enabled']:
        focus += ['新品与产品展示','种草表达','商品承接']
    return list(dict.fromkeys(focus))


def _legacy_diagnose(frame, selection, summary):
    rows = []
    documents = frame['标题'].fillna('') + '\n' + frame['正文'].fillna('')
    available = documents.str.strip().ne('')
    for focus in focus_for(selection, frame):
        conclusion, evidence, advice = INSUFFICIENT, '缺少足够可比较记录', '补充笔记文本和对应互动数据后再判断。'
        if focus == '选题结构':
            usable = summary[(summary['主支柱'] != OTHER) & (summary['篇数'] >= 2)].sort_values('篇数', ascending=False)
            if len(frame) >= 6 and len(usable) >= 2:
                first = usable.iloc[0]
                conclusion = f"本次样本最多的内容支柱为「{first['主支柱']}」，{first['篇数']}篇，占{first['占比（%）']:.1f}%。"
                evidence = '；'.join(f"{row['主支柱']}：{row['篇数']}篇" for _, row in usable.iterrows())
                advice = '结合定位复核主题命名，再比较各支柱的收藏、评论表现；占比高不等于效果好。'
        elif focus == '涨粉表现':
            valid = frame.dropna(subset=['每千次观看涨粉'])
            if len(valid)>=3:
                conclusion=f"{len(valid)}篇分子分母精确且口径一致的笔记，平均每千次观看涨粉 {valid['每千次观看涨粉'].mean():.2f}。"
                evidence=f"本次共{len(frame)}篇，排除{len(frame)-len(valid)}篇；按单篇比值平均，不是全账号涨粉转化率。"
                advice='结合内容形式和首发日期比较；同篇观看与涨粉需覆盖一致统计范围。'
        elif focus in ['收藏倾向', '互动表现']:
            metric, count = ('藏赞比', '藏赞比有效篇数') if focus == '收藏倾向' else ('平均点赞', '点赞有效篇数')
            eligible = summary[(summary[count] >= 3) & (summary['主支柱'] != OTHER)].dropna(subset=[metric]).sort_values(metric, ascending=False)
            if len(eligible) >= 2:
                first, last = eligible.iloc[0], eligible.iloc[-1]
                fmt = lambda value: f'{value:.1%}' if metric == '藏赞比' else f'{value:.2f}'
                conclusion = (f"「{first['主支柱']}」的{metric}为{fmt(first[metric])}，"
                              f"「{last['主支柱']}」为{fmt(last[metric])}；仅为本次样本的描述性比较。")
                evidence = f"对应有效篇数 {int(first[count])} 与 {int(last[count])}；每组至少3篇。"
                advice = '用相近发布时间、形式和选题继续验证；收藏/点赞不是曝光转化率，也不能证明内容质量或因果关系。'
        else:
            pattern, advice = RULES[focus]
            selected = frame[documents.str.contains(pattern, regex=True, flags=re.I)]
            body_count=int(frame['正文'].ne('').sum())
            if available.sum() >= 3 and len(selected) >= 2 and body_count>=3:
                conclusion = f"{len(selected)}/{int(available.sum())}篇有效文本出现相关表达；仅确认可见线索。"
                evidence = '；'.join(f"第{row['序号']}篇「{row['标题']}」：" + '、'.join(dict.fromkeys(re.findall(pattern, row['标题']+'\n'+row['正文'], flags=re.I)))
                                   for _, row in selected.head(3).iterrows())
            else:
                evidence = f'有效文本 {int(available.sum())} 篇，正文 {body_count} 篇，相关表达 {len(selected)} 篇；完整诊断需至少3篇正文及2篇线索。只有标题时仅作初步标题分析。'
        rows.append({'分析重点': focus, '观察结论': conclusion, '依据与范围': evidence, '建议核对': advice})
    if selection['identity'] in ['待确认', '其他'] and not selection['domains']:
        rows.insert(0, {'分析重点': '账号定位', '观察结论': INSUFFICIENT, '依据与范围': '账号类型尚未明确',
                        '建议核对': '补充账号简介或确认身份与领域，诊断重点会随之更新。'})
    if not selection['goals']:
        rows.append({'分析重点':'运营目标','观察结论':'尚未由用户确认，不推断涨粉、销售或到店意图。',
                     '依据与范围':'商品文字线索只启用线索核对，不等同于目标确认。','建议核对':'在账号画像中选择实际运营目标。'})
    return pd.DataFrame(rows)


def diagnose(frame, selection, summary):
    from diagnosis_evidence import enrich_diagnoses
    return enrich_diagnoses(frame,selection,_legacy_diagnose(frame,selection,summary))
