"""Compact dashboard views. Calculations use the existing cleaned records."""
from html import escape
from base64 import b64encode

import altair as alt
import pandas as pd
import streamlit as st
from analysis import METRICS, GROUP_COLUMNS, TYPE_COLUMNS, summarize
from note_schema import publication_dates, normalize_notes, THEME_FIELDS, content_text
from performance import scope_matches
from metric_display import metric_text as public_metric_text, display_values, display_total, display_ranking, has_abbreviations, NOTICE as DISPLAY_NOTICE

PALETTE = ['#1B4D3E', '#B84A32', '#3B6E8C', '#7A6A4F', '#5C7A67', '#8C9289']
NAV = [('overview', '数据概览', 'grid'), ('deep-analysis', '内容分析', 'layers'),
       ('data-trend', '趋势分析', 'chart'), ('content-distribution', '内容分类', 'pie'),
       ('detail-analysis', '单篇详情', 'file'), ('operations-advice', '运营建议', 'spark'),
       ('data-upload', '数据上传', 'upload'), ('user-guide', '使用说明', 'help')]
ICON_PATHS = {
    'grid': '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    'layers': '<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
    'chart': '<path d="M3 3v18h18M6 15l4-5 4 3 6-8"/>',
    'pie': '<path d="M12 3v9h9A9 9 0 0 0 12 3Z"/><path d="M8 4a9 9 0 1 0 12 12H8Z"/>',
    'file': '<rect x="5" y="3" width="14" height="18" rx="3"/><path d="M9 8h6M9 12h6M9 16h4"/>',
    'spark': '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/>',
    'upload': '<path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5"/>',
    'help': '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 4 2l-1.5 1.5M12 16h.01"/>',
}


def icon(name):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#1B4D3E" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' + ICON_PATHS[name] + '</svg>'
    return '<img class="nav-icon" alt="" src="data:image/svg+xml;base64,' + b64encode(svg.encode()).decode() + '">'


def anchor(name):
    st.html(f'<div id="{name}" class="section-anchor"></div>')


def start_upload():
    st.session_state['source-picker-open'] = False
    st.session_state['data-source'] = 'Excel 文件'
    st.session_state['show_saved_project'] = False
    st.session_state['open-upload'] = True


def render_hero():
    has_data = bool(st.session_state.get('excel-upload') or st.session_state.get('demo_scenario')
                    or st.session_state.get('public_snapshot') or st.session_state.get('active_project'))
    with st.container(key='glass-hero'):
        st.html('<div class="hero-copy"><h1>AI运营分析台</h1></div>')
        st.button('上传 Excel 开始分析' if has_data else '开始体验', icon=':material/upload_file:',
                  type='primary', key='hero-upload', on_click=start_upload)


def render_sidebar(sources):
    from source_picker import select_source, open_source_picker
    with st.sidebar:
        st.html('<div class="sidebar-brand"><div class="brand-mark">A</div><strong>AI运营分析台</strong></div>')
        if not st.session_state.get('source-picker-open', True) or st.session_state.get('show_saved_project'):
            st.button('返回数据来源', icon=':material/arrow_back:', key='source-back', on_click=open_source_picker)
        with st.expander('数据来源'):
            mode = st.radio('数据来源', sources, key='data-source', width='stretch', label_visibility='collapsed', on_change=select_source)
        if mode == 'Excel 文件' and not st.session_state.get('show_saved_project'):
            links = ''.join(f'<a class="nav-{name}" href="#{name}" target="_self">{icon(symbol)}<span>{title}</span></a>' for name, title, symbol in NAV)
            st.html('<nav class="workspace-nav" aria-label="分析导航">' + links + '</nav>')
        from project_ui import project_picker
        project_picker()
        with st.expander('使用说明'):
            st.write('上传 Excel 或加载演示数据，查看看板后可继续做内容分析、人工标注及报告导出。')
            st.caption('缺失与近似数值不参与精确统计。')
    return mode


