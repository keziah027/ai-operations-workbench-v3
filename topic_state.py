"""主题身份与名称分开；操作纯函数返回新状态，便于存档、撤销和回归。"""
from copy import deepcopy
from uuid import uuid4
from collections import Counter
import pandas as pd
from dynamic_topics import OTHER, terms
from content_analysis import build_annotations
from note_schema import content_text


def create_state(notes, automatic, previous=None):
    definitions=[{'id':identity,'name':name,'origin':'自动归纳'} for identity,name in
                 zip(automatic.get('topic_ids',[]),automatic['labels'])]
    definitions.append({'id':'other','name':OTHER,'origin':'保留分类'})
    rows=build_annotations(notes,automatic).to_dict('records')
    if previous is not None:
        for row,old in zip(rows,previous.to_dict('records')):
            row.update(old)
            match=next((topic for topic in definitions if topic['name']==row['主支柱']),None)
            if match is None:
                match={'id':'manual-'+uuid4().hex[:12],'name':row['主支柱'],'origin':'旧人工分类'}
                definitions.insert(-1,match)
            row['主题ID']=match['id']
    return {'topics':definitions,'annotations':rows,'revision':0,'undo':None}


def _name(state, name, exclude=None):
    name=content_text(name)
    if not name or name==OTHER or len(name)>80:
        raise ValueError('主题名称需为1—80字的有效名称，不能使用占位文字。')
    if any(topic['name']==name and topic['id']!=exclude for topic in state['topics']):
        raise ValueError('已有同名主题；请合并或选择已有目标，不要重复命名。')
    return name


def _begin(state, action):
    result=deepcopy(state)
    result['undo']={'topics':deepcopy(state['topics']),
                    'membership':[(row['主题ID'],row.get('最终分类来源','自动初判')) for row in state['annotations']],
                    'action':action,'redirects':deepcopy(state.get('redirects',{}))}
    result['revision']+=1
    return result


def sync_names(state):
    names={topic['id']:topic['name'] for topic in state['topics']}
    for row in state['annotations']:
        if row['主题ID'] not in names:
            raise ValueError('笔记引用了不存在的主题。')
        row['主支柱']=names[row['主题ID']]
    return state


def rename_topic(state, identity, name):
    if identity=='other': raise ValueError('保留分类不能改名。')
    name=_name(state,name,identity)
    result=_begin(state,'主题改名')
    topic=next((topic for topic in result['topics'] if topic['id']==identity),None)
    if topic is None: raise ValueError('主题已不存在。')
    topic['name']=name
    return sync_names(result)


def merge_topics(state, identities, name):
    identities=set(identities)
    if len(identities)<2 or 'other' in identities:
        raise ValueError('请选择至少两个有效主题进行合并。')
    if not identities.issubset({topic['id'] for topic in state['topics']}):
        raise ValueError('所选主题已变化，请重新选择。')
    name=_name(state,name)
    result=_begin(state,'主题合并')
    identity='manual-'+uuid4().hex[:12]
    result['topics']=[topic for topic in result['topics'] if topic['id'] not in identities]
    result['topics'].insert(-1,{'id':identity,'name':name,'origin':'人工合并'})
    for source in identities: result.setdefault('redirects',{})[source]=identity
    for row in result['annotations']:
        if row['主题ID'] in identities:
            row.update({'主题ID':identity,'最终分类来源':'人工合并'})
    return sync_names(result)


def move_notes(state, source, row_numbers, target=None, new_name=None):
    chosen=set(row_numbers)
    if not chosen: raise ValueError('请至少勾选一篇需要移出的笔记。')
    available={row['序号'] for row in state['annotations'] if row['主题ID']==source}
    if not chosen.issubset(available): raise ValueError('所选笔记已不属于该主题，请重新选择。')
    if new_name: new_name=_name(state,new_name)
    elif target==source or target not in {topic['id'] for topic in state['topics']}:
        raise ValueError('请选择不同的目标主题，或填写新主题名称。')
    result=_begin(state,'人工拆分/移入')
    if new_name:
        target='manual-'+uuid4().hex[:12]
        result['topics'].insert(-1,{'id':target,'name':new_name,'origin':'人工拆分'})
    for row in result['annotations']:
        if row['序号'] in chosen: row.update({'主题ID':target,'最终分类来源':'人工拆分/移入'})
    return sync_names(result)


def apply_editor(state, edited):
    result=deepcopy(state)
    by_name={topic['name']:topic['id'] for topic in state['topics']}
    records=edited.to_dict('records')
    if len(records)!=len(state['annotations']): raise ValueError('逐篇标注不能增删笔记。')
    changed=any(row['主支柱']!=old['主支柱'] for row,old in zip(records,state['annotations']))
    if changed: result=_begin(state,'逐篇分类')
    for row,old in zip(records,state['annotations']):
        identity=by_name.get(row['主支柱'])
        if identity is None: raise ValueError('请先建立目标主题。')
        row['主题ID']=identity
        if identity!=old['主题ID']: row['最终分类来源']='人工逐篇分类'
    result['annotations']=records
    return sync_names(result)


def undo_topic(state):
    backup=state.get('undo')
    if not backup: raise ValueError('没有可撤销的主题操作。')
    result=deepcopy(state)
    result['topics']=deepcopy(backup['topics'])
    result['redirects']=deepcopy(backup.get('redirects',{}))
    for row,(identity,origin) in zip(result['annotations'],backup['membership']):
        row.update({'主题ID':identity,'最终分类来源':origin})
    result.update(undo=None,revision=state['revision']+1)
    return sync_names(result)


def review_topics(frame):
    rows=[]
    for identity,group in frame.groupby('主题ID',sort=False):
        counts=Counter(word for _,row in group.iterrows() for word in set(terms(row['标题']+' '+row['正文'])))
        keywords=[]
        for word in sorted(counts,key=lambda word:(-counts[word],-len(word),word)):
            if not any(word in selected or selected in word for selected in keywords): keywords.append(word)
            if len(keywords)==5: break
        ranked=sorted(group.to_dict('records'),key=lambda row:-sum(counts[word] for word in set(terms(row['标题']+' '+row['正文']))))
        rows.append({'主题ID':identity,'最终主题':group.iloc[0]['主支柱'],'篇数':len(group),
                     '当前组关键词':'、'.join(keywords),'代表笔记':'；'.join(f"第{r['序号']}篇：{r['标题']}" for r in ranked[:3]),
                     '待复核篇数':int(group['分类置信度'].eq('低').sum())})
    return pd.DataFrame(rows)
