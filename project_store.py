"""单用户 JSON 存档：版本校验、目录边界、原子写入，与浏览器资料隔离。"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import json
import os
import re
import tempfile
from state_codec import plain,encoded,without_secrets,fingerprint

FORMAT_VERSION=1
DEFAULT_ROOT=Path(__file__).resolve().parent/'.local'/'analysis-projects'

class ProjectError(ValueError): pass

def checked_path(root,identity):
    root=Path(root).absolute()
    if root.resolve()!=root: raise ProjectError('存档目录存在重定向，请使用项目内的真实目录。')
    if not re.fullmatch('[a-f0-9]{32}',identity): raise ProjectError('项目编号无效，不能读取任意路径。')
    target=root/(identity+'.json')
    if target.resolve().parent!=root.resolve(): raise ProjectError('项目文件超出存档目录。')
    return target

def validate(project):
    if not isinstance(project,dict) or project.get('format_version')!=FORMAT_VERSION:
        raise ProjectError('存档格式版本不兼容，请使用创建该存档的版本或升级工作台。')
    if not re.fullmatch('[a-f0-9]{32}',str(project.get('id',''))): raise ProjectError('存档项目编号损坏。')
    if not isinstance(project.get('snapshot'),dict) or not isinstance(project['snapshot'].get('notes'),list):
        raise ProjectError('存档缺少可用数据快照。')
    state=project.get('state',{})
    if not isinstance(state,dict): raise ProjectError('存档人工状态损坏。')
    editing=state.get('editing',{})
    if not isinstance(editing,dict): raise ProjectError('存档主题状态损坏。')
    if not project['snapshot'].get('name') or not project['snapshot'].get('captured_at'):
        raise ProjectError('存档缺少账号名称或快照时间。')
    if not isinstance(editing.get('topics'),list) or not isinstance(editing.get('annotations'),list):
        raise ProjectError('存档中的主题或标注结构损坏。')
    topics=editing['topics']; rows=editing['annotations']
    if any(not isinstance(t,dict) or not t.get('id') or not t.get('name') for t in topics): raise ProjectError('主题记录损坏。')
    ids=[t['id'] for t in topics]
    if len(set(ids))!=len(ids) or len({t['name'] for t in topics})!=len(topics): raise ProjectError('主题身份或名称重复。')
    if len(rows)!=len(project['snapshot']['notes']) or any(not isinstance(r,dict) or r.get('主题ID') not in ids for r in rows):
        raise ProjectError('笔记与标注数量或主题归属不一致。')
    if not isinstance(project.get('history'),dict) or not isinstance(project.get('account'),dict): raise ProjectError('存档缺少历史记录或账号身份。')
    if not project['account'].get('key') or any(not isinstance(record,dict) or not isinstance(record.get('note'),dict) or not isinstance(record.get('annotation'),dict) or not record['annotation'].get('主题ID') for record in project['history'].values()):
        raise ProjectError('历史笔记记录损坏。')
    current=project.get('current_ids')
    if not isinstance(current,list) or len(current)!=len(rows) or len(set(current))!=len(current):
        raise ProjectError('本次笔记身份列表损坏或重复。')
    if not isinstance(state.get('settings'),dict) or not isinstance(state.get('audience_overrides'),dict): raise ProjectError('人工设置记录损坏。')
    return project

def load_project(identity,root=DEFAULT_ROOT):
    path=checked_path(root,identity)
    try:
        if path.stat().st_size>80*1024*1024: raise ProjectError('存档超过80MB，请拆分项目后使用。')
        data=json.loads(path.read_text(encoding='utf-8'))
        validate(data)
        if data['id']!=identity: raise ProjectError('存档编号与文件名不一致。')
        return data
    except (OSError,UnicodeError,json.JSONDecodeError) as exc:
        raise ProjectError('无法打开项目：文件丢失、损坏或不可读取。原文件未被修改。') from exc

def save_project(project,root=DEFAULT_ROOT,as_new=False):
    data=without_secrets(plain(deepcopy(project)))
    if as_new: data['id']=uuid4().hex
    data['saved_at']=datetime.now().astimezone().isoformat(timespec='seconds')
    validate(data)
    path=checked_path(root,data['id']); temporary=None
    try:
        payload=encoded(data)
        if len(payload.encode('utf-8'))>80*1024*1024: raise ProjectError('项目超过80MB，请缩小快照。')
        path.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,prefix='.saving-',suffix='.tmp',delete=False) as handle:
            temporary=Path(handle.name); handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary,path)
        return data
    except OSError as exc:
        raise ProjectError('保存失败，请检查磁盘空间及目录权限；上一份有效存档保持不变。') from exc
    finally:
        if temporary and temporary.exists(): temporary.unlink(missing_ok=True)

def list_projects(root=DEFAULT_ROOT):
    root=Path(root); rows=[]
    if not root.exists(): return rows
    if root.resolve()!=root.absolute(): raise ProjectError('存档目录存在重定向。')
    for path in sorted(root.glob('*.json')):
        try:
            project=load_project(path.stem,root)
            rows.append({'id':path.stem,'name':project.get('name','未命名项目'),'saved_at':project.get('saved_at','')})
        except ProjectError:
            if re.fullmatch('[a-f0-9]{32}',path.stem): rows.append({'id':path.stem,'name':'无法读取的存档','saved_at':''})
    return rows

def content_version(project):
    return fingerprint({key:value for key,value in project.items() if key not in ['saved_at']})