def render_empty():
    # A quiet entry state, without example metrics or promotional feature cards.
    st.html('<div class="empty-state compact-empty">暂无分析数据</div>')
    for name, _, _ in NAV:
        if name not in ('data-upload', 'user-guide'):
            anchor(name)


def chart_theme(chart):
    return chart.configure(background='transparent').configure_view(strokeOpacity=0).configure_axis(
        labelColor='#4A4945', titleColor='#161615', gridColor='#DFDCD2', domain=False,
        tickSize=0, labelPadding=8, title=None, labelFont='Microsoft YaHei', labelFontSize=12,
    ).configure_legend(labelColor='#555b7b', title=None)


def efficiency_data(frame):
    """Mean of per-note rates; never substitute likes or mix reporting scopes."""
    result = pd.DataFrame(index=frame.index)
    for field in ['点赞', '收藏', '评论']:
        name = field + '率'
        result[name] = float('nan')
        if '观看' not in frame or field not in frame:
            continue
        denominator = pd.to_numeric(frame['观看'], errors='coerce')
        numerator = pd.to_numeric(frame[field], errors='coerce')
        valid = denominator.gt(0) & numerator.ge(0) & scope_matches(frame, field, '观看')
        for column in [field, '观看']:
            if column + '精度' in frame:
                valid &= frame[column + '精度'].eq('精确')
        result[name] = numerator.div(denominator).where(valid)
    return result


def category_field(frame):
    return next((c for c in ['内容支柱', *GROUP_COLUMNS] if c in frame), None)


def dashboard_topics(frame, snapshot=None):
    """Use the same reviewed themes and final manual memberships as the report."""
    from content_ui_v2 import cached_topics, analysis_key
    notes = normalize_notes(snapshot['notes'] if snapshot else frame.to_dict('records'))
    text_notes = [{field: note.get(field, '') for field in ['标题', '正文', '内容概述（整理）', '笔记链接', *THEME_FIELDS]} for note in notes]
    topics = cached_topics(text_notes, snapshot.get('id') if snapshot and snapshot.get('is_case_study') else None)
    labels = topics['assignments']
    if snapshot:
        state = st.session_state.get('editor-state-' + analysis_key(snapshot), {})
        rows = state.get('annotations', [])
        if len(rows) == len(frame):
            labels = [row['主支柱'] for row in rows]
    result = frame.copy()
    result['内容支柱'] = labels
    return result


def content_formats(frame):
    """Normalize explicit media labels only; never infer format from the title."""
    aliases = {'图文': '图文', '图片': '图文', '图文笔记': '图文', '图片笔记': '图文',
               'image': '图文', 'images': '图文', 'normal': '图文',
               '视频': '视频', '视频笔记': '视频', '短视频': '视频', 'video': '视频'}
    fields = ['图文/视频', '内容形式', '笔记类型', '内容类型', 'type']
    return frame.apply(lambda row: next((aliases[value] for field in fields
        if (value := content_text(row.get(field)).lower()) in aliases), ''), axis=1)


def interaction_ratios(frame):
    result = pd.DataFrame(index=frame.index)
    for field, label in [('收藏', '藏赞比'), ('评论', '评赞比')]:
        denominator = pd.to_numeric(frame.get('点赞', pd.Series(index=frame.index, dtype=float)), errors='coerce')
        numerator = pd.to_numeric(frame.get(field, pd.Series(index=frame.index, dtype=float)), errors='coerce')
        valid = denominator.gt(0) & numerator.ge(0) & scope_matches(frame, field, '点赞')
        for column in [field, '点赞']:
            if column + '精度' in frame:
                valid &= frame[column + '精度'].eq('精确')
        result[label] = numerator.div(denominator).where(valid)
    return result


def trend_date_field(frame):
    for field in ['发布时间', '页面日期']:
        if field in frame and publication_dates(frame[field]).notna().any():
            return field
    return None


