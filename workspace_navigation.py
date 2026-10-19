"""Shared navigation for the sidebar-free workspace."""
import streamlit as st


def render_hero(sources):
    from source_picker import open_source_picker
    with st.container(key='glass-hero'):
        st.html('<div class="hero-copy"><h1>AI运营分析台</h1></div>')
        st.button('返回数据来源', icon=':material/arrow_back:',
                  key='source-back', on_click=open_source_picker)
        render_workspace_menu(sources)


def render_workspace_menu(sources):
    from source_picker import select_source
    with st.popover('项目与数据', icon=':material/folder_open:'):
        with st.expander('数据来源'):
            mode = st.radio('数据来源', sources, key='data-source', width='stretch', label_visibility='collapsed', on_change=select_source)
        from project_ui import project_picker
        project_picker()
    return mode


