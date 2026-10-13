"""启动方式：python -m streamlit run app.py"""

from pathlib import Path
from datetime import datetime
from note_schema import normalize_notes, COUNT_FIELDS
from performance import add_ratios
import hashlib

import pandas as pd
import streamlit as st
from deployment import public_mode, DEMO_NOTICE

from analysis import weekly_pattern, hourly_pattern, performance_tiers, account_comparison
from analysis import GROUP_COLUMNS, TYPE_COLUMNS, METRICS, daily_trend, group_summary, inspect_workbook, read_excel, summarize


def workbook_structure(contents):
    from result_cache import session_cache
    return session_cache('workbooks').get('structure', hashlib.sha256(contents).hexdigest(), lambda: inspect_workbook(contents))


def metric_text(value, decimals=0):
    return "—" if value is None or pd.isna(value) else f"{value:,.{decimals}f}"


@st.cache_resource
def account_browser(version="creator-v1"):
    if public_mode():
        raise RuntimeError('公开部署不创建共享的账号登录浏览器。')
    from account_session import AccountBrowser
    return AccountBrowser()


@st.fragment(run_every="1s")
def public_read_progress():
    state = account_browser().job_status()
    if not state or state.get("kind", "public") != "public":
        return
    if state["status"] == "running":
        denominator = state["loaded"] if state["stage"] == "详情" else state["requested"]
        numerator = state["processed"] if state["stage"] == "详情" else state["loaded"]
        st.progress(min(numerator / max(denominator, 1), 1.0), text=state["message"])
        st.caption(f"已找到 {state['loaded']} 篇 · 已处理详情 {state['processed']} 篇。可以继续使用页面，读取在后台进行。")
        if st.button("停止读取并保留结果", key="stop-public-read"):
            account_browser().cancel_read(state["id"])
            st.info("已请求停止，等待当前页面操作结束后显示已确认结果。")
    elif st.session_state.get("public_job_consumed") != state["id"]:
        st.session_state["public_job_consumed"] = state["id"]
        if state["status"] == "done":
            st.session_state["public_snapshot"] = {"input": state["input"], "data": state["result"]}
        else:
            st.session_state["public_job_error"] = state["error"]
        st.rerun()


def public_account_page():
    from account_reader import AccountReadError

    if public_mode():
        st.subheader('公开账号主页读取')
        st.info('此功能需要本机浏览器登录，在公开网站上无法弹出你的登录窗口。原版读取功能保留在本地模式；在线可切换到“真实账号案例”体验已采集的公开快照，或上传 Excel、加载模拟数据。')
        return

    st.subheader("公开账号主页读取")
    st.info("可向下加载更多笔记，并逐篇打开详情读取点赞、收藏和评论。实际数量取决于页面可见范围，不能保证覆盖账号全部历史。")
    st.caption("先在专用小红书窗口登录，再粘贴目标账号链接。类似“1千+”的模糊数字保留原文，不转换成精确统计。")
    login, close, clear = st.columns(3)
    state = account_browser().job_status()
    busy = bool(state and state["status"] == "running")
    if login.button("打开小红书登录窗口", width="stretch", disabled=busy):
        try:
            with st.spinner("正在打开小红书窗口…"):
                account_browser().open_login()
            st.success("小红书窗口已打开。请在里面点击“登录”，自行扫码或按页面提示登录，然后回来读取账号。")
        except AccountReadError as exc:
            st.warning(str(exc))
    if close.button("关闭小红书窗口", width="stretch", disabled=busy):
        try:
            account_browser().close()
            st.info("窗口已关闭。本机保存的登录信息保留，是否仍有效由小红书决定。")
        except AccountReadError as exc:
            st.warning(str(exc))
    if clear.button("清除本机登录", width="stretch", disabled=busy):
        st.session_state.pop("public_snapshot", None)
        try:
            account_browser().clear_login()
            st.success("已关闭专用窗口并清除本机登录信息，下次需要重新登录。")
        except AccountReadError as exc:
            st.warning(str(exc))
    st.caption("登录信息仅保存在本项目的专用浏览器中，不使用你日常浏览器的登录资料。请勿在分析台中填写密码或验证码；关闭窗口不等于退出登录。")
    use_login = st.checkbox("使用我的小红书登录状态访问目标账号", value=True, disabled=busy)
    link = st.text_input("粘贴账号主页链接或分享文字", placeholder="https://www.xiaohongshu.com/user/profile/… 或 https://xhslink.cn/o/…", disabled=busy)
    limit = st.number_input("本次最多读取多少篇", min_value=1, max_value=1000, value=100, step=10, disabled=busy)
    include_details = st.checkbox("逐篇打开笔记，补充收藏和评论", value=True, disabled=busy)
    st.caption("逐篇读取需要更长时间；访问验证时会停止，不自动重试。模糊数字和未显示的数据仍保留为未确认。")
    if st.button("开始读取账号数据", type="primary", disabled=busy):
        st.session_state.pop("public_snapshot", None)
        st.session_state.pop("public_job_error", None)
        try:
            account_browser().start_read(link, limit=int(limit), include_details=include_details, use_login=use_login)
            st.rerun()
        except AccountReadError as exc:
            st.warning(str(exc))
    public_read_progress()
    if st.session_state.get("public_job_error"):
        st.warning(st.session_state["public_job_error"])
    saved = st.session_state.get("public_snapshot")
    if not saved:
        st.download_button("导出公开账号数据与分析（Excel）", data=b"", file_name="公开账号.xlsx", disabled=True, key="empty-public-export")
        st.caption("读取账号后，可以在V2五模块分析下方导出全部已读取数据与分析结果。")
        return
    render_public_snapshot(saved["data"])