def trend_data(frame, metric, by_date=True):
    data = frame.copy()
    data[metric] = pd.to_numeric(data[metric], errors='coerce')
    if metric + '精度' in data:
        data[metric] = data[metric].where(data[metric + '精度'].eq('精确'))
    data['样本序号'] = range(1, len(data) + 1)
    field = trend_date_field(frame)
    data['发布日期'] = publication_dates(data[field] if field else pd.Series(index=data.index, dtype=object)).dt.normalize()
    if by_date:
        valid = data.dropna(subset=['发布日期', metric])
        result = valid.groupby('发布日期', as_index=False)[metric].mean()
        if field == '页面日期' and '页面日期性质' in valid:
            kinds = valid.groupby('发布日期')['页面日期性质'].agg(lambda values: '、'.join(sorted(set(values.dropna().astype(str)))))
            result['日期性质'] = result['发布日期'].map(kinds)
        return result
    return data.dropna(subset=[metric])[['样本序号', '标题', metric]]


def observations(frame, rates):
    """Short reproducible observations, without attributing causes to correlations."""
    items = []
    field = category_field(frame)
    likes = pd.to_numeric(frame['点赞'], errors='coerce')
    if field:
        groups = frame.assign(_likes=likes).groupby(field, dropna=False)['_likes'].agg(['mean', 'count'])
        eligible = groups[groups['count'].ge(2)].sort_values('mean', ascending=False, kind='stable')
        if not eligible.empty and pd.notna(eligible.iloc[0]['mean']):
            label = str(eligible.index[0])
            if label not in ('未分类', 'nan', '<NA>', ''):
                items.append(f'「{label[:24]}」平均点赞最高，为 {eligible.iloc[0]["mean"]:,.0f}；可优先复盘这类内容。')
    if not items and likes.notna().any():
        note = frame.loc[likes.idxmax()]
        items.append(f'「{str(note["标题"])[:28]}」获得 {likes.max():,.0f} 次点赞，可作为内容复盘的起点。')
    save = rates['收藏率'].dropna()
    if len(save) >= 2 and save.max() > save.mean():
        title = str(frame.loc[save.idxmax(), '标题'])[:24]
        items.append(f'「{title}」收藏率 {save.max():.1%}，高于样本均值 {save.mean():.1%}；可参考其选题。')
    comments = pd.to_numeric(frame['评论'], errors='coerce')
    if comments.notna().any() and comments.max() > 0:
        title = str(frame.loc[comments.idxmax(), '标题'])[:24]
        scope = '在精确评论样本中，' if has_abbreviations(frame, '评论') else ''
        items.append(f'{scope}「{title}」评论最多，共 {comments.max():,.0f} 条；可复盘这篇内容的互动方式。')
    return items[:3]


def distribution(frame, field, *, small=False):
    labels = frame[field].fillna('未分类').astype(str).str.strip().replace('', '未分类') if field else pd.Series('未分类', index=frame.index)
    counts = labels.value_counts().rename_axis('分类').reset_index(name='篇数')
    counts['占比'] = counts['篇数'] / max(len(frame), 1)
    counts['颜色'] = [PALETTE[i % len(PALETTE)] for i in range(len(counts))]
    plot, legend = st.columns([1, 1.05], gap='small')
    with plot:
        ring = alt.Chart(counts).mark_arc(innerRadius=alt.ExprRef(expr='(min(width, height) / 2 - 6) * 0.72'), outerRadius=alt.ExprRef(expr='min(width, height) / 2 - 6'),
                                        cornerRadius=2, stroke='#ffffff', strokeWidth=1.8).encode(
            theta='篇数:Q', color=alt.Color('分类:N', scale=alt.Scale(domain=counts['分类'].tolist(), range=counts['颜色'].tolist()), legend=None),
            tooltip=['分类:N', '篇数:Q', alt.Tooltip('占比:Q', format='.1%')])
        center = alt.Chart(pd.DataFrame({'label':[str(len(frame))]})).mark_text(fontSize=19 if small else 26, color='#161615', fontWeight=600, dy=-5).encode(text='label:N')
        unit = alt.Chart(pd.DataFrame({'label':['篇']})).mark_text(fontSize=10, color='#4A4945', dy=17).encode(text='label:N')
        st.altair_chart(chart_theme((ring + center + unit).properties(height=155 if small else 200)), width='stretch', theme=None)
    with legend:
        rows = ''.join(f'<div class="legend-row"><i style="background:{row["颜色"]}"></i><span title="{escape(row["分类"])}">{escape(row["分类"])}</span><b>{row["占比"]:.0%}</b></div>' for row in counts.to_dict('records'))
        st.html('<div class="distribution-legend'+ (' small-legend' if small else '') +'">'+rows+'</div>')


