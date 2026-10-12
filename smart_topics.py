"""Reviewed case themes and local semantic matching with a transparent text fallback."""
from collections import Counter
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import os
import re
import numpy as np
import pandas as pd
from dynamic_topics import discover_topics, OTHER, terms
from note_schema import normalize_notes, THEME_FIELDS, content_text
from topic_catalog import CATALOG, ANCHORS

VERSION = 'semantic-themes-1'


def text_fields(note):
    return [content_text(note.get(k)) for k in ['标题','正文','内容概述（整理）',*THEME_FIELDS]]


def signature(note):
    return hashlib.sha256(json.dumps(text_fields(note),ensure_ascii=False).encode()).hexdigest()


def result_for(notes, assignments, evidence, confidence, method, origin):
    labels = list(dict.fromkeys(label for label in assignments if label != OTHER))
    identities = {label:'theme-'+hashlib.sha256((origin+label).encode()).hexdigest()[:12] for label in labels}
    rows=[]
    for label in labels:
        members=[i for i,v in enumerate(assignments) if v==label]
        words=Counter(word for i in members for word in terms(' '.join(text_fields(notes[i]))))
        selected=[]
        for word in sorted(words,key=lambda w:(-words[w],-len(w),w)):
            if not any(word in old or old in word for old in selected):selected.append(word)
            if len(selected)==3:break
        rows.append({'主题ID':identities[label],'内容支柱':label,'命名状态':origin,
                     '归纳关键词':'、'.join(selected),'初分篇数':len(members),
                     '代表笔记':'；'.join(f"第{i+1}篇：{notes[i].get('标题','')}" for i in members[:3])})
    return dict(labels=labels,topic_ids=list(identities.values()),assignments=assignments,
                assignment_ids=[identities.get(v,'other') for v in assignments],evidence=evidence,
                confidence=confidence,topics=pd.DataFrame(rows),method=method,origin=origin)


def reviewed_topics(notes, case_id):
    if not case_id:return None
    reviews=json.loads(Path(__file__).with_name('reviewed_topics.json').read_text(encoding='utf-8')).get(case_id)
    if not reviews:return None
    matched=[]
    for note in notes:
        review=reviews.get(note.get('笔记链接'))
        if not review or review['signature']!=signature(note):return None
        matched.append(review)
    return result_for(notes,[r['theme'] for r in matched],[r['reason'] for r in matched],['中']*len(notes),
                      '案例分类已根据标题与整理概述逐篇复核；按内容含义归组，不是现场大模型生成。可继续改名、合并、拆分和调整笔记。',
                      '案例预先复核')


@lru_cache(maxsize=1)
def prototypes():
    from semantic_encoder import encode
    return encode([label+'。'+description for label,description in CATALOG.items()])


def short_fallback(notes):
    base=discover_topics(notes)
    rename={}
    for row in base['topics'].to_dict('records'):
        label=row['内容支柱']
        if '建议人工命名' in label or len(label)>14:
            words=[s for s in row['归纳关键词'].split('、') if 2<=len(s)<=8]
            label='与'.join(words[:2])+'相关内容' if words else '待复核内容'
        rename[row['内容支柱']]=label
    return result_for(notes,[rename.get(label,label) for label in base['assignments']],
                      base['evidence'],base['confidence'],'快速文本归纳，名称来自当前材料的短语；可人工复核。','文本初判')


def discover_smart_topics(notes, case_id=None, encoder=None, prototype_vectors=None):
    notes=normalize_notes(notes)
    reviewed=reviewed_topics(notes,case_id)
    if reviewed is not None:return reviewed
    if not notes or not any(any(text_fields(n)) for n in notes):return discover_topics(notes)
    if os.environ.get('TOPIC_ENGINE')=='rules':return short_fallback(notes)
    try:
        if encoder is None:
            from semantic_encoder import encode
            encoder=encode
        texts=['。'.join(filter(None,text_fields(n)))[:2000] for n in notes]
        vectors=encoder(texts)
        reference=prototypes() if prototype_vectors is None else prototype_vectors
        scores=vectors @ reference.T
        labels=list(CATALOG)
        assignments=[];evidence=[];confidence=[]
        # Retain specific repeated source themes when a broad domain would erase distinctions.
        explicit=[content_text(n.get('内容主题')) for n in notes]
        frequencies=Counter(explicit)
        for i,note in enumerate(notes):
            if not any(text_fields(note)):
                assignments.append(OTHER);evidence.append('缺少可用文字');confidence.append('低');continue
            ranked=np.argsort(-scores[i],kind='stable')
            first,second=int(ranked[0]),int(ranked[1])
            strength=float(scores[i,first]);gap=strength-float(scores[i,second])
            supported = any(term in texts[i].lower() for term in ANCHORS.get(labels[first], ()))
            if explicit[i] and len(explicit[i])<=14 and frequencies[explicit[i]]>=2:
                assignments.append(explicit[i]);evidence.append('保留材料中重复出现的内容主题字段；未将其当作平台认证分类');confidence.append('中')
            elif (strength>=.40 and gap>=.025) or (supported and strength>=.15 and gap>=.04):
                assignments.append(labels[first]);confidence.append('中' if strength>=.48 and gap>=.06 else '低')
                evidence.append(f'本地语义匹配：{labels[first]}；相似度 {strength:.2f}，领先次选 {gap:.2f}（不是准确率）。依据标题、已读取正文及整理概述。')
            else:
                assignments.append(OTHER);confidence.append('低')
                evidence.append('语义匹配不够明确，暂不强行归组；请补充正文或人工分类。')
        return result_for(notes,assignments,evidence,confidence,
                          '免费语义模型在服务器本地匹配文本，结合领域描述和明确关键词归纳；不强制分成三类，不向外部 AI 发送内容。名称与逐篇分类均可修改。',
                          '语义初判')
    except Exception:
        fallback=short_fallback(notes)
        fallback['method']='语义模型暂不可用，当前使用快速文本归纳；没有调用付费 API。稍后新开页面可重试。'
        fallback['retry_semantic']=True
        return fallback
