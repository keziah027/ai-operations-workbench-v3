"""上传表格、公开账号和自有后台共用的 V2 分析界面。"""
import hashlib
import json
from html import escape
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from account_profile import identify_account, IDENTITIES, DOMAINS, GOALS, INSUFFICIENT, clean, commerce_context
from account_diagnosis import diagnose
from note_schema import normalize_notes,THEME_FIELDS,COUNT_FIELDS
from performance import sample_audit, backend_tables
from dynamic_topics import discover_topics, OTHER
from topic_ui import render_topic_editor
from topic_state import review_topics
from packaging_analysis import packaging_tables
from audience_ui import edit_audience
from diagnosis_evidence import ANALYSIS_GOALS
from project_ui import prepare_context,save_controls
from result_cache import session_cache,report_bytes
from ai_ui import render_ai
from ai_report import markdown_appendix
from content_analysis import COVERS, build_annotations, build_detail, pillar_summary, audience_signals, high_interaction


def cached_topics(notes):
    return session_cache('topics').get('discover', notes, lambda: discover_topics(notes))


def show_sources(frame, columns):
    st.dataframe(frame[[col for col in columns if col in frame]], hide_index=True, width='stretch', column_config={
        '笔记链接': st.column_config.LinkColumn('笔记链接', display_text='打开笔记')})


def markdown_report(snapshot, analysis):
    def rows(frame):
        return ['- ' + '；'.join(f'{col}：{value}' for col, value in row.items() if pd.notna(value)) for row in frame.to_dict('records')]
    lines = [f"# {snapshot['name']} · 账号运营分析 V3", f"读取时间：{snapshot['captured_at']}；样本 {len(snapshot['notes'])} 篇。",
             f"来源：{snapshot.get('source_kind', '公开账号')}；{snapshot.get('url', '')}",
             '本地文本归纳与人工修订；置信度是证据强度，不是预测概率。当前样本的相关性不证明因果。',
             '## ① 账号画像', f"身份初判：{analysis['profile']['identity']}；置信度：{analysis['profile']['identity_confidence']}；当前采用：{analysis['identity']}",
             '领域：'+ '、'.join(analysis['domains']), '用户确认目标：'+('、'.join(analysis['goals']) or '尚未确认'),
             analysis['profile']['reason'], analysis['position'], analysis['audience'] or INSUFFICIENT,
             *rows(analysis['audience_findings']), '## ② 内容结构',
             '藏赞比/评赞比为各笔记比值的平均值；点赞为0或所需指标缺失的笔记不参与。',
             *rows(analysis['summary']), *rows(analysis.get('final_topics',pd.DataFrame())), '## ③ 高互动规律',
             f"比较指标：{analysis['metric']}；有效{len(analysis['valid'])}篇，高互动组{len(analysis['top'])}篇。",
             '标题、正文、封面分别只用已读取或已标注样本比较，每组至少2篇。',
             *(rows(analysis['comparisons']) or [INSUFFICIENT]), '## ④ 内容包装']
    for _, item in analysis['detail'].iterrows():
        lines.append(f"- 第{item['序号']}篇 {item['标题']}：{item['主支柱']}；封面：{item['封面类型']} {item['封面观察']}；"
                     f"原自动分类：{item.get('自动主支柱','')}；自动依据：{item.get('自动分类依据','')}；{item['特征依据']}；正文结构：{item['正文结构']}；来源：{item['笔记链接']}")
        lines.append(f"  自动分类：{item.get('自动主支柱','')}；自动依据：{item.get('自动分类依据','')}；"
                     f"辅助标签：{item.get('封面辅助标签','')}；已复核：{item.get('辅助标签已复核',False)}；人工正文结构：{item.get('正文结构（人工）','待标注')}")
    lines.append('封面类型配置：'+ '、'.join(analysis.get('editing',{}).get('packaging',{}).get('cover_types',[])))
    for name,table in analysis.get('packaging_tables',{}).items():
        lines += ['### '+name,*rows(table)]
    lines += ['## ⑤ 运营诊断', '本次分析重点：'+'、'.join(analysis.get('analysis_goals',[])), *rows(analysis['diagnosis']), '人工补充：' + (analysis['diagnosis_note'] or '未填写'),
              '## 比较样本范围', *rows(analysis['sample_audit'])]
    for name,table in analysis['backend_tables'].items():
        lines += ['## '+name, *rows(table)]
    lines += ['## 人群假设复核记录（含已删除候选）',*rows(analysis.get('audience_all',pd.DataFrame()))]
    if snapshot.get('is_case_study'):
        lines += ['## 真实案例来源与限制', snapshot.get('category', ''), snapshot.get('selection_basis', ''),
                  snapshot.get('scope', ''), snapshot.get('collection_method', ''),
                  *snapshot.get('warnings', []), '### 内容概述（阅读后整理，非作者原文）']
        lines += [f"- {note['标题']}：{note.get('内容概述（整理）', '')}" for note in snapshot['notes']]
    lines.append(markdown_appendix(analysis.get('ai',{})))
    return '\n\n'.join(lines)