def overview_metric(frame, preferred=None):
    """Prefer the snapshot's comparison metric when exact likes are unavailable."""
    if display_values(frame, '点赞').notna().any():
        return '点赞'
    for metric in dict.fromkeys([preferred, '评论', '收藏', '点赞']):
        if metric in METRICS and frame[metric].notna().any():
            return metric
    return '点赞'


def render_trend(frame, default_metric='点赞'):
    date_field = trend_date_field(frame)
    st.subheader('数据趋势')
    controls, order_col = st.columns([1.5, 1], gap='small')
    with controls:
        metric = st.segmented_control('趋势指标', METRICS, default=default_metric, key='overview-metric', label_visibility='collapsed') or default_metric
    with order_col:
        prefix = '页面日期' if date_field == '页面日期' else '发布时间'
        options = [prefix + '升序', prefix + '降序']
        order = st.selectbox('时间排序', options, key='trend-order', label_visibility='collapsed')
    approximate = has_abbreviations(frame, metric)
    display_frame = frame.copy()
    if approximate:
        display_frame[metric] = display_values(frame, metric)
        display_frame[metric+'精度'] = '精确'  # Only the isolated chart input; source analysis is unchanged.
        st.write(DISPLAY_NOTICE)
    trend = trend_data(display_frame, metric)
    if trend.empty:
        st.info('请补充有效日期后查看趋势。' if date_field is None else f'暂无同时具备日期与精确{metric}的数据。')
        return
    if date_field == '页面日期':
        st.caption('按页面日期统计，含已标注的编辑日期。')
    reverse = order.endswith('降序')
    axis_format = '%Y-%m-%d' if trend['发布日期'].dt.year.nunique() > 1 else '%m-%d'
    axis = alt.X('发布日期:T', title=prefix, axis=alt.Axis(format=axis_format, tickCount=6), scale=alt.Scale(reverse=reverse))
    tips = [alt.Tooltip('发布日期:T', title=prefix, format='%Y-%m-%d')]
    if '日期性质' in trend:
        tips.append(alt.Tooltip('日期性质:N'))
    base = alt.Chart(trend).encode(
        x=axis,
        y=alt.Y(f'{metric}:Q', title=metric+'（页面折算）' if approximate else metric, scale=alt.Scale(zero=True)),
        tooltip=[*tips, alt.Tooltip(f'{metric}:Q', title=f'平均{metric}'+('（页面折算）' if approximate else ''), format=',.1f')])
    area = base.mark_area(color=alt.Gradient(gradient='linear', stops=[alt.GradientStop(color='#1B4D3E33', offset=0), alt.GradientStop(color='#1B4D3E00', offset=1)], x1=0, x2=0, y1=0, y2=1))
    line = base.mark_line(color='#1B4D3E', strokeWidth=2.2, point=alt.OverlayMarkDef(size=24, filled=True, fill='#FDFCFA', stroke='#1B4D3E'))
    st.altair_chart(chart_theme((area + line).properties(height=205)), width='stretch', theme=None)


