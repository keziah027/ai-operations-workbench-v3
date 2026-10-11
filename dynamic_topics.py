"""从本次语料归纳主题；不按账号类型预设内容分类。无需新增依赖。"""
from collections import Counter
import math
import re
import hashlib

import numpy as np
import pandas as pd

from account_profile import clean, note_text, usable_title
from note_schema import normalize_notes, THEME_FIELDS

OTHER = "其他/待确认"
STOP = set("这个 那个 一个 一些 什么 怎么 如何 为什么 自己 我们 你们 他们 可以 真的 今天 分享 大家 一起 就是 不是 还是 以及 关于 因为 所以 如果 但是 已经 时候 这些 那些 笔记 内容 小红书 关注 点赞 收藏 评论 标题 正文 未命名 教程 方法 技巧 干货".split())
EDGE = set("的了是在和与及把被就也很更最都而我你他她它这那么吗呢吧呀啊哦让给从对到着过地得有不为")


def phrases(note):
    """完整字段、真实话题和标题短句用于命名；短字片段仅作为关键词。"""
    candidates=[]
    for field in THEME_FIELDS:
        candidates += re.split(r'[；;，,、/|]', clean(note.get(field)))
    candidates += re.findall(r'#([\w\u4e00-\u9fff]{2,24})', note_text(note))
    candidates += re.split(r'[：:，,！!？?。|｜/\n]', usable_title(note.get('标题')))
    result=[]
    for value in candidates:
        value=re.sub(r'^\s*\d+[.、）)]\s*|\s*\d+\s*$', '', value).strip().strip('#')
        if clean(value) and value.lower() not in STOP and 4<=len(value)<=20:
            result.append(value)
    return list(dict.fromkeys(result))


def terms(value):
    """汉字短语与英文词片段；停用语只用于清理，不提供任何主题名。"""
    counts = Counter()
    value = re.sub(r"https?://\S+", " ", clean(value).lower())
    for chunk in re.findall(r"[\u4e00-\u9fff]+|[a-z][a-z0-9-]{1,24}", value):
        if chunk.isascii():
            counts[chunk] += 1
            continue
        for size in range(2, min(6, len(chunk)) + 1):
            for start in range(len(chunk) - size + 1):
                token = chunk[start:start + size]
                if token not in STOP and token[0] not in EDGE and token[-1] not in EDGE and not any(word in token for word in STOP if len(word) > 1):
                    counts[token] += 1
    return counts


