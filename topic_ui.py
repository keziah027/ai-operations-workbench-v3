"""主题编辑界面，所有操作作用于同一最终状态。"""
import pandas as pd
import streamlit as st
from content_analysis import COVERS
from topic_state import create_state,rename_topic,merge_topics,move_notes,undo_topic,apply_editor
from packaging_analysis import setup_packaging,change_cover_type,BODY_TYPES


def render_topic_editor(notes,automatic,key,commerce):
    state_key=f'editor-state-{key}'
    if state_key not in st.session_state:
        old=st.session_state.get(f'annotation-data-v2-{key}')
        st.session_state[state_key]=create_state(notes,automatic,old['data'] if old else None)
    state=setup_packaging(st.session_state[state_key])
    def commit(operation,*args,**kwargs):
        try:
            st.session_state[state_key]=operation(state,*args,**kwargs)
        except ValueError as exc:
            st.error(str(exc)); return
        st.rerun()
    # A revision changes only on an explicit operation, keeping the editor's baseline stable.
    revision=state['revision']
    editor=f'annotations-v3-{key}-{revision}-{int(commerce)}'
    base=f'editor-base-{key}-{revision}-{int(commerce)}'
    if base not in st.session_state:
        st.session_state[base]=pd.DataFrame(state['annotations'])
    config={'主支柱':st.column_config.SelectboxColumn(options=[t['name'] for t in state['topics']],required=True),
            '封面类型':st.column_config.SelectboxColumn(options=state['packaging']['cover_types'],required=True),
            '封面辅助标签':st.column_config.TextColumn(help='用逗号分隔，如文字密集、有人物、对比结构；辅助标签可以重叠'),
            '辅助标签已复核':st.column_config.CheckboxColumn(help='只有主动勾选的笔记进入辅助标签占比比较'),
            '正文结构（人工）':st.column_config.SelectboxColumn(options=BODY_TYPES,required=True)}
    if not commerce: config['商品/系列（人工确认）']=None
    readonly=['序号','标题','分类依据','分类置信度','主题ID','自动主题ID','自动主支柱','自动分类依据','最终分类来源','_note_id']
    edited=st.data_editor(st.session_state[base],key=editor,hide_index=True,width='stretch',
                         disabled=readonly,column_config=config,num_rows='fixed')
    state=apply_editor(state,edited)
    if any(row.get('内容变更待复核') for row in state['annotations']):
        st.warning('部分已知笔记的标题或正文发生变化，原人工标注已保留。请核对后取消“内容变更待复核”。')
    # A normal row edit keeps its baseline until an explicit operation.
    state['revision']=revision
    st.session_state[state_key]=state
    definitions={t['id']:t['name'] for t in state['topics']}
    valid=[identity for identity in definitions if identity!='other']
    st.caption('主支柱为最终采用分类；自动主题、自动依据始终保留。主题名称可改，主题编号不变。')
    if valid:
        with st.form(f'rename-{key}-{revision}'):
            selected=st.selectbox('要改名的主题',valid,format_func=definitions.get)
            name=st.text_input('新的主题名称')
            if st.form_submit_button('应用主题改名'): commit(rename_topic,selected,name)
    with st.form(f'merge-{key}-{revision}'):
        selected=st.multiselect('选择要合并的主题',valid,format_func=definitions.get)
        name=st.text_input('合并后的主题名称')
        if st.form_submit_button('合并所选主题'): commit(merge_topics,selected,name)
    source=st.selectbox('查看并拆分主题',list(definitions),format_func=definitions.get,key=f'split-source-{key}-{revision}')
    candidates=[row for row in state['annotations'] if row['主题ID']==source]
    st.dataframe(pd.DataFrame(candidates)[['序号','标题','主支柱','分类置信度']] if candidates else pd.DataFrame(),hide_index=True,width='stretch')
    with st.form(f'split-{key}-{revision}-{source}'):
        titles={row['序号']:f"第{row['序号']}篇：{row['标题']}" for row in candidates}
        selected=st.multiselect('勾选需要移出的笔记',list(titles),format_func=titles.get)
        destinations=[identity for identity in definitions if identity!=source]
        target=st.selectbox('移入已有主题',['new',*destinations],format_func=lambda value:'新建主题' if value=='new' else definitions[value])
        new_name=st.text_input('新建主题名称（选择新建时填写）')
        if st.form_submit_button('应用拆分/移入'):
            commit(move_notes,source,selected,target=target,new_name=new_name if target=='new' else None)
    if st.button('撤销最近一次主题操作',disabled=not state.get('undo'),key=f'undo-{key}'):
        commit(undo_topic)
    with st.expander('管理封面主类型'):
        st.caption('主类型互斥；文字密度、人物出现、对比结构请填写辅助标签。旧类型保留，不自动识别图片。')
        with st.form(f'cover-add-{key}-{revision}'):
            name=st.text_input('新增封面类型名称')
            if st.form_submit_button('新增封面类型'): commit(change_cover_type,'add',name=name)
        cover_types=state['packaging']['cover_types']
        with st.form(f'cover-rename-{key}-{revision}'):
            old=st.selectbox('重命名封面类型',[value for value in cover_types if value!='待标注'])
            name=st.text_input('封面类型新名称')
            if st.form_submit_button('应用封面类型改名'): commit(change_cover_type,'rename',old=old,name=name)
        old=st.selectbox('准备删除的封面类型',[value for value in cover_types if value!='待标注'],key=f'cover-delete-{key}-{revision}')
        with st.form(f'cover-delete-form-{key}-{revision}-{old}'):
            replacement=st.selectbox('删除后将已有标注转为',['请选择',*[value for value in cover_types if value!=old]])
            if st.form_submit_button('删除并替换此类型'): commit(change_cover_type,'delete',old=old,replacement=replacement)
    return pd.DataFrame(state['annotations']),state
