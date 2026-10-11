"""稳定身份匹配人工状态；本次样本与历史记录分别保存。"""
from copy import deepcopy
from uuid import uuid4
from collections import Counter
from urllib.parse import urlsplit
import re
from note_identity import platform_note_id,digest
from note_schema import normalize_notes
from state_codec import fingerprint,plain
from topic_state import create_state,sync_names
from packaging_analysis import setup_packaging
from project_store import ProjectError,FORMAT_VERSION

def scalar(value):
    value=plain(value)
    return '' if value is None else str(value).strip()

def account_identity(snapshot):
    direct=scalar(snapshot.get('account_id') or (snapshot.get('overview') or {}).get('account_id'))
    explicit={scalar(note.get('账号ID',note.get('account_id'))) for note in snapshot.get('notes',[])}-{''}
    if len(explicit)==1: direct=next(iter(explicit))
    if direct: return {'key':'account:'+direct,'stable':True}
    try:
        parsed=urlsplit(snapshot.get('url',''))
        match=re.search(r'/user/profile/([a-zA-Z0-9_-]+)',parsed.path)
        if match and (parsed.hostname=='xiaohongshu.com' or (parsed.hostname or '').endswith('.xiaohongshu.com')):
            return {'key':'account:'+match[1],'stable':True}
    except ValueError: pass
    scope=[snapshot.get('source_kind','公开账号'),snapshot.get('url',snapshot.get('source','')),snapshot.get('name','')]
    return {'key':'import:'+fingerprint(scope)[:20],'stable':False}

def text_version(note): return fingerprint([note.get('标题',''),note.get('正文','')])

def note_keys(snapshot):
    notes=normalize_notes(snapshot.get('notes',[])); scope=account_identity(snapshot)['key']; seen=Counter(); keys=[]
    bases=['note:'+platform_note_id(note) if platform_note_id(note) else 'local:'+digest(scope)+':'+fingerprint([note.get('标题'),note.get('正文'),note.get('发布时间'),note.get('内容形式')])[:20] for note in notes]
    frequencies=Counter(bases)
    for note in notes:
        explicit=platform_note_id(note)
        base='note:'+explicit if explicit else 'local:'+digest(scope)+':'+fingerprint([note.get('标题'),note.get('正文'),note.get('发布时间'),note.get('内容形式')])[:20]
        if not explicit and frequencies[base]>1:
            base+=':ambiguous:'+fingerprint([snapshot.get('captured_at'),snapshot.get('notes')])[:12]
        seen[base]+=1
        keys.append(base if seen[base]==1 else base+':occurrence:'+str(seen[base]))
    return keys

def compatible(project,snapshot):
    account=account_identity(snapshot)
    return account['key'] in [project['account']['key'],*project.get('account_aliases',[])]

def new_project(snapshot,automatic):
    notes=normalize_notes(snapshot['notes'])
    return {'format_version':FORMAT_VERSION,'id':uuid4().hex,'name':snapshot.get('name','分析项目'),
            'account':account_identity(snapshot),'account_aliases':[],'snapshot':deepcopy(snapshot),
            'state':{'editing':setup_packaging(create_state(notes,automatic)),'settings':{},'audience_overrides':{}},
            'history':{},'current_ids':note_keys(snapshot),'saved_at':''}

def refresh_project(project,snapshot,automatic,manual_matches=None,confirm_scope=False):
    result=deepcopy(project); incoming=account_identity(snapshot)
    if not compatible(project,snapshot):
        if not confirm_scope: raise ProjectError('账号或导入范围不同，未自动沿用人工修改。')
        if project['account']['stable'] and incoming['stable']:
            raise ProjectError('两个明确账号ID不同，不能合并项目。')
        result.setdefault('account_aliases',[]).append(incoming['key'])
    old_history=project['history']; matches=manual_matches or {}; ids=note_keys(snapshot)
    if not set(matches).issubset(ids) or not set(matches.values()).issubset(old_history): raise ProjectError('人工匹配的笔记编号无效。')
    if len(set(matches.values()))!=len(matches): raise ProjectError('不能把多篇新笔记匹配到同一篇历史笔记。')
    # 恢复原快照时保留撤销信息；读取新样本后不把旧的按行撤销套到新顺序。
    if fingerprint(snapshot)==fingerprint(project['snapshot']) and not matches:
        return result
    notes=normalize_notes(snapshot['notes']); fresh=setup_packaging(create_state(notes,automatic))
    state=deepcopy(project['state']['editing']); topics={t['id']:t for t in state['topics']}
    for topic in fresh['topics']:
        if topic['id'] not in topics:
            topic=deepcopy(topic); names={t['name'] for t in topics.values()}; base=topic['name']; number=2
            while topic['name'] in names: topic['name']=f'{base}（新识别{number}）'; number+=1
            topics[topic['id']]=topic
    state['topics']=list(topics.values()); rows=[]; final_ids=[]
    for index,(note,identity,new_row) in enumerate(zip(notes,ids,fresh['annotations'])):
        identity=matches.get(identity,identity)
        if identity in final_ids: raise ProjectError('笔记匹配冲突，请调整匹配目标。')
        final_ids.append(identity)
        old=old_history.get(identity)
        row=deepcopy(old['annotation']) if old else new_row
        visited=set(); topic_id=row['主题ID']
        while topic_id in state.get('redirects',{}) and topic_id not in visited:
            visited.add(topic_id); topic_id=state['redirects'][topic_id]
        row['主题ID']=topic_id
        row.update({'序号':index+1,'标题':new_row['标题'],'_note_id':identity,
                    '内容变更待复核':bool(old and (old.get('text_version')!=text_version(note) or old['annotation'].get('内容变更待复核')))})
        rows.append(row)
    state.update(annotations=rows,undo=None,revision=state.get('revision',0)+1)
    result['state']['editing']=setup_packaging(sync_names(state))
    result.update(snapshot=deepcopy(snapshot),current_ids=final_ids)
    return result

def collect_project(base,snapshot,editing,settings,overrides,name):
    result=deepcopy(base); result['name']=name.strip() or snapshot.get('name','分析项目')
    result['snapshot']=deepcopy(snapshot)
    result['state']={'editing':deepcopy(editing),'settings':deepcopy(settings),'audience_overrides':deepcopy(overrides)}
    ids=result.get('current_ids') or note_keys(snapshot)
    if len(ids)!=len(snapshot['notes']): raise ProjectError('当前快照与项目笔记编号不一致。')
    for identity,note,row in zip(ids,normalize_notes(snapshot['notes']),result['state']['editing']['annotations']):
        row['_note_id']=identity
        result['history'][identity]={'note':note,'annotation':deepcopy(row),'text_version':text_version(note),'last_seen':snapshot.get('captured_at','')}
    return plain(result)