def render_public_snapshot(snapshot):
    notes = pd.DataFrame(normalize_notes(snapshot["notes"]))
    for metric in METRICS:
        notes[metric] = pd.to_numeric(notes[metric], errors="coerce")
    st.write(f"**{snapshot['name']}**")
    st.link_button("查看来源主页", snapshot["url"])
    if snapshot.get('is_case_study'):
        st.caption(f"真实案例快照 · {snapshot['captured_at'][:10]}采集 · {len(notes)}篇 · 非实时；详细来源见页面底部。")
    else:
        st.caption(f"读取时间：{snapshot['captured_at']}；设定上限 {snapshot.get('requested_limit', len(notes))} 篇，本次找到 {len(notes)} 篇。")
        st.info(f"读取结束原因：{snapshot.get('stop_reason', '已完成')}。详情成功读取 {snapshot.get('successful_details', 0)}/{len(notes)} 篇。")
        for warning in snapshot.get("warnings", []):
            st.warning(warning)
        with st.expander("主页账号指标（前台显示原文）"):
            st.text(snapshot["profile_text"])
    columns = st.columns(4)
    columns[0].metric("本次读取篇数", len(notes))
    for column, metric in zip(columns[1:], METRICS):
        column.metric(f"可确认{metric}合计", metric_text(notes[metric].sum(min_count=1)))
    for column, metric in zip(st.columns(3), METRICS):
        column.metric(f"平均{metric}（可确认）", metric_text(notes[metric].mean(), 2))
    st.caption("数据完整度：" + "；".join(f"{metric} {notes[metric].count()}/{len(notes)} 篇" for metric in METRICS)
               + "。平均值只使用该项已确认的数据，不推算全账号总量。")
    notes = add_ratios(notes)
    for ratio in ['藏赞比','评赞比']:
        notes[ratio]=notes[ratio].map(lambda value: '—' if pd.isna(value) else f'{value:.2%}')
    links = {"笔记链接": st.column_config.LinkColumn("笔记链接", display_text="打开笔记")}
    st.dataframe(notes.drop(columns=["正文", "封面链接", "可见商品入口"], errors="ignore"), hide_index=True, width="stretch", column_config=links)
    for tab, metric in zip(st.tabs([f"{metric} TOP10" for metric in METRICS]), METRICS):
        with tab:
            ranked = notes.dropna(subset=[metric]).sort_values(metric, ascending=False, kind="stable").head(10)
            if ranked.empty:
                st.info(f"本次没有可确认的{metric}数据，暂时无法排行。")
            else:
                st.dataframe(ranked[["标题", metric, "笔记链接"]], hide_index=True, width="stretch", column_config=links)
    from content_ui import render_content_analysis
    render_content_analysis(snapshot)


