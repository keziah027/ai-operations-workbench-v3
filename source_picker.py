"""Source selection only; all data processing stays in the existing pages."""
import streamlit as st


SOURCES = ("Excel 文件", "真实账号案例", "公开账号", "我的账号后台")
SYMBOLS = ("table_view", "collections_bookmark", "public", "manage_accounts")


def select_source(source=None):
    # Navigation does not start a read, submit a job, or discard analysis data.
    source = source or st.session_state.get("data-source", SOURCES[0])
    if source not in SOURCES:
        return
    st.session_state["data-source"] = source
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