def render_content_analysis(snapshot):
    if snapshot.get('is_demo'):
        from deployment import DEMO_NOTICE
        st.warning(DEMO_NOTICE)
    if snapshot.get('is_case_study'):
        st.info(snapshot.get('scope', '真实账号公开信息快照，非实时数据。'))
        with st.expander('案例来源、内容概述与分析限制'):
            for warning in snapshot.get('warnings', []):
                st.write(warning)
            show_sources(pd.DataFrame(snapshot['notes']), ['标题', '内容概述（整理）', '笔记链接'])
    notes = normalize_notes(snapshot.get('notes', []))
    st.subheader('账号运营分析 · V3')
    from deployment import public_mode
    st.caption('前五模块由程序计算，可人工修订。第六模块为规则演示，不向AI服务发送数据。' if public_mode() else '前五模块在本地计算，可人工修订。第六模块为可选AI助手，仅在点击生成或发送问题时发送预览摘要。')
    if not notes:
        st.info(INSUFFICIENT)
        return
    key = hashlib.sha256(json.dumps([snapshot.get('url'), snapshot.get('captured_at'), notes], ensure_ascii=False, default=str).encode()).hexdigest()[:16]
    if st.session_state.get('restore_epoch'): key+='-r'+str(st.session_state['restore_epoch'])
    text_notes=[{field:note.get(field,'') for field in ['标题','正文',*THEME_FIELDS]} for note in notes]
    topics = cached_topics(text_notes)
    calculations=session_cache('analysis')
    prepare_context(snapshot,topics,key)
    tabs = st.tabs(['① 账号画像', '② 内容结构', '③ 高互动规律', '④ 内容包装', '⑤ 运营诊断', '⑥ AI运营助手'])
    with tabs[0]:
        bio_key = f'bio-v2-{key}'
        bio = st.text_area('账号简介（可补充或修正）', value=st.session_state.get(bio_key, clean(snapshot.get('bio'))), key=bio_key)
        profile = identify_account(notes, bio)
        st.write(f"**身份初判：{profile['identity']} · 置信度：{profile['identity_confidence']}**")
        st.write(profile['reason'])
        st.caption(profile['method'])
        with st.expander('查看身份与领域识别依据'):
            st.dataframe(profile['candidates'], hide_index=True, width='stretch')
        choice = st.selectbox('账号身份（可修改）', ['采用自动初判'] + IDENTITIES, key=f'identity-v21-{key}')
        identity = profile['identity'] if choice == '采用自动初判' else choice
        domains_key = f'domains-v21-{key}'
        domains = st.multiselect('内容领域（可多选）', DOMAINS, default=st.session_state.get(domains_key, profile['domains']), key=domains_key)
        goals = st.multiselect('运营目标（由你确认，可多选）', GOALS, key=f'goals-v21-{key}')
        selection = {'identity':identity, 'domains':domains, 'goals':goals}
        commerce = commerce_context(notes, goals)
        st.caption('身份、领域与目标分别记录。未选择目标时不推断经营意图；销售目标或实际商品线索可启用商品承接分析。')
        position = st.text_area('你的账号定位结论', key=f'position-v2-{key}', placeholder='结合简介和笔记证据填写定位。')
        audience = st.text_area('你的核心人群假设及待验证问题', key=f'audience-v2-{key}', placeholder='记录有依据的兴趣和需求；真实粉丝画像需后台数据验证。')
        audience_area = st.container()
    with tabs[1]:
        st.write('**这个账号主要在发什么？**')
        st.caption(topics['method'])
        if len(topics['labels']) < 3:
            st.info('当前可区分的主题不足3类，保留实际归纳结果；补充更多不同选题的标题和正文后再判断。')
        if not topics['topics'].empty:
            with st.expander('查看主题归纳依据及代表笔记'):
                st.dataframe(topics['topics'], hide_index=True, width='stretch')
        with st.expander('调整主题名称与逐篇分类'):
            annotations, editing = render_topic_editor(notes, topics, key, commerce['enabled'])
        frame = calculations.get('detail-v1',[notes,annotations],lambda:build_detail(notes,annotations))
        final_topics=calculations.get('topic-review-v1',frame[['主题ID','主支柱','序号','标题','正文','分类置信度']],lambda:review_topics(frame))
        with st.expander('复核最终主题与代表笔记'):
            st.dataframe(final_topics,hide_index=True,width='stretch')
            for _,topic in final_topics.iterrows():
                with st.expander(f"{topic['最终主题']} · {topic['篇数']}篇"):
                    group=frame[frame['主题ID'].eq(topic['主题ID'])]
                    show_sources(group,['序号','标题','主支柱','自动主支柱','分类依据','分类置信度','笔记链接'])
            st.write('**分类模糊，建议优先复核**')
            show_sources(frame[frame['分类置信度'].eq('低')],['序号','标题','主支柱','自动主支柱','分类依据','笔记链接'])
        stat_fields=['主支柱','标题','正文','发布时间','内容形式',*COUNT_FIELDS,'藏赞比','评赞比','观看曝光比','每千次观看涨粉']
        summary,tables = calculations.get('statistics-v1',frame[stat_fields],lambda:(pillar_summary(frame),backend_tables(frame)))
        with st.expander('数据完整度与可支持的分析'):
            st.dataframe(tables['数据完整度'], hide_index=True, width='stretch')
        if frame['正文'].ne('').sum()==0:
            st.info('当前只有标题等基础字段：提供初步选题与标题分析；正文结构和完整运营诊断暂无法判断。')
        st.caption(f"样本 {len(frame)} 篇 · 正文已读 {frame['正文'].ne('').sum()} 篇 · 其他/待确认 {frame['主支柱'].eq(OTHER).sum()} 篇 · 低置信度初判 {annotations['分类置信度'].eq('低').sum()} 篇，建议优先复核。")
        st.dataframe(summary, hide_index=True, width='stretch', column_config={
            '藏赞比': st.column_config.NumberColumn('藏赞比（均值）', format='percent'),
            '评赞比': st.column_config.NumberColumn('评赞比（均值）', format='percent')})
        st.caption('占比按全部样本计算。各项均值仅用该项有效数据；藏赞比/评赞比 = 每篇收藏/点赞、评论/点赞的平均值，点赞为0或数据缺失时不参与。不是曝光转化率，可超过100%。')
        chart_metric = st.selectbox('比较各支柱的表现', ['篇数', '平均点赞', '平均收藏', '平均评论', '藏赞比', '评赞比'], key=f'pillar-metric-v2-{key}')
        plot = summary.dropna(subset=[chart_metric])
        if not plot.empty:
            st.bar_chart(plot, x='主支柱', y=chart_metric, sort=False)
        else:
            st.info(INSUFFICIENT)
        show_sources(frame, ['序号', '标题', '主支柱', '分类置信度', '笔记链接'])
    audience_findings = calculations.get('audience-v1',[frame[['序号','标题','正文','主支柱','笔记链接']],bio],lambda:audience_signals(frame,bio))
    with audience_area:
        st.write('**内容面向的人群假设**')
        audience_auto=audience_findings.copy()
        audience_findings,audience_all=edit_audience(audience_auto,key)
        if audience_findings.empty:
            st.info(INSUFFICIENT)
        else:
            st.dataframe(audience_findings, hide_index=True, width='stretch')
        st.caption('按当前内容提出兴趣假设，不代表真实粉丝的年龄、性别、购买力或职业。')
    with tabs[2]:
        options = ['互动总量', '点赞', '收藏', '评论'] + [name for name in ['曝光','观看','涨粉','观看曝光比','每千次观看涨粉'] if frame[name].notna().any()]
        if st.session_state.get(f'interaction-v2-{key}',options[0]) not in options:
            st.session_state[f'interaction-v2-{key}']=options[0]
            st.caption('本次缺少此前比较指标，暂改用互动总量。')
        preferred = snapshot.get('preferred_metric', options[0])
        metric = st.selectbox('用哪项数据比较高互动内容', options,
                             index=options.index(preferred) if preferred in options else 0,
                             key=f'interaction-v2-{key}')
        if snapshot.get('is_case_study') and preferred != options[0]:
            st.caption('本案例部分赞藏评显示为缩写数值，未充当精确值统计。默认比较可确认数据较多的指标；可在上方切换。')
        valid, top, comparisons = calculations.get('interactions-v1',[frame,metric],lambda:high_interaction(frame,metric))
        audit = sample_audit(frame, metric)
        st.write(f'本次读取 {len(frame)} 篇；纳入 {len(valid)} 篇；排除 {len(frame)-len(valid)} 篇。只描述纳入样本，不代表全账号规律。')
        with st.expander('查看每篇笔记的纳入/排除原因'):
            show_sources(audit, list(audit.columns))
        st.caption(f'有效样本 {len(valid)} 篇；前25%向上取整为高互动组，共 {len(top)} 篇。同值按读取顺序，至少8篇且指标有差异才比较特征。')
        show_sources(top, ['序号', '标题', '主支柱', metric, '内容特征', '笔记链接'])
        if comparisons.empty:
            st.info(INSUFFICIENT)
        else:
            st.dataframe(comparisons, hide_index=True, width='stretch')
        st.caption('正的占比差表示高互动组中更常见，不代表显著性或因果。标题、正文和封面分别以有效文本/标注为分母，两组各至少2篇；缺失不会记为“没有特征”。')
        if frame[['曝光','观看','涨粉']].notna().any().any():
            st.write('**后台表现比较**')
            st.caption('观看曝光比=同篇观看÷曝光；每千次观看涨粉=同篇涨粉÷观看×1000。按单篇比值平均；仅使用精确值、正分母及一致的统计周期/口径。不是官方点击率或独立用户转化率。未单列周期时沿用来源行的统计范围。')
            for table_name in ['后台支柱表现','内容形式表现','发布时间表现']:
                with st.expander(table_name):
                    if tables[table_name].empty:
                        st.info(INSUFFICIENT)
                    else:
                        st.dataframe(tables[table_name],hide_index=True,width='stretch')
            st.caption('首发日期分组比较的是当前累计表现，不是每日新增。内容形式或首发日期缺失的记录不参与对应分组。')
        with st.expander('查看每篇笔记的特征证据'):
            show_sources(frame, ['序号', '标题', '内容特征', '特征依据', '笔记链接'])
    with tabs[3]:
        packaging=packaging_tables(frame)
        for title,table in packaging.items():
            st.write('**'+title+'**')
            st.dataframe(table,hide_index=True,width='stretch')
        st.caption('主封面类型占比互斥；辅助标签可以重叠，仅统计勾选“辅助标签已复核”的笔记。待标注不等于没有特征。')
        cover_filter=st.selectbox('按封面主类型筛选',['全部',*frame['封面类型'].drop_duplicates().tolist()],key=f'cover-filter-{key}')
        show_sources(frame if cover_filter=='全部' else frame[frame['封面类型'].eq(cover_filter)],
                     ['序号','标题','封面类型','封面辅助标签','辅助标签已复核','封面观察','正文结构（人工）'])
        selected = st.selectbox('选择笔记查看封面与正文', list(range(len(frame))), format_func=lambda i: f"{i+1}. {frame.iloc[i]['标题']}", key=f'sample-v2-{key}')
        item = frame.iloc[selected]
        picture, detail = st.columns([1, 2])
        if item['封面链接']:
            with picture:
                components.html(f'''<!doctype html><html><head><meta name="referrer" content="no-referrer"></head>
                    <body style="margin:0;font:14px sans-serif;color:#64796b"><img src="{escape(item['封面链接'], quote=True)}"
                    referrerpolicy="no-referrer" alt="笔记封面" style="width:100%;height:360px;object-fit:contain"
                    onerror="this.hidden=true;document.getElementById('fallback').hidden=false">
                    <p id="fallback" hidden>封面暂时无法加载，请打开原笔记核对。</p></body></html>''', height=370)
        else:
            picture.info('本次未读取封面，视觉风格需人工查看原笔记。')
        if item['笔记链接']:
            detail.link_button('打开原笔记核对', item['笔记链接'])
        detail.write(f"标题特征：{item['标题特征']}；字数：{item['标题字数']}")
        detail.write(f"正文结构：{item['正文结构']}")
        detail.write(f"人工结构：{item.get('正文结构（人工）','待标注')}；辅助标签：{item.get('封面辅助标签','') or '未填写'}")
        detail.write(f"封面标注：{item['封面类型']}；{item['封面观察'] or '未填写观察'}")
        detail.text(item['正文'] or '未读取正文，暂无法判断正文结构。')
        show_sources(frame, ['标题', '标题特征', '标题字数', '正文段数', '正文结构', '开头摘录', '结尾摘录', '笔记链接'])
        st.caption('包装特征为文本线索，封面视觉类型需人工标注；不自动评价文案质量。')
    with tabs[4]:
        analysis_goals=st.multiselect('本次分析重点（可多选）',ANALYSIS_GOALS,key=f'analysis-goals-{key}')
        selection['analysis_goals']=analysis_goals
        st.write(f"**身份：{identity} · 领域：{'、'.join(domains) or '待确认'} · 目标：{'、'.join(goals) or '尚未确认'}**")
        diagnosis_fields=list(dict.fromkeys(['序号','笔记链接','可见商品入口',*stat_fields]))
        diagnosis_input=frame[[field for field in diagnosis_fields if field in frame]]
        diagnosis = calculations.get('diagnosis-v1',[diagnosis_input,selection,summary],lambda:diagnose(frame,selection,summary))
        def show_diagnosis(observation):
            st.write('**'+observation['诊断主题']+' · '+observation['观察类型']+'**')
            st.write(observation['观察结果'])
            for field in ['样本范围与有效数量','比较指标和计算口径','实际差异','局限或待确认因素']:
                st.caption(field+'：'+str(observation[field]))
            st.write('下一步：'+observation['下一步动作'])
            st.write('复盘：'+observation['验证指标与复盘条件'])
            with st.expander('查看这条诊断的证据筆记'):
                st.write(observation['证据笔记'])
        supported=diagnosis[~diagnosis['观察结果'].eq(INSUFFICIENT)]
        featured=supported.head(3) if not supported.empty else diagnosis.head(1)
        for _,observation in featured.iterrows(): show_diagnosis(observation)
        with st.expander('其余观察与数据缺口'):
            for _,observation in diagnosis.drop(index=featured.index).iterrows(): show_diagnosis(observation)
        if commerce['enabled']:
            st.write('**商品承接线索**')
            st.caption('启用依据：'+commerce['reason'])
            show_sources(frame, ['标题', '商品提及', '商品/系列（人工确认）', '购买引导', '店铺/橱窗', '可见入口数', '承接位置（人工确认）', '笔记链接'])
            st.caption('文字和可见入口不证明实际点击、加购、订单或GMV；未读取入口不代表没有商业化。')
        else:
            show_sources(frame, ['标题', '主支柱', '价值/服务（人工确认）', '承接位置（人工确认）', '笔记链接'])
        diagnosis_note = st.text_area('你的运营诊断补充', key=f'diagnosis-note-v2-{key}')
        st.caption('建议是下一步核对方向，观察结论仅在满足最低数据条件时展示。未识别某种表达不代表账号没有该特点。')
    analysis = {'profile': profile, **selection, 'commerce_enabled':commerce['enabled'], 'commerce_reason':commerce['reason'], 'position': position, 'audience': audience,
                'audience_findings': audience_findings,'audience_auto':audience_auto,'audience_all':audience_all, 'metric': metric, 'valid': valid, 'top': top,
                'comparisons': comparisons, 'summary': summary, 'detail': frame, 'annotations': annotations,
                'diagnosis': diagnosis, 'diagnosis_note': diagnosis_note, 'topics': topics['topics'], 'commerce': commerce['evidence'].to_dict('records'),
                'sample_audit':audit, 'backend_tables':tables, 'final_topics':final_topics, 'editing':editing,'packaging_tables':packaging}
    export_snapshot = dict(snapshot, bio=bio, notes=notes)
    with tabs[5]:
        analysis['ai']=render_ai(export_snapshot,analysis,key)
    save_controls(snapshot,analysis,key)
    from excel_export import public_workbook, export_filename, MIME
    label = '导出公开账号数据与分析（Excel）' if snapshot.get('source_kind', '公开账号') == '公开账号' else '导出V3数据与分析（Excel）'
    try:
        excel_data,markdown_data=report_bytes(session_cache('exports'),export_snapshot,analysis,markdown_report)
    except Exception:
        st.error('报告生成失败，未提供旧版下载。可以重试；如持续失败，请缩小样本并检查原始字段。')
        if st.button('重试生成报告',key=f'retry-report-{key}'): st.rerun()
        return analysis
    st.download_button(label, excel_data,
                       file_name=export_filename('V3账号分析', snapshot['name'], snapshot['captured_at']), mime=MIME, key=f'v2-excel-{key}')
    st.caption('导出包含账号初判与人工选择、动态支柱、特征证据、运营诊断和笔记明细。修改后请重新下载，文件为当前结果快照。')
    st.download_button('下载分析报告（Markdown）', markdown_data, file_name='账号运营分析V3.md', mime='text/markdown', key=f'v2-report-{key}')
    with st.expander('计算与报告缓存状态'):
        st.dataframe(pd.DataFrame([dict(缓存='分析',**calculations.info()),dict(缓存='导出',**session_cache('exports').info())]),hide_index=True,width='stretch')
    return analysis