def render_ranking(frame, metric='点赞'):
    st.subheader('高互动内容 TOP5')
    ranked = display_ranking(frame, metric, 5)
    if ranked.empty:
        st.info(f'暂无精确{metric}数据')
        return
    if metric != '点赞':
        st.write(f'按已确认{metric}数排序（{frame[metric].count()}/{len(frame)}篇）')
    if has_abbreviations(frame, metric):
        st.write('按页面显示值分组；“10万+”之间不区分高低。')
    rows = ''
    for i, (_, note) in enumerate(ranked.iterrows(), 1):
        values = [escape(public_metric_text(note, m)) for m in METRICS]
        i = int(note['_显示分组'])
        title = escape(str(note['标题']))
        rows += f'<tr><td><span class="rank rank-{i}">{i:02}</span></td><td title="{title}">{title}</td>' + ''.join(f'<td>{v}</td>' for v in values) + '</tr>'
    st.html('<div class="ranking-wrap"><table class="ranking-table"><thead><tr><th>#</th><th>标题</th><th>点赞</th><th>收藏</th><th>评论</th></tr></thead><tbody>' + rows + '</tbody></table></div>')


def render_efficiency(frame, rates):
    st.subheader('互动效率')
    choices = ['点赞率与收藏率', '收藏率与评论率', '藏赞比与评赞比'] if rates.notna().any().any() else ['藏赞比与评赞比']
    mode = st.selectbox('效率指标', choices, key='efficiency-mode', label_visibility='collapsed')
    ratio_mode = mode == '藏赞比与评赞比'
    if ratio_mode:
        rates = interaction_ratios(frame)
        fields = ['藏赞比', '评赞比']
        st.caption('收藏 / 点赞 · 评论 / 点赞')
        if len(choices) == 1:
            st.caption('缺少有效观看量，暂不能计算点赞率、收藏率。')
    else:
        fields = ['点赞率', '收藏率'] if mode == '点赞率与收藏率' else ['收藏率', '评论率']
    cols = st.columns(2, gap='small')
    for col, field, color in zip(cols, fields, ['#1B4D3E', '#B84A32']):
        with col, st.container(key='rate-'+field):
            values = rates[field]
            st.metric('平均'+field, '—' if values.notna().sum() == 0 else f'{values.mean():.1%}')
            if '发布时间' in frame:
                daily = pd.DataFrame({'日期':publication_dates(frame['发布时间']).dt.normalize(), '比率':values}).dropna().groupby('日期',as_index=False)['比率'].mean()
                if not daily.empty:
                    spark = alt.Chart(daily).mark_line(color=color,strokeWidth=1.8,point=len(daily)==1).encode(
                        x=alt.X('日期:T',axis=None),y=alt.Y('比率:Q',axis=None,scale=alt.Scale(zero=True)),
                        tooltip=[alt.Tooltip('日期:T',format='%Y-%m-%d'),alt.Tooltip('比率:Q',title=field,format='.1%')])
                    st.altair_chart(chart_theme(spark.properties(height=40)),width='stretch',theme=None)


def render_formats(frame):
    st.subheader('内容形式分布')
    formats = content_formats(frame)
    import hashlib
    key = hashlib.sha256(frame.to_json(force_ascii=False).encode()).hexdigest()[:16]
    with st.expander('补充内容形式'):
        st.caption('仅按已确认的形式填写；当前会话生效，可下载后保留。')
        with st.form('formats-' + key):
            original = pd.DataFrame({'标题': frame['标题'].tolist(), '内容形式': formats.replace('', '待确认').tolist()})
            baseline = st.session_state.get('formats-saved-' + key, original)
            edited = st.data_editor(baseline, hide_index=True, width='stretch', disabled=['标题'],
                column_config={'内容形式': st.column_config.SelectboxColumn(options=['图文', '视频', '待确认'], required=True)}, key='formats-editor-' + key)
            if st.form_submit_button('应用内容形式'):
                st.session_state['formats-saved-' + key] = edited
        saved = st.session_state.get('formats-saved-' + key)
        if saved is not None:
            formats = pd.Series(saved['内容形式'].replace('待确认', '').tolist(), index=frame.index)
            export = frame.copy()
            export['图文/视频'] = formats
            export['内容形式'] = formats
            from io import BytesIO
            output = BytesIO()
            export.to_excel(output, index=False)
            st.download_button('下载已补充的数据', output.getvalue(), '内容形式已补充.xlsx', key='formats-download-' + key)
    known = frame.assign(内容形式= formats).loc[formats.ne('')]
    if known.empty:
        st.info('缺少内容形式，请补充图文 / 视频。')
    else:
        distribution(known, '内容形式', small=True)
    missing = len(frame) - len(known)
    if missing and not known.empty:
        st.caption(f'已确认 {len(known)} 篇 · 待确认 {missing} 篇；占比按已确认篇数计算。')


