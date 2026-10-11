"""可复核的公共账号拆解。仅使用已读取文本和人工标注，不调用外部 AI。"""
import math
import re
from urllib.parse import urlsplit

import pandas as pd

from dynamic_topics import discover_topics, OTHER
from content_features import detect_features, FEATURE_PATTERNS
from account_profile import usable_title
from note_schema import normalize_notes, COUNT_FIELDS
from performance import add_ratios
from packaging_analysis import DEFAULT_COVERS, tags
from result_cache import BoundedCache

TEXT_CACHE=BoundedCache(max_entries=512,max_bytes=8*1024*1024)

# 兼容旧调用；实际分类选项来自本次语料，不再预设主题。
PILLARS = [OTHER]
COVERS = DEFAULT_COVERS
COMMERCE = {
    "商品提及": ["新品", "商品", "产品", "新款", "套装", "周边"],
    "购买引导": ["购买", "下单", "入手", "抢购", "拍下", "加购", "预售", "上架"],
    "店铺/橱窗": ["店铺", "橱窗", "小黄车", "购物车", "商品链接", "商品卡", "主页链接", "淘宝"],
    "私信承接": ["私信", "私聊", "私戳"],
    "评论承接": ["评论区", "评论留言", "留言领取", "扣1", "扣 1"],
}


def text(value):
    return value.strip() if isinstance(value, str) else ""


def matches(value, words):
    lowered = value.lower()
    return [word for word in words if word in lowered]


def infer_pillar(title, body):
    result = discover_topics([{"标题": title, "正文": body}])
    return result["assignments"][0], result["evidence"][0]


def title_features(title):
    return list(detect_features(title)) or ["未命中特定句式"]


def body_structure(body):
    if not body:
        return "未读取正文", "", ""
    paragraphs = [part.strip() for part in re.split(r"\n+", body) if part.strip()]
    sequence = []
    for part in paragraphs:
        if part.startswith("#"):
            role = "话题标签"
        elif matches(part, ["购买", "下单", "加购", "店铺", "橱窗", "私信"]):
            role = "行动/承接提示"
        elif matches(part, ["评论", "留言", "关注", "收藏", "点赞", "投票"]):
            role = "互动提示"
        elif re.match(r"^(?:第[一二三四五六七八九十\d]+步|[1-9][、.．）)])", part):
            role = "步骤/清单"
        else:
            role = "内容段落"
        if not sequence or sequence[-1] != role:
            sequence.append(role)
    return ('未识别特定结构' if sequence==['内容段落'] else " → ".join(sequence)), paragraphs[0][:180], paragraphs[-1][:180]


def safe_link(value, image=False):
    try:
        parts = urlsplit(text(value))
        if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password or parts.port not in (None, 80, 443):
            return ""
        if image and not (parts.hostname.endswith(".xhscdn.com") or parts.hostname == "xhscdn.com"):
            return ""
        return value
    except ValueError:
        return ""


def build_annotations(notes, topics=None):
    notes = normalize_notes(notes)
    topics = topics if topics is not None else discover_topics(notes)
    rows = []
    for index, note in enumerate(notes):
        title, body = usable_title(note.get("标题")), text(note.get("正文"))
        pillar, reason = topics["assignments"][index], topics["evidence"][index]
        rows.append({"序号": index + 1, "标题": title, "主支柱": pillar,
                     "分类依据": reason, "分类置信度": topics["confidence"][index], "封面类型": "待标注", "封面观察": "",
                     "价值/服务（人工确认）": "",
                     "商品/系列（人工确认）": "", "承接位置（人工确认）": "",
                     '主题ID':topics.get('assignment_ids',['other']*len(notes))[index],
                     '自动主题ID':topics.get('assignment_ids',['other']*len(notes))[index],
                     '自动主支柱':pillar,'自动分类依据':reason,'最终分类来源':'自动初判'})
    return pd.DataFrame(rows)


def build_detail(notes, annotations):
    notes = normalize_notes(notes)
    rows = []
    for index, note in enumerate(notes):
        title, body = usable_title(note.get("标题")), text(note.get("正文"))
        label = annotations.iloc[index]
        def analyze_text():
            return {'features':detect_features(title,body),'title_features':title_features(title),
                    'body_features':list(detect_features('',body)), 'structure':body_structure(body),
                    'signals':{name:matches(title+'\n'+body,words) for name,words in COMMERCE.items()}}
        from deployment import public_mode
        if public_mode():
            from result_cache import session_cache
            cache = session_cache('text')
        else:
            cache = TEXT_CACHE
        cached=cache.get('text-v1',[title,body],analyze_text)
        features=cached['features']; structure,opening,ending=cached['structure']; signals=cached['signals']
        entries = note.get('可见商品入口')
        visible = [entry for entry in (entries if isinstance(entries, list) else []) if isinstance(entry, dict) and safe_link(entry.get("url"))]
        rows.append({**note, **label.to_dict(), "发布时间":note.get('发布时间'), "序号": index + 1, "标题": title, "主支柱": label["主支柱"], "封面类型": label["封面类型"],
                     "封面观察": text(label["封面观察"]), "标题特征": "、".join(cached['title_features']), '正文特征':'、'.join(cached['body_features']), "标题字数": len(title),
                     "内容特征": "、".join(features), "特征依据": "；".join(f"{name}【{proof}】" for name, proof in features.items()),
                     "分类依据": text(label.get("分类依据")), "分类置信度": text(label.get("分类置信度")),
                     "正文": body, "正文结构": structure, "开头摘录": opening, "结尾摘录": ending,
                     "正文段数": len([p for p in body.splitlines() if p.strip()]) if body else None,
                     "笔记链接": safe_link(note.get("笔记链接")), "封面链接": safe_link(note.get("封面链接"), image=True),
                     **{metric: note.get(metric) for metric in ["点赞", "收藏", "评论"]},
                     **{name: "、".join(hits) for name, hits in signals.items()},
                     "可见入口数": len(visible), "可见入口": visible,
                     "商品/系列（人工确认）": text(label["商品/系列（人工确认）"]),
                     "价值/服务（人工确认）": text(label.get("价值/服务（人工确认）")),
                     "承接位置（人工确认）": text(label["承接位置（人工确认）"])})
    df = pd.DataFrame(rows)
    for metric in COUNT_FIELDS:
        df[metric] = pd.to_numeric(df[metric], errors="coerce")
    df["互动总量"] = df[["点赞", "收藏", "评论"]].sum(axis=1, min_count=3)
    return add_ratios(df)