@st.fragment(run_every="1s")
def creator_read_progress():
    state = account_browser().job_status()
    if not state or state.get("kind") != "creator":
        return
    if state["status"] == "running":
        st.progress(min(state["loaded"] / max(state["requested"], 1), 1.0), text=state["message"])
        if st.button("停止同步并保留结果", key="stop-creator-read"):
            account_browser().cancel_read(state["id"])
            st.info("已请求停止，当前页面操作结束后会显示已确认的数据。")
    elif st.session_state.get("creator_job_consumed") != state["id"]:
        st.session_state["creator_job_consumed"] = state["id"]
        if state["status"] == "done":
            st.session_state["creator_snapshot"] = state["result"]
        else:
            st.session_state["creator_error"] = state["error"]
        st.rerun()


def creator_account_page():
    from account_reader import AccountReadError

    if public_mode():
        st.subheader('自有账号后台数据')
        st.info('后台同步需要账号所有者在本机浏览器登录。原版同步功能保留在本地模式；在线可上传包含曝光、观看、涨粉等字段的 Excel，继续使用后台指标分析。')
        return

    st.subheader("自有账号后台数据")
    st.info("在专用窗口登录小红书创作服务平台后，可以同步账号总览和笔记明细。只读取后台页面中已显示的数据。")
    state = account_browser().job_status()
    busy = bool(state and state["status"] == "running")
    left, right = st.columns(2)
    if left.button("打开创作平台登录窗口", width="stretch", disabled=busy):
        try:
            account_browser().open_creator()
            st.success("创作平台窗口已打开。请在小红书官方页面完成登录，再回来点击同步。")
        except AccountReadError as exc:
            st.warning(str(exc))
    if right.button("检查创作平台登录", width="stretch", disabled=busy):
        try:
            status = account_browser().creator_status()
            st.success(status["status"])
        except AccountReadError as exc:
            st.warning(str(exc))
    st.caption("密码和验证码只填在小红书窗口。后台登录与公开主页登录可能需要分别完成；登录状态保存在本项目专用浏览器中。")
    period = st.selectbox("账号总览统计周期", ["近 7 日", "近 30 日"], disabled=busy)
    limit = st.number_input("本次最多同步多少篇后台笔记", min_value=1, max_value=1000, value=100, step=10, disabled=busy)
    st.caption("笔记明细按创作平台“内容分析”里的首发时间、笔记类型筛选读取，自动从第一页翻页。需要其他日期时，先在该窗口调整筛选，再同步。后台目前提示只支持近半年发布的笔记。")
    if busy and state.get("kind") != "creator":
        st.warning("公开账号读取正在进行，请先到“公开账号”停止或等待完成。")
    if st.button("同步后台数据", type="primary", disabled=busy):
        st.session_state.pop("creator_error", None)
        st.session_state.pop("creator_snapshot", None)
        try:
            account_browser().start_creator_read(days=7 if period == "近 7 日" else 30, limit=int(limit))
            st.rerun()
        except AccountReadError as exc:
            st.warning(str(exc))
    creator_read_progress()
    if st.session_state.get("creator_error"):
        st.warning(st.session_state["creator_error"])
    result = st.session_state.get("creator_snapshot")
    if not result:
        st.download_button("导出自有账号数据与分析（Excel）", data=b"", file_name="自有账号.xlsx", disabled=True, key="empty-creator-export")
        st.caption("同步后台数据后即可导出 Excel。")
        return
    overview = result["overview"]
    st.write(f"**{overview['name']}** · 小红书账号：{overview['account_id']}")
    st.caption(f"同步时间：{result['captured_at']}")
    st.info(result["stop_reason"])
    for warning in result["warnings"]:
        st.warning(warning)
    from excel_export import creator_workbook, export_filename, MIME
    from result_cache import session_cache,EXPORT_VERSION
    raw_report=session_cache('exports').get('creator-raw',[EXPORT_VERSION,result],lambda:creator_workbook(result))
    st.download_button("导出自有账号数据与分析（Excel）", raw_report,
                       file_name=export_filename("自有账号", overview["name"], result["captured_at"]),
                       mime=MIME, key="creator-excel")
    st.caption("导出账号期间总览、已读取笔记、互动汇总、排行榜和发布时间趋势。中途停止时也可导出已确认的部分结果。")
    st.subheader("账号总览")
    st.caption(f"近 {result['days']} 日 · {overview['period']}。保留后台原文和环比；“万”等缩略值不作为精确总数。")
    st.dataframe(pd.DataFrame(overview["metrics"]), hide_index=True, width="stretch")
    st.subheader("后台笔记明细")
    filters = result["filters"]
    if filters:
        st.caption(f"笔记首发时间：{filters['start']} 至 {filters['end']}；类型：{filters['type']}。后台符合筛选共 {result['platform_total']} 篇，本次读取 {len(result['notes'])} 篇。")
    st.caption("以下合计与平均值仅针对本次读取的笔记，采用后台表中显示的数值；与上面的账号期间总览口径不同。")
    if not result["notes"]:
        st.info("本次没有读到后台笔记明细，请查看上方停止原因。")
        return
    notes = pd.DataFrame(normalize_notes(result["notes"]))
    for metric in METRICS + ["曝光", "观看"]:
        if metric in notes:
            notes[metric] = pd.to_numeric(notes[metric], errors="coerce")
    columns = st.columns(4)
    columns[0].metric("已读取后台笔记", len(notes))
    for column, metric in zip(columns[1:], METRICS):
        column.metric(f"已确认{metric}合计", metric_text(notes[metric].sum(min_count=1)))
    for column, metric in zip(st.columns(3), METRICS):
        column.metric(f"平均{metric}", metric_text(notes[metric].mean(), 2))
    st.caption("互动数据完整度：" + "；".join(f"{metric} {notes[metric].count()}/{len(notes)} 篇" for metric in METRICS))
    notes = add_ratios(notes)
    main_columns = [column for column in notes if not column.startswith("后台")]
    show_table(notes[main_columns])
    with st.expander("查看后台各项数字原文"):
        show_table(notes)
    for tab, metric in zip(st.tabs([f"{metric} TOP10" for metric in METRICS]), METRICS):
        with tab:
            show_table(notes.dropna(subset=[metric]).sort_values(metric, ascending=False, kind="stable").head(10)[["标题", "发布时间", metric]])
    chart = notes.assign(发布时间=pd.to_datetime(notes["发布时间"], errors="coerce")).dropna(subset=["发布时间", "点赞"])
    if not chart.empty:
        st.write("**按笔记首发日期比较平均点赞**")
        chart["发布日期"] = chart["发布时间"].dt.date
        st.line_chart(chart.groupby("发布日期", as_index=False)["点赞"].mean(), x="发布日期", y="点赞")
    from content_ui import render_content_analysis
    render_content_analysis(dict(result, name=overview['name'], url=result.get('source', ''), bio='',
        source_kind='自有账号后台', creator_data=result,
        scope=f"后台当前筛选：{filters}；本次{len(result['notes'])}篇，符合筛选{result.get('platform_total')}篇。账号期间总览与笔记汇总不同口径。"))


