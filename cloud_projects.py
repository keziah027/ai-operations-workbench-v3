"""Session-only project storage; never enumerate or write a shared server directory."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
import json
import streamlit as st
from project_store import validate, ProjectError
from state_codec import plain, without_secrets, encoded


def projects():
    return st.session_state.setdefault('_private_projects', {})


def load_project(identity, root=None):
    if identity not in projects():
        raise ProjectError('本次会话没有该项目，请先导入你下载的项目存档。')
    return deepcopy(projects()[identity])


def list_projects(root=None):
    return [{'id': p['id'], 'name': p['name'], 'saved_at': p['saved_at']} for p in projects().values()]


def save_project(project, root=None, as_new=False):
    data = without_secrets(plain(deepcopy(project)))
    if as_new:
        data['id'] = uuid4().hex
    data['saved_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    validate(data)
    size = len(encoded(data).encode('utf-8'))
    if size > 10 * 1024 * 1024:
        raise ProjectError('公开演示的单个项目上限为10MB。')
    if data['id'] not in projects() and len(projects()) >= 5:
        raise ProjectError('本次会话最多保存5个项目，请下载存档后重新开始会话。')
    projects()[data['id']] = data
    return deepcopy(data)


def import_project(contents):
    if len(contents) > 10 * 1024 * 1024:
        raise ProjectError('项目存档超过10MB。')
    try:
        data = json.loads(contents)
        validate(data)
        if len(data['snapshot']['notes']) > 1000 or len(data['history']) > 5000:
            raise ProjectError('公开演示存档最多包含1000篇当前笔记、5000篇历史笔记。')
        if not isinstance(data.get('name'), str):
            raise ProjectError('项目名称无效。')
        return save_project(data, as_new=True)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        raise ProjectError('项目存档无法读取，请使用本工作台导出的JSON存档。') from None