def render_overview(frame, snapshot=None):
    frame = dashboard_topics(frame, snapshot)
    default_metric = overview_metric(frame, (snapshot or {}).get('preferred_metric'))
    metric_source = (snapshot or {}).get('id') or frame.to_json(force_ascii=False)
    if st.session_state.get('overview-metric-source') != metric_source:
        st.session_state['overview-metric-source'] = metric_source
        if 'overview-metric' in st.session_state:
            st.session_state['overview-metric'] = default_metric
    anchor('overview')
    totals = summarize(frame)
    with st.container(key='overview-kpis'):
        for col, label in zip(st.columns(5), ['总发布篇数', '总点赞', '总收藏', '总评论', '平均点赞']):
            value = totals[label]
            text = '—' if pd.isna(value) else (f'{value:,.1f}' if label == '平均点赞' else f'{value:,.0f}')
            field = label[1:] if label in ('总点赞','总收藏','总评论') else '点赞'
            help_text = None if label == '总发布篇数' else f'使用精确{field}的 {frame[field].count()}/{len(frame)} 篇；缺失与近似值不计入。'
            if label != '总发布篇数' and has_abbreviations(frame, field):
                text = display_total(frame, field, mean=label=='平均点赞')
                label += '（页面折算）'
                help_text = DISPLAY_NOTICE + f' 有显示值 {display_values(frame, field).count()}/{len(frame)} 篇；缺失值不计入。'
            col.metric(label, text, help=help_text)
    left, right = st.columns([1.55, 1], gap='medium')
    with left, st.container(key='overview-trend', border=True):
        anchor('data-trend')
        render_trend(frame, default_metric)
    with right, st.container(key='overview-distribution', border=True):
        anchor('content-distribution')
        st.subheader('内容主题分布')
        distribution(frame, '内容支柱')
    left, right = st.columns([1.05, 1.5], gap='medium')
    rates = efficiency_data(frame)
    with left, st.container(key='overview-top', border=True):
        render_ranking(frame, default_metric)
    with right:
        efficiency_col, format_col = st.columns([1.15, 1], gap='medium')
        with efficiency_col, st.container(key='overview-efficiency', border=True):
            render_efficiency(frame, rates)
        with format_col, st.container(key='overview-format', border=True):
            render_formats(frame)
        with st.container(key='overview-advice', border=True):
            anchor('operations-advice')
            st.subheader('运营建议')
            advice = observations(frame, rates)
            if not advice:
                st.info('暂无足够数据生成建议')
            else:
                st.html('<ol class="advice-list">' + ''.join(f'<li>{escape(item)}</li>' for item in advice) + '</ol>')
            st.html('<a class="advice-more" href="#deep-analysis" target="_self">查看完整分析 →</a>')


def render_guide():
    anchor('user-guide')
    with st.expander('使用说明与指标口径'):
        st.write('上传 Excel 后查看看板；点击“内容分析”可继续复核分类、生成分析、保存项目和导出报告。')
        st.write('趋势横轴使用日期，优先采用发布时间；案例使用页面显示日期时，注明编辑日期。无有效日期的记录不进入时间趋势。点赞率、收藏率、评论率以同篇观看量为分母；藏赞比、评赞比以点赞量为分母，分别取有效篇均值。缺失与近似值不参与精确统计。')
