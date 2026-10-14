"""本地项目操作；默认不写盘，保存按钮明确提交当前人工状态。"""
from copy import deepcopy
from period_comparison import remember_period
import pandas as pd
import streamlit as st
from deployment import public_mode
from project_store import DEFAULT_ROOT,ProjectError,list_projects,load_project,save_project,content_version
if public_mode():
    from cloud_projects import list_projects, load_project, save_project
from project_state import new_project,refresh_project,collect_project,compatible,account_identity,note_keys

STORE_ROOT=DEFAULT_ROOT
BINDINGS={'bio':'bio-v2','identity_choice':'identity-v21','domains':'domains-v21','goals':'goals-v21',
          'position':'position-v2','audience':'audience-v2','diagnosis_note':'diagnosis-note-v2',
          'analysis_goals':'analysis-goals','metric':'interaction-v2'}

def project_picker():
    with st.expander('分析项目：打开与恢复' if public_mode() else '本地分析项目：打开与恢复'):
        st.caption('公开模式仅在当前会话内保存，刷新、断线或服务重启后可能清空。请下载JSON存档，下次导入恢复；不同访客互不可见。' if public_mode() else '项目存档用于继续编辑；Excel/Markdown是报告。存档保存在本项目的 .local/analysis-projects，与浏览器登录资料分开。')
        if public_mode():
            archive = st.file_uploader('导入下载的项目存档（JSON）', type=['json'], key='project-import')
            if st.button('恢复项目存档', disabled=archive is None):
                from cloud_projects import import_project
                try:
                    project = import_project(archive.getvalue())
                    remember_period(st.session_state, project)
                    st.session_state.update(active_project=project, show_saved_project=True, project_dirty=False,
                                            restore_epoch=st.session_state.get('restore_epoch', 0) + 1)
                    st.rerun()
                except ProjectError as exc:
                    st.error(str(exc))
        try: entries=list_projects(STORE_ROOT)
        except ProjectError as exc: st.error(str(exc)); return
        labels={row['id']:f"{row['name']} · {row['saved_at']}" for row in entries}
        chosen=st.selectbox('选择已保存项目',['',*labels],format_func=lambda item:labels.get(item,'请选择项目'),key='open-project-choice')
        allowed=True
        if st.session_state.get('project_dirty'):
            st.warning('当前分析有未保存修改。切换前请保存，或确认放弃当前编辑页面。')
            allowed=st.checkbox('确认切换项目，当前未保存修改不写入存档',key='allow-project-switch')
        if st.button('打开项目',disabled=not chosen or not allowed):
            try:
                project=load_project(chosen,STORE_ROOT)
                remember_period(st.session_state, project)
                st.session_state.update(active_project=project,show_saved_project=True,project_dirty=False,
                                        restore_epoch=st.session_state.get('restore_epoch',0)+1)
                st.rerun()
            except ProjectError as exc: st.error(str(exc))
        st.caption('多期环比：先打开已保存的同账号项目，再返回入口上传新一期 Excel 或读取后台。Excel 请填写账号名称；对比仅在本次会话保留。')
        if st.session_state.get('active_project'):
            if st.button('返回数据入口，读取或上传新数据'):
                st.session_state['show_saved_project']=False
                st.rerun()

def install_context(project,key):
    if project['state'].get('ai_workspace'):
        from ai_ui import workspace_key
        st.session_state[workspace_key(project['snapshot'])]=deepcopy(project['state']['ai_workspace'])
    st.session_state[f'project-context-{key}']=deepcopy(project)
    st.session_state[f'editor-state-{key}']=deepcopy(project['state']['editing'])
    st.session_state[f'audience-overrides-{key}']=deepcopy(project['state']['audience_overrides'])
    for field,prefix in BINDINGS.items():
        if field in project['state']['settings']:
            st.session_state[f'{prefix}-{key}']=deepcopy(project['state']['settings'][field])