def show_table(df):
    display = df.copy()
    for column in ["藏赞比", "评赞比", "占比", "爆款率"]:
        if column in display:
            display[column] = display[column].map(lambda value: "—" if pd.isna(value) else f"{value:.2%}")
    st.dataframe(display, hide_index=True, width="stretch")


def real_case_page(cases):
    from real_cases import case_snapshot, NOTICE
    st.subheader('真实账号案例')
    st.caption('使用已采集的真实公开信息体验分析，无需登录。这里不会实时访问账号。')
    options = {case['id']: case for case in cases}
    chosen = st.selectbox('选择真实案例', list(options), format_func=lambda item: options[item]['name'])
    selected = options[chosen]
    if selected.get('category'):
        st.write('领域：' + selected['category'])
    historical = ' · 历史作品样本' if '历史' in selected['scope'] else ''
    st.caption(f"{selected['captured_at'][:10]}采集 · {len(selected['notes'])}篇公开笔记{historical}")
    st.link_button('核对账号来源', selected['url'])
    if st.button('加载真实账号案例', type='primary'):
        st.session_state['active-real-case-id'] = chosen
    active = st.session_state.get('active-real-case-id')
    if active == chosen:
        st.info('当前分析案例：' + options[active]['name'])
        render_public_snapshot(case_snapshot(options[active]))
    else:
        st.info(NOTICE)


