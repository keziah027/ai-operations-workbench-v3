"""Interactive landing cover using the Editorial Paper & Forest Ink theme."""
from base64 import b64encode
from pathlib import Path
import streamlit as st


@st.cache_data
def dashboard_panel():
    path = Path(__file__).with_name('assets').joinpath('cover-dashboard-panel-v1.png')
    return b64encode(path.read_bytes()).decode() if path.exists() else ''


def enter_workspace():
    st.session_state['cover-open'] = False
    st.session_state['source-picker-open'] = True
    st.session_state['show_saved_project'] = False


def open_cover():
    st.session_state['cover-open'] = True


@st.dialog('功能')
def show_features():
    st.write('导入 Excel 或选择真实案例，查看数据概览、内容分析、趋势分析与运营建议。')
    st.write('本地模式还可登录并读取公开账号或同步自己的账号后台。')
    if st.button('选择数据来源', key='cover-feature-start'):
        enter_workspace()
        st.rerun()


@st.dialog('关于')
def show_about():
    st.write('AI运营分析台')
    st.write('从已有数据出发，整理内容表现、发现趋势并辅助运营决策。')


COVER_LEDGER_HTML = '''
<div class="cover-ledger" aria-hidden="true">
  <div class="cover-ledger-head">
    <span>样本数据预览</span>
    <span>小Lin说</span>
  </div>
  <div class="cover-ledger-kpis">
    <div class="cover-ledger-kpi"><span>样本篇数</span><strong>18 篇</strong></div>
    <div class="cover-ledger-kpi"><span>总点赞</span><strong>49,089</strong></div>
    <div class="cover-ledger-kpi"><span>平均点赞</span><strong>6,136.1</strong></div>
    <div class="cover-ledger-kpi"><span>平均藏赞比</span><strong>24.9%</strong></div>
  </div>
  <div class="cover-ledger-body">
    <div class="cover-ledger-chart">
      <h4>数据趋势</h4>
      <svg viewBox="0 0 360 130" style="width:100%;height:125px;overflow:visible">
        <defs>
          <linearGradient id="edGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#1B4D3E" stop-opacity="0.18"/>
            <stop offset="100%" stop-color="#1B4D3E" stop-opacity="0.0"/>
          </linearGradient>
        </defs>
        <line x1="36" y1="14" x2="348" y2="14" stroke="#DFDCD2" stroke-dasharray="3 3"/>
        <line x1="36" y1="60" x2="348" y2="60" stroke="#DFDCD2" stroke-dasharray="3 3"/>
        <line x1="36" y1="106" x2="348" y2="106" stroke="#DFDCD2" stroke-dasharray="3 3"/>
        <text x="30" y="18" text-anchor="end" fill="#4A4945" font-size="11">10k</text>
        <text x="30" y="64" text-anchor="end" fill="#4A4945" font-size="11">5k</text>
        <text x="30" y="110" text-anchor="end" fill="#4A4945" font-size="11">0</text>
        <path d="M36,38 L80,63 L125,18 L170,46 L215,63 L260,66 L304,58 L348,32 L348,106 L36,106 Z" fill="url(#edGrad)"/>
        <path d="M36,38 L80,63 L125,18 L170,46 L215,63 L260,66 L304,58 L348,32" fill="none" stroke="#1B4D3E" stroke-width="2.2"/>
        <circle cx="36" cy="38" r="3.2" fill="#FDFCFA" stroke="#1B4D3E" stroke-width="2"/>
        <circle cx="125" cy="18" r="3.2" fill="#FDFCFA" stroke="#1B4D3E" stroke-width="2"/>
        <circle cx="215" cy="63" r="3.2" fill="#FDFCFA" stroke="#1B4D3E" stroke-width="2"/>
        <circle cx="348" cy="32" r="3.2" fill="#FDFCFA" stroke="#1B4D3E" stroke-width="2"/>
        <text x="36" y="124" text-anchor="middle" fill="#4A4945" font-size="11">08-28</text>
        <text x="125" y="124" text-anchor="middle" fill="#4A4945" font-size="11">09-15</text>
        <text x="215" y="124" text-anchor="middle" fill="#4A4945" font-size="11">09-26</text>
        <text x="348" y="124" text-anchor="middle" fill="#4A4945" font-size="11">10-10</text>
      </svg>
    </div>
    <div class="cover-ledger-pillars">
      <h4>内容主题分布</h4>
      <div class="cover-pillar-item">
        <div class="cover-pillar-row"><span>企业经营与资本运作</span><strong>33%</strong></div>
        <div class="cover-pillar-track"><div class="cover-pillar-fill" style="width:33.3%;background:#1B4D3E"></div></div>
      </div>
      <div class="cover-pillar-item">
        <div class="cover-pillar-row"><span>宏观经济与国际财经</span><strong>22%</strong></div>
        <div class="cover-pillar-track"><div class="cover-pillar-fill" style="width:22.2%;background:#B84A32"></div></div>
      </div>
      <div class="cover-pillar-item">
        <div class="cover-pillar-row"><span>科技产业与消费电子</span><strong>17%</strong></div>
        <div class="cover-pillar-track"><div class="cover-pillar-fill" style="width:16.7%;background:#3B6E8C"></div></div>
      </div>
      <div class="cover-pillar-item">
        <div class="cover-pillar-row"><span>商业机制与财富话题</span><strong>17%</strong></div>
        <div class="cover-pillar-track"><div class="cover-pillar-fill" style="width:16.7%;background:#7A6A4F"></div></div>
      </div>
    </div>
  </div>
</div>
'''


def render_cover():
    with st.container(key='cover'):
        with st.container(key='cover-nav'):
            brand, home, features, analysis, about, action = st.columns([3.3, .8, .8, 1.2, .8, 1.8], vertical_alignment='center')
            with brand:
                st.html('<div class="cover-brand"><span class="cover-logo" aria-hidden="true">A</span><strong>AI运营分析台</strong></div>')
            home.button('首页', key='cover-home', on_click=open_cover, width='stretch')
            if features.button('功能', key='cover-features', width='stretch'):
                show_features()
            analysis.button('数据分析', key='cover-analysis', on_click=enter_workspace, width='stretch')
            if about.button('关于', key='cover-about', width='stretch'):
                show_about()
            action.button('开始体验 →', key='cover-top-start', on_click=enter_workspace, width='stretch')
        with st.container(key='cover-copy'):
            st.html('<h1 class="cover-title"><span>AI</span>运营分析台</h1>')
            st.button('开始体验 →', key='cover-start', on_click=enter_workspace)
        with st.container(key='cover-art'):
            st.html(COVER_LEDGER_HTML)