def prepare_context(snapshot,automatic,key):
    context_key=f'project-context-{key}'
    active=st.session_state.get('active_project')
    if context_key not in st.session_state:
        if active and compatible(active,snapshot):
            project=refresh_project(active,snapshot,automatic)
            install_context(project,key)
        else:
            # 不为未保存的另一账号建立自动继承关系。
            st.session_state[context_key]=new_project(snapshot,automatic)
    base=st.session_state[context_key]
    ambiguous=bool(active and any(identity.startswith('local:') and identity not in active['history'] for identity in note_keys(snapshot)))
    if active and (not compatible(active,snapshot) or ambiguous):
        incoming=account_identity(snapshot)
        st.info('部分无ID笔记未能确定对应历史记录，可以人工匹配。' if compatible(active,snapshot) else '当前数据与已打开项目的账号或导入范围不同，未自动沿用标注。可直接保存为新项目。')
        if compatible(active,snapshot) or not(active['account']['stable'] and incoming['stable']):
            with st.expander('跨文件恢复：确认账号并逐篇匹配'):
                st.caption('没有稳定笔记ID时不按同名标题自动匹配。明确选择对应的历史笔记；未匹配记录作为新笔记。')
                new_ids=note_keys(snapshot)
                history=active['history']
                titles={identity:f"{record['note'].get('标题','未命名')} [{identity}]" for identity,record in history.items()}
                mapping=pd.DataFrame({'本次笔记ID':new_ids,'标题':[note.get('标题','') for note in snapshot['notes']],
                                      '对应历史笔记':['新笔记']*len(new_ids)})
                with st.form(f'match-{key}'):
                    agreed=st.checkbox('我确认这是同一账号，按下表匹配人工修改')
                    edited=st.data_editor(mapping,hide_index=True,width='stretch',disabled=['本次笔记ID','标题'],
                        column_config={'对应历史笔记':st.column_config.SelectboxColumn(options=['新笔记',*titles.values()],required=True)})
                    if st.form_submit_button('应用人工匹配'):
                        if not agreed: st.error('请先确认账号与笔记对应关系。')
                        else:
                            reverse={name:identity for identity,name in titles.items()}
                            matches={row['本次笔记ID']:reverse[row['对应历史笔记']] for row in edited.to_dict('records') if row['对应历史笔记']!='新笔记'}
                            try:
                                restored=refresh_project(active,snapshot,automatic,matches,confirm_scope=True)
                                install_context(restored,key)
                                st.session_state['active_project']=restored
                                st.rerun()
                            except ProjectError as exc: st.error(str(exc))
    count=len(base['history']); current=len(snapshot['notes'])
    st.caption(f'本次分析 {current} 篇；已保存/关联的项目历史 {count} 篇。历史未读到的笔记保留，当前统计只用本次样本。')

def save_controls(snapshot,analysis,key):
    base=st.session_state[f'project-context-{key}']
    settings={field:deepcopy(st.session_state[f'{prefix}-{key}']) for field,prefix in BINDINGS.items() if f'{prefix}-{key}' in st.session_state}
    with st.expander('保存当前分析项目',expanded=True):
        name=st.text_input('项目名称',value=base['name'],key=f'project-name-{key}')
        current=collect_project(base,snapshot,analysis['editing'],settings,st.session_state.get(f'audience-overrides-{key}',{}),name)
        from ai_ui import workspace_key
        ai_workspace=st.session_state.get(workspace_key(snapshot))
        if ai_workspace and (ai_workspace.get('record') or ai_workspace.get('chat')):
            current['state']['ai_workspace']=deepcopy(ai_workspace)
        dirty=not base.get('saved_at') or content_version(current)!=content_version(base)
        st.session_state['project_dirty']=dirty
        if public_mode():
            from state_codec import encoded, without_secrets
            st.download_button('下载项目存档（JSON，可恢复编辑）', encoded(without_secrets(current)).encode('utf-8'),
                               file_name='运营分析项目.json', mime='application/json', key=f'archive-{key}')
        st.caption(('有未保存修改。' if dirty else '当前修改已保存。')+' 最后保存：'+(base.get('saved_at') or '尚未保存'))
        save,copy=st.columns(2)
        requested=save.button('保存项目',key=f'save-project-{key}')
        separate=copy.button('另存为新项目',key=f'copy-project-{key}')
        if requested or separate:
            try:
                saved=save_project(current,STORE_ROOT,as_new=separate)
                st.session_state[f'project-context-{key}']=saved
                st.session_state['active_project']=saved
                st.session_state['project_dirty']=False
                st.rerun()
            except ProjectError as exc: st.error(str(exc))
        # 保留同一已关联项目的会话草稿，重读不会清空未写盘的人工内容。
        active=st.session_state.get('active_project')
        if active and active['id']==current['id']: st.session_state['active_project']=current
    return current
