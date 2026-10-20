"""Source selection only; all data processing stays in the existing pages."""
import streamlit as st


SOURCES = ("Excel 文件", "真实账号案例", "公开账号", "我的账号后台")
SYMBOLS = ("table_view", "collections_bookmark", "public", "manage_accounts")


def select_source(source):
    # Navigation does not start a read, submit a job, or discard analysis data.
    if source not in SOURCES:
        return
    st.session_state["active-data-source"] = source
    st.session_state["source-picker-open"] = False
    st.session_state["show_saved_project"] = False
    if source == SOURCES[0]:
        st.session_state["open-upload"] = True


def open_source_picker():
    st.session_state["source-picker-open"] = True
    st.session_state["show_saved_project"] = False


def retain_upload():
    # Streamlit removes uploads when their widget is unmounted. Keep this exact
    # widget mounted off-screen during navigation, without copying or re-uploading.
    if "excel-upload" in st.session_state:
        with st.container(key="source-retained-upload"):
            st.file_uploader("上传 .xlsx 文件", type=["xlsx"], key="excel-upload")


def render_source_picker():
    with st.container(key="source-picker"):
        st.html('<h1 class="source-picker-title" aria-label="请选择数据来源">'
                '<span class="source-title-lead">请选择</span>'
                '<span class="source-title-main">数据来源</span></h1>')
        with st.container(key="source-options"):
            for index, (source, symbol) in enumerate(zip(SOURCES, SYMBOLS)):
                st.button(source, icon=f":material/{symbol}:",
                          key=f"source-card-{index}", width="stretch",
                          on_click=select_source, args=(source,))

def current_source():
    # This is navigation state, never a widget key. Old radio events cannot
    # overwrite it, and widget cleanup cannot remove it when pages change.
    source = st.session_state.get('active-data-source', SOURCES[0])
    return source if source in SOURCES else SOURCES[0]


def render_hero():
    with st.container(key='glass-hero'):
        st.html('<div class="hero-copy"><h1>AI运营分析台</h1></div>')
        st.button('返回数据来源', icon=':material/arrow_back:',
                  key='source-back', on_click=open_source_picker)
        with st.popover('项目管理', icon=':material/folder_open:'):
            from project_ui import project_picker
            project_picker()