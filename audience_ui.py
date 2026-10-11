import hashlib
from uuid import uuid4
import streamlit as st
from audience_analysis import final_audience

def edit_audience(automatic,key):
    overrides_key=f'audience-overrides-{key}'
    overrides=st.session_state.setdefault(overrides_key,{})
    version=st.session_state.get(f'audience-revision-{key}',0)
    identity=hashlib.sha256(automatic.to_json(force_ascii=False).encode()).hexdigest()[:12]
    base_key=f'audience-base-{key}-{identity}-{version}'
    if base_key not in st.session_state: st.session_state[base_key]=final_audience(automatic,overrides)
    with st.expander('复核、修改与确认人群假设'):
        st.caption('可修改最终假设与待验证问题；选择“已删除”移出最终报告，自动证据仍保留。确认表示你的判断，不代表已证实真实粉丝画像。')
        base=st.session_state[base_key]
        edited=st.data_editor(base,hide_index=True,width='stretch',num_rows='fixed',key=f'audience-editor-{key}-{identity}-{version}',
            disabled=[col for col in base.columns if col not in ['最终假设','待验证问题','状态']],
            column_config={'状态':st.column_config.SelectboxColumn(options=['候选待验证','人工确认','人工修订','已删除'],required=True)})
        for before,after in zip(base.to_dict('records'),edited.to_dict('records')):
            fields={field:after[field] for field in ['最终假设','待验证问题','状态']}
            if any(before[field]!=after[field] for field in fields):
                if fields['最终假设']!=before['最终假设'] and fields['状态']=='候选待验证': fields['状态']='人工修订'
                overrides.setdefault(after['假设ID'],{}).update(fields)
        with st.form(f'add-audience-{key}'):
            hypothesis=st.text_input('补充人群或需求假设')
            proof=st.text_input('人工依据或待验证来源')
            question=st.text_input('补充假设的待验证问题')
            if st.form_submit_button('加入人工假设'):
                if not hypothesis.strip(): st.error('请填写假设内容。')
                else:
                    overrides['manual-'+uuid4().hex]={'假设类别':'人工补充','最终假设':hypothesis.strip(),
                        '自动假设':'','证据来源':'人工填写','原文依据':proof,'待验证问题':question,'状态':'人工修订'}
                    st.session_state[f'audience-revision-{key}']=version+1
                    st.rerun()
    all_rows=final_audience(automatic,overrides)
    return all_rows[~all_rows['状态'].eq('已删除')].copy(),all_rows