def main():
    st.set_page_config(page_title="AI运营工作台", page_icon="🌿", layout="wide")
    st.html("<style>" + Path(__file__).with_name("theme.css").read_text(encoding="utf-8") + "</style>")
    st.title("AI运营工作台")
    st.caption('AI运营分析台 V3 · 作品集公开演示' if public_mode() else '分析小红书历史内容与公开主页数据 · 本地运行')
    if public_mode():
        st.info('无需注册：选择“真实账号案例”分析真实公开快照，或点击“加载演示数据”体验模拟账号。AI助手采用规则演示，不调用付费API。')
        st.caption('上传文件仅用于当前访客会话的分析；不会保存到共享项目目录。请勿上传个人隐私或商业机密，离开前可下载报告与项目存档。')
    from project_ui import project_picker
    project_picker()
    from real_cases import list_cases
    cases = list_cases()
    sources = ["Excel 文件", "公开账号", "我的账号后台"]
    if cases:
        sources.insert(1, "真实账号案例")
    mode = st.radio("数据来源", sources, horizontal=True, width="stretch")
    if st.session_state.get('show_saved_project') and st.session_state.get('active_project'):
        from content_ui import render_content_analysis
        render_content_analysis(st.session_state['active_project']['snapshot'])
        return
    if mode == "真实账号案例":
        real_case_page(cases)
        return
    if mode == "公开账号":
        public_account_page()
        return
    if mode == "我的账号后台":
        creator_account_page()
        return
    st.info('支持多工作表和带标题行的 Excel，自动寻找笔记明细及表头。只有标题也可分析初步选题；补充正文和指标后可支持更多分析，缺失数值不按零处理。')
    with st.expander("查看 Excel 格式说明"):
        st.write("识别“标题 / 笔记标题”“发布时间 / 前台日期”“图文/视频 / 内容形式”等常见列名，以及点赞数、收藏数、评论数。")
        st.write("发布时间建议填写为 2026-09-01；精确互动量填写非负整数或1,200。1.2万、1千+等缩略原文保留为近似/下界估计，不参加精确合计、均值和排行；空值也不按0处理。")
        st.write("执行选题后可添加“对应选题”或“选题编号”列，填入选题池编号；空白和占位文本记为未关联。")
        st.write("每一行都计为一篇笔记；同标题不会自动去重。请勿把合计行放在数据中。")
    from demo_data import SCENARIOS, DemoUpload, demo_workbook
    scenario = st.selectbox('选择演示账号类型', list(SCENARIOS))
    load, clear = st.columns(2)
    if load.button('加载演示数据', type='primary', width='stretch'):
        st.session_state['demo_scenario'] = scenario
    if clear.button('清除演示数据', width='stretch', disabled='demo_scenario' not in st.session_state):
        st.session_state.pop('demo_scenario', None)
    st.download_button('下载模拟示例 Excel', data=demo_workbook(scenario), file_name=f'模拟数据_{scenario}.xlsx',
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    uploaded = st.file_uploader("上传 .xlsx 文件", type=["xlsx"])
    is_demo = uploaded is None and 'demo_scenario' in st.session_state
    if is_demo:
        uploaded = DemoUpload(st.session_state['demo_scenario'])
        st.warning(DEMO_NOTICE + ' 当前场景：' + st.session_state['demo_scenario'])
    elif uploaded is not None and 'demo_scenario' in st.session_state:
        st.caption('当前分析你上传的文件；清除上传后可继续体验演示数据。')
    if uploaded is None:
        st.caption("上传后会显示数据概览、三个 TOP10、主题分组和基础图表。")
        return
    try:
        contents = uploaded.getvalue()
        structure = workbook_structure(contents)
        file_key = hashlib.sha256(contents).hexdigest()[:12]
        candidates = structure["candidates"]
        default_sheet = candidates[0]["sheet"] if candidates else structure["sheets"][0]
        with st.expander("读取设置：工作表与表头", expanded=not candidates):
            sheet = st.selectbox("选择笔记明细工作表", structure["sheets"],
                                 index=structure["sheets"].index(default_sheet), key=f"sheet-{file_key}")
            detected = next((item for item in candidates if item["sheet"] == sheet), None)
            header_row = st.number_input("表头在 Excel 的第几行", min_value=1, max_value=500,
                                         value=detected["header_row"] if detected else 1,
                                         key=f"header-{file_key}-{sheet}")
            st.caption("自动检查每个工作表的前 30 行。汇总页和透视表不作为笔记明细；识别不准确时，可在这里手动选择。")
        df, messages = read_excel(contents, sheet_name=sheet, header_row=int(header_row))
    except ValueError as exc:
        st.error(str(exc))
        return
    except Exception:
        st.error("无法读取这个文件。请确认它是未加密的 .xlsx 文件，并在 Excel 中重新另存为 .xlsx 后上传。")
        return
    for message in messages:
        st.warning(message)
    source = df.attrs["source"]
    st.caption(f"数据来源：{source['sheet']} · 第 {source['header_row']} 行表头")
    if source["mappings"]:
        st.caption("已识别列名：" + "；".join(f"{original} → {mapped}" for original, mapped in source["mappings"].items()))
    st.success(f"已读取 {len(df)} 篇笔记。")
    st.subheader("数据概览")
    summary = summarize(df)
    for column, label in zip(st.columns(4), ["总发布篇数", "总点赞", "总收藏", "总评论"]):
        shown_label = label
        if label != "总发布篇数" and df[label[1:]].isna().any():
            shown_label = f"已确认{label[1:]}合计"
        column.metric(shown_label, metric_text(summary[label]))
    for column, label in zip(st.columns(3), ["平均点赞", "平均收藏", "平均评论"]):
        column.metric(label, metric_text(summary[label], 2))
    st.caption("数据完整度：" + "；".join(f"{metric} {df[metric].count()}/{len(df)} 篇" for metric in METRICS)
               + "。每项平均值 = 该项已确认合计 ÷ 该项已确认篇数；全部缺失时显示“—”。")

    st.subheader("互动比值与笔记明细")
    st.caption("藏赞比 = 收藏 ÷ 点赞；评赞比 = 评论 ÷ 点赞。点赞为 0 或所需数据缺失时显示“—”。这些比值不是按曝光量计算的转化率，可能超过 100%。")
    details = ["标题"] + (["原始日期"] if "原始日期" in df else []) + METRICS + ["藏赞比", "评赞比"]
    if '对应选题' in df:
        details.append('对应选题')
    if "数据状态" in df:
        details.append("数据状态")
    with st.expander("查看每篇笔记的藏赞比、评赞比和明细", expanded=True):
        show_table(df[details])
    with st.expander('查看数字原文、数值与精度'):
        columns=['标题']+[metric+suffix for metric in COUNT_FIELDS for suffix in ['原文','数值','精度'] if metric+suffix in df]
        st.dataframe(df[columns],hide_index=True,width='stretch')
        st.caption('“数值”可能只是原文的估计或下界；只有标为“精确”的记录用于汇总、比值和排行。')

    st.subheader("表现 TOP10")
    for tab, metric in zip(st.tabs([f"{metric} TOP10" for metric in METRICS]), METRICS):
        with tab:
            ranked = df.dropna(subset=[metric]).sort_values(metric, ascending=False, kind="stable").head(10)[details].copy()
            ranked.insert(0, "排名", range(1, len(ranked) + 1))
            if ranked.empty:
                st.info(f"还没有已确认的{metric}数据，暂时无法排行。")
            else:
                show_table(ranked)
    st.caption("各榜单只使用该项已确认的笔记；不足 10 篇时显示全部，数值相同时按 Excel 原有顺序排列。")

    st.subheader("内容主题 / 产品系列分析")
    groups = [column for column in GROUP_COLUMNS if column in df]
    if groups:
        selected = st.selectbox("选择分组字段", groups)
        st.dataframe(group_summary(df, selected).round(2), hide_index=True, width="stretch")
        st.caption("内容数量包含该组全部笔记；各项平均值忽略该项未确认数据，全组都缺失的指标留空。")
    else:
        st.info("添加“内容主题”或“产品系列”列后，即可查看分组分析。也支持“产品系列/内容主题”列名。")

    st.subheader("基础图表")
    st.write("**各笔记点赞排行**")
    ranking = df.dropna(subset=["点赞"]).sort_values("点赞", ascending=False, kind="stable").copy()
    ranking["笔记"] = [f"{position}. {title}" for position, title in enumerate(ranking["标题"], 1)]
    if ranking.empty:
        st.info("没有已确认的点赞数据，暂时无法绘图。")
    else:
        st.bar_chart(ranking, x="笔记", y="点赞", sort="-点赞", color="#EC6A8D")

    st.write("**各内容类型平均点赞**")
    content_type = next((column for column in TYPE_COLUMNS if column in df), None)
    if content_type:
        averages = group_summary(df, content_type).dropna(subset=["平均点赞"])
        if averages.empty:
            st.info("没有已确认的点赞数据，暂时无法比较内容类型。")
        else:
            st.bar_chart(averages, x=content_type, y="平均点赞", sort="-平均点赞", color="#7C83DB")
    else:
        st.info("添加“图文/视频”或“内容类型”列后，即可查看类型对比。")

    st.write("**发布时间与点赞趋势**")
    st.caption("按发布日期汇总每篇笔记的当前点赞量，展示当天发布笔记的平均点赞；并非每日新增点赞。")
    if "发布时间" not in df or df["发布时间"].notna().sum() == 0:
        st.info("提供有效的“发布时间”后，即可查看时间趋势。")
    else:
        trend = daily_trend(df)
        if trend.empty:
            st.info("需要同一篇笔记同时有有效发布时间和已确认点赞，才能绘制趋势。")
        else:
            st.line_chart(trend, x="发布时间", y="平均点赞", color="#EC6A8D")
        if len(trend) == 1:
            st.caption(f"目前只有一个有效发布日期，当日平均点赞为 {trend['平均点赞'].iloc[0]:,.2f}。")


    for heading, dimension, builder, color in [
            ('各星期平均互动', '星期', weekly_pattern, '#EC6A8D'),
            ('各时段平均互动', '时段', hourly_pattern, '#7C83DB')]:
        st.write('**'+heading+'**')
        pattern = builder(df)
        if pattern.empty:
            st.info('提供有效发布时间后可查看周几规律。' if dimension == '星期' else '提供包含具体时分的有效发布时间后可查看时段规律。')
        elif pattern['平均点赞'].notna().any():
            st.bar_chart(pattern.dropna(subset=['平均点赞']), x=dimension, y='平均点赞', sort=False, color=color)
        else:
            st.info('已识别发布时间，但没有可确认的点赞数据，暂时无法绘图。')
        if not pattern.empty:
            show_table(pattern)
        st.caption('按发布日期分组展示当天发布笔记的当前累计平均互动；观察时长不同时不在此直接断言“最近下降”；样本少时仅供参考。')
        if dimension == '时段':
            st.caption('仅有日期、没有具体时分的记录不参与时段分析；凌晨和深夜分别统计。')


    st.write('**表现分层与内容稳定性**')
    tiers = performance_tiers(df)
    middle, rate = st.columns(2)
    middle.metric('点赞中位数', metric_text(tiers['median'], 2))
    rate.metric('爆款率', '—' if pd.isna(tiers['viral_rate']) else f"{tiers['viral_rate']:.0%}")
    if tiers['status'] == '样本不足':
        st.info('样本不足，暂不做分层；至少需要4篇精确点赞数据。')
    else:
        if tiers['status'] == '四分位重合':
            st.info('上下四分位重合，当前有效笔记统一归为中坚，暂不区分爆款。')
        show_table(tiers['summary'])
    st.caption(f"精确点赞有效 {tiers['valid_count']}/{len(df)} 篇；下四分位 {metric_text(tiers['p25'],2)}，上四分位 {metric_text(tiers['p75'],2)}。")
    st.caption('爆款按本账号有效篇数的上四分位划分，用于衡量内容稳定性，不预示单篇表现。阈值并列会全部纳入，占比可能高于25%；全表有多个账号时，此处为工作表整体基准，各账号基准见横向对比。')


    comparison = account_comparison(df)
    if not comparison.empty:
        st.subheader('多账号横向对比')
        show_table(comparison)
        comparable = comparison.dropna(subset=['平均点赞'])
        if not comparable.empty:
            st.bar_chart(comparable, x='账号', y='平均点赞', sort=False, color='#7C83DB')
        st.caption('各账号分别统计；藏赞比、评赞比为逐篇有效比值的均值，不是合计相除。爆款率采用各账号自己的上四分位基准；样本不足或阈值重合时留空。')
        st.caption('未填写账号的记录不进入横向对比；不同粉丝规模、发布时间与观察时长会影响结果，不能仅据平均互动判断运营优劣。')

    # V2 与原有统计共用清洗后的记录，保留原统计、图表与读取设置。
    account_frame = df
    account_name = Path(uploaded.name).stem
    if '账号名称' in df:
        account_names = df['账号名称'].fillna('未填写账号').astype(str)
        unique_names = account_names.unique().tolist()
        if len(unique_names) > 1:
            account_name = st.selectbox('选择需要进行V2分析的账号', unique_names, key=f'v2-account-{file_key}-{sheet}')
            account_frame = df[account_names.eq(account_name)]
            st.caption('上方基础统计为当前工作表整体数据；下方V2仅分析所选账号，避免混合定位。')
        elif unique_names:
            account_name = unique_names[0]
    bio = ''
    if '账号简介' in account_frame:
        bio = '\n'.join(account_frame['账号简介'].dropna().astype(str).drop_duplicates().tolist()[:3])
    source_id = f"{file_key}-{sheet}-{header_row}-{account_name}"
    time_key = f'v2-import-time-{source_id}'
    if time_key not in st.session_state:
        st.session_state[time_key] = datetime.now().astimezone().isoformat(timespec='seconds')
    from content_ui import render_content_analysis
    render_content_analysis({'name': account_name, 'url': f'Excel：{uploaded.name} / {sheet}', 'bio': bio,
        'captured_at': st.session_state[time_key], 'notes': account_frame.to_dict('records'),
        'source_kind': '模拟数据演示（非真实运营数据）' if is_demo else 'Excel上传', 'is_demo': is_demo,
        'scope': f'{uploaded.name} / {sheet} / 第{header_row}行表头；账号：{account_name}；共{len(account_frame)}篇。',
        'stop_reason': '已读取所选Excel明细', 'requested_limit': len(account_frame)})


if __name__ == "__main__":
    main()