def pillar_summary(df):
    rows = []
    for label in df["主支柱"].drop_duplicates():
        group = df[df["主支柱"] == label]
        rows.append({"主支柱": label, "篇数": len(group), "占比（%）": round(len(group) / len(df) * 100, 2),
                     "平均点赞": group["点赞"].mean(), "平均收藏": group["收藏"].mean(), "平均评论": group["评论"].mean(),
                     "点赞有效篇数": int(group["点赞"].count()), "收藏有效篇数": int(group["收藏"].count()), "评论有效篇数": int(group["评论"].count()),
                     "藏赞比": group["藏赞比"].mean(), "评赞比": group["评赞比"].mean(),
                     "藏赞比有效篇数": int(group["藏赞比"].count()), "评赞比有效篇数": int(group["评赞比"].count())})
    return pd.DataFrame(rows)


def audience_signals(df, bio):
    from audience_analysis import audience_candidates
    return audience_candidates(df,bio)


def high_interaction(df, metric):
    valid = df.dropna(subset=[metric]).sort_values(metric, ascending=False, kind="stable")
    size = max(1, math.ceil(len(valid) * 0.25)) if len(valid) else 0
    top, rest = valid.head(size), valid.iloc[size:]
    rows = []
    if len(valid) >= 8 and valid[metric].nunique() > 1:
        features = [(f"支柱：{label}", df["主支柱"].eq(label)) for label in df["主支柱"].unique() if label not in [OTHER, "待判定"]]
        features += [(f"封面：{label}", df["封面类型"].eq(label)) for label in df['封面类型'].dropna().unique() if label not in ['', '待标注']]
        if '封面辅助标签' in df:
            values=list(dict.fromkeys(tag for value in df['封面辅助标签'] for tag in tags(value)))
            features += [('辅助标签：'+tag,df['封面辅助标签'].map(lambda value:tag in tags(value))) for tag in values]
        features += [("标题：" + label, df["标题特征"].str.contains(label, regex=False)) for label in FEATURE_PATTERNS]
        body_features=df.get('正文特征',df['正文'].map(lambda value:'、'.join(detect_features('',value))) if '正文特征' not in df else None)
        features += [("正文：" + label, body_features.str.contains(label,regex=False)) for label in FEATURE_PATTERNS if label not in ["提问式标题", "包含数字", "感叹句式"]]
        for label, mask in features:
            top_index, rest_index = top.index, rest.index
            if label.startswith("封面："):
                top_index = top[top["封面类型"] != "待标注"].index
                rest_index = rest[rest["封面类型"] != "待标注"].index
                if len(top_index) < 2 or len(rest_index) < 2:
                    continue
            elif label.startswith('辅助标签：'):
                top_index=top[top['辅助标签已复核'].eq(True)].index
                rest_index=rest[rest['辅助标签已复核'].eq(True)].index
                if len(top_index)<2 or len(rest_index)<2: continue
            elif label.startswith("正文："):
                top_index = top[top["正文"].ne("")].index
                rest_index = rest[rest["正文"].ne("")].index
                if len(top_index) < 2 or len(rest_index) < 2:
                    continue
            elif label.startswith("标题："):
                top_index = top[top["标题"].ne("")].index
                rest_index = rest[rest["标题"].ne("")].index
                if len(top_index) < 2 or len(rest_index) < 2:
                    continue
            top_count, rest_count = int(mask.loc[top_index].sum()), int(mask.loc[rest_index].sum())
            if top_count + rest_count:
                high_pct, base_pct = 100 * top_count / len(top_index), 100 * rest_count / len(rest_index)
                rows.append({"特征": label, "高互动组命中": top_count, "其余组命中": rest_count,
                             "高互动组有效篇数": len(top_index), "其余组有效篇数": len(rest_index),
                             "高互动组占比（%）": round(high_pct, 1), "其余组占比（%）": round(base_pct, 1),
                             "占比差（百分点）": round(high_pct - base_pct, 1)})
    comparisons = pd.DataFrame(rows)
    if not comparisons.empty:
        comparisons = comparisons.sort_values("占比差（百分点）", ascending=False)
    return valid, top, comparisons
