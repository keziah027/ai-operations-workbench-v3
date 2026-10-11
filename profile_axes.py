"""身份、内容领域、运营目标相互独立；目标不自动勾选。"""
import itertools
import re
import pandas as pd
from note_schema import content_text, normalize_notes

UNKNOWN = '待确认'
INSUFFICIENT = '当前数据不足，暂无法判断'
IDENTITIES = ['品牌', '个人创作者', '机构', '其他', UNKNOWN]
DOMAINS = ['MBTI', '知识', '职场', '美妆', '穿搭', '生活方式', '本地生活', '文创手作', '其他']
GOALS = ['涨粉', '收藏沉淀', '销售', '咨询', '到店']
MBTI = [''.join(chars).lower() for chars in itertools.product('IE', 'NS', 'TF', 'JP')]
IDENTITY_RULES = {
    '品牌':['官方品牌','品牌官方','旗舰店','自有品牌','原创品牌','品牌主理人','我们品牌','品牌直营'],
    '个人创作者':['博主','个人创作者','主理人','咨询师','设计师','我的经历','我曾','我在','我从','独立创作'],
    '机构':['机构','工作室','研究院','学校','协会','培训中心','官方机构'],
}
DOMAIN_RULES = {
    'MBTI':['mbti','人格','八维',*MBTI],
    '知识':['知识','科普','原理','心理学','认知','解读','学习','历史','科学','读书'],
    '职场':['职场','面试','简历','求职','升职','领导','同事','汇报','打工人','跳槽','应届生'],
    '美妆':['美妆','护肤','妆容','化妆','口红','粉底','防晒','敏感肌','眼影'],
    '穿搭':['穿搭','搭配','ootd','显瘦','衣橱','小个子','连衣裙'],
    '生活方式':['生活','日常','独居','家居','旅行','露营','周末','治愈','vlog'],
    '本地生活':['探店','同城','到店','团购','周边游','餐厅','咖啡店','门店'],
    '文创手作':['文创','造景','贴纸','拼贴','微缩','手账','胶带','手作'],
}


def clean(value):
    return content_text(value)


def usable_title(value):
    value = clean(value)
    return '' if re.fullmatch(r'笔记\s*\d+|未命名笔记', value) else value


def note_text(note):
    return '\n'.join(filter(None, [usable_title(note.get('标题')), clean(note.get('正文')), clean(note.get('主题文本'))]))


def hits(value, words):
    value = clean(value).lower()
    return [word for word in words if (re.search(r'(?<![a-z])'+re.escape(word)+r'(?![a-z])',value) if word.isascii() else word in value)]


def evidence_table(notes, bio, rules, axis):
    documents = [note_text(note) for note in notes]
    available = sum(bool(doc.strip()) for doc in documents)
    rows = []
    for category, words in rules.items():
        bio_hits = hits(bio, words)
        matches = [(i+1, note.get('标题',''), hits(doc,words)) for i,(note,doc) in enumerate(zip(notes,documents)) if hits(doc,words)]
        vocabulary = set(bio_hits+[word for _,_,terms in matches for word in terms])
        score = .45*min(len(bio_hits)/2,1)+.4*len(matches)/max(available,1)+.15*min(len(vocabulary)/4,1)
        supported = bool(bio_hits) or len(matches)>=2
        level = '高' if supported and available>=8 and score>=.6 else '中' if supported and available>=3 else '低'
        rows.append({'维度':axis,'候选':category,'证据强度':round(score,3),'置信度':level,'有依据':supported,
                     '命中笔记数':len(matches),'简介依据':'、'.join(bio_hits) or '无', '文本依据':'、'.join(sorted(vocabulary)),
                     '例证':'；'.join(f'第{i}篇：{title}' for i,title,_ in matches[:3])})
    return pd.DataFrame(rows).sort_values('证据强度',ascending=False,kind='stable').reset_index(drop=True)


def identify_account(notes, bio=''):
    notes = normalize_notes(notes)
    identities = evidence_table(notes,bio,IDENTITY_RULES,'身份')
    domains = evidence_table(notes,bio,DOMAIN_RULES,'领域')
    best = identities.iloc[0]
    identity = best['候选'] if best['有依据'] and best['证据强度']>=.23 else UNKNOWN
    # 身份证据接近时保留待确认，不强行把机构/品牌/个人混为一个类型。
    if best['证据强度'] and best['证据强度']-identities.iloc[1]['证据强度']<.06:
        identity = UNKNOWN
    chosen = domains[domains['有依据'] & domains['证据强度'].ge(.2)]['候选'].tolist()
    return {'identity':identity, 'identity_confidence':best['置信度'] if identity!=UNKNOWN else '低',
            'domains':chosen,'goals':[], 'candidates':pd.concat([identities,domains],ignore_index=True).drop(columns='有依据'),
            'reason':f'身份初判：{identity}；领域线索：'+('、'.join(chosen) or '待确认')+'。运营目标须由用户选择确认。',
            'method':'本地词汇证据初判；置信度为证据强弱，未经标定，不代表预测概率。身份、领域与目标独立。',
            'text_count':sum(bool(note_text(n).strip()) for n in notes), 'body_count':sum(bool(clean(n.get('正文'))) for n in notes)}


def commerce_context(notes, goals):
    evidence = []
    for i,note in enumerate(normalize_notes(notes),1):
        terms = hits(note_text(note), ['购买','下单','店铺','橱窗','商品卡','商品链接','预售'])
        links = note.get('可见商品入口')
        if isinstance(links,list) and any(isinstance(link,dict) and link.get('url') for link in links):
            terms.append('可见商品入口')
        if terms:
            evidence.append({'序号':i,'标题':note.get('标题',''),'商品承接依据':'、'.join(terms),'笔记链接':note.get('笔记链接','')})
    return {'enabled':'销售' in goals or bool(evidence),
            'reason':'用户确认销售目标' if '销售' in goals else '检测到实际商品承接线索（不代表已确认销售目标）' if evidence else '无销售目标或已读商品承接线索',
            'evidence':pd.DataFrame(evidence,columns=['序号','标题','商品承接依据','笔记链接'])}