def discover_topics(notes):
    """确定性 TF-IDF / 余弦聚类，目标 3–7 类；重复/少量/无文本时不虚构类别。"""
    notes = normalize_notes(notes)
    documents, token_counts, explicit = [], [], Counter()
    for note in notes:
        documents.append(note_text(note))
        counts = terms(usable_title(note.get("标题")))
        counts = Counter({word: value * 3 for word, value in counts.items()})
        counts.update(terms(clean(note.get("正文"))[:6000]))
        for field in ['主题文本']:
            value = clean(note.get(field))
            counts.update({word: count * 2 for word, count in terms(value).items()})
        for phrase in re.findall(r"#([\u4e00-\u9fffa-zA-Z][\u4e00-\u9fffa-zA-Z0-9]{1,11})", documents[-1]):
            phrase = phrase.lower()
            if phrase not in STOP:
                counts[phrase] += 5
                explicit[phrase] += 1
        token_counts.append(counts)
    frequency = Counter(word for counts in token_counts for word in counts)
    # 优先保留重复主题，也保留少量独有词以容纳长尾内容。
    vocabulary = sorted(frequency, key=lambda word: (-frequency[word] * math.sqrt(len(word)), word))[:2400]
    empty = {"labels": [], "assignments": [OTHER] * len(notes), "evidence": ["缺少可用主题文本"] * len(notes),
             "confidence": ["低"] * len(notes), "topics": pd.DataFrame(), "method": "无可用文本，暂不归纳主题。"}
    if not vocabulary:
        return empty
    n = len(notes)
    matrix = np.array([[math.log1p(counts.get(word, 0)) * (math.log((n + 1) / (frequency[word] + 1)) + 1)
                        for word in vocabulary] for counts in token_counts], dtype=float)
    lengths = np.linalg.norm(matrix, axis=1)
    matrix /= np.maximum(lengths[:, None], 1e-12)
    valid = np.flatnonzero(lengths > 0)
    if not len(valid):
        return empty
    requested = min(7, max(3, round(math.sqrt(len(valid) / 2))))
    centre = matrix[valid].mean(axis=0)
    seeds = [int(valid[np.argmax(matrix[valid] @ centre)])]
    while len(seeds) < min(requested, len(valid)):
        similarity = (matrix[valid] @ matrix[seeds].T).max(axis=1)
        farthest = int(valid[np.argmin(similarity)])
        if farthest in seeds or 1 - float(similarity.min()) < .24:
            break  # 重复或高度相似内容不强拆成三类。
        seeds.append(farthest)
    centers = matrix[seeds].copy()
    previous = None
    for _ in range(25):
        assignment = (matrix @ centers.T).argmax(axis=1)
        if previous is not None and np.array_equal(assignment, previous):
            break
        previous = assignment.copy()
        for group in range(len(centers)):
            members = matrix[(assignment == group) & (lengths > 0)]
            if len(members):
                mean = members.mean(axis=0)
                centers[group] = mean / max(np.linalg.norm(mean), 1e-12)
    scores = matrix @ centers.T
    global_mean = matrix[valid].mean(axis=0)
    labels, descriptors, rows, ids = {}, {}, [], {}
    phrase_docs=[phrases(note) for note in notes]
    phrase_df=Counter(phrase for doc in phrase_docs for phrase in set(doc))
    for group in sorted(set(assignment[valid])):
        indices = [int(i) for i in valid if assignment[i] == group]
        local_frequency = Counter(word for i in indices for word in token_counts[i])
        weights = np.maximum(matrix[indices].mean(axis=0) - .85 * global_mean, 0)
        positions = {word: i for i, word in enumerate(vocabulary)}
        candidates = sorted(vocabulary, key=lambda word: (
            -(weights[positions[word]] * (1 + .15 * min(len(word), 6)) * (2.5 if explicit[word] else 1)), word))
        selected = []
        for word in candidates:
            if not local_frequency[word] or (len(indices) >= 3 and local_frequency[word] < 2):
                continue
            if any(word in earlier or earlier in word for earlier in selected):
                continue
            selected.append(word)
            if len(selected) == 3:
                break
        selected = selected or [next(iter(token_counts[indices[0]]))]
        local_phrases=Counter(phrase for i in indices for phrase in set(phrase_docs[i]))
        eligible=[phrase for phrase,count in local_phrases.items()
                  if (count>=2 or len(indices)<=2) and
                  (len(centers)==1 or phrase_df[phrase]/len(valid)<.8)]
        eligible.sort(key=lambda phrase: (-(local_phrases[phrase]/len(indices) -
                       .75*phrase_df[phrase]/len(valid)), -min(len(phrase),12), phrase))
        name=eligible[0] if eligible else f'主题{group+1}（建议人工命名）'
        if name in labels.values():
            name += f"（{group + 1}）"
        labels[group] = name
        descriptors[group] = selected
        ids[group]='auto-'+hashlib.sha256('\n'.join(sorted(documents[i] for i in indices)).encode()).hexdigest()[:12]
        rows.append({'主题ID':ids[group], "内容支柱": name, '命名状态':'语料短语建议' if eligible else '建议人工命名',
                     "归纳关键词": "、".join(selected), "初分篇数": len(indices),
                     "代表笔记": "；".join(f"第{i+1}篇：{clean(notes[i].get('标题'))}" for i in sorted(indices, key=lambda i: -scores[i, group])[:3])})
    chosen, evidence, confidence = [], [], []
    for index, counts in enumerate(token_counts):
        group = int(assignment[index])
        strength = float(scores[index, group])
        alternatives = sorted(scores[index], reverse=True)
        gap = alternatives[0] - alternatives[1] if len(alternatives) > 1 else strength
        if lengths[index] == 0 or strength < .12:
            chosen.append(OTHER)
            evidence.append("缺少可用文本或与已归纳主题的相似度过低，请人工确认")
            confidence.append("低")
            continue
        chosen.append(labels[group])
        shared = [word for word in descriptors[group] if word in counts]
        evidence.append("文本聚类；共同片段：" + ("、".join(shared) or "其他词片段相似") + f"；相似度 {strength:.2f}"
                        + ("；多个主题接近，请优先复核" if gap < .08 else ""))
        confidence.append("高" if strength >= .6 and gap >= .15 else "中" if gap >= .08 else "低")
    return {"labels": list(labels.values()), 'topic_ids':list(ids.values()),
            'assignment_ids':[ids[int(assignment[i])] if value!=OTHER else 'other' for i,value in enumerate(chosen)],
            "assignments": chosen, "evidence": evidence, "confidence": confidence,
            "topics": pd.DataFrame(rows), "method": "按本次标题、正文、话题及已有主题字段的词片段相似性归纳；目标3–7类，文本太少或高度重复时可少于3类。主题名取自语料，不调用外部大模型。"}
