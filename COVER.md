# 首页封面

根据用户提供的封面参考图，在原 Streamlit 应用前增加可交互首页。顶部提供首页、功能、数据分析、关于及开始体验；主区域展示大标题和开始体验按钮，使用与数据来源页一致的柔和蓝紫渐变背景，右侧叠加独立透明玻璃看板面板，无底座或环绕光带。开始体验和数据分析进入现有四种数据来源选择页。功能与关于展示简短弹窗。

新增文件：`cover_ui.py`、`cover.css`、`assets/cover-glass-v1.png`；`app.py` 增加首页状态分支，原有分析函数与计算规则不变。来源选择页继续保持无侧栏设计，分析页保留原导航。

根据最新反馈，首页已停止加载玻璃看板背景图，直接沿用全站渐变背景。原图 `assets/cover-glass-v1.png` 仅作为历史素材保留。主标题、导航、按钮仍为真实网页控件。数据来源标题采用轻量引导文字与紫蓝渐变重点文字；全站灰色辅助说明小字及其占位间距不再显示，表单、分析、状态提醒和报告功能保持原样。

运行方式不变：解压完整项目，运行 `start.cmd`。刷新打开首页，点击开始体验进入原流程。

## 历史封面素材提示词（当前页面已停用该图）

Use case: precise-object-edit. Asset type: 16:9 website hero background for AI运营分析台. Input image is the edit target and exact visual reference. Preserve the luminous pale periwinkle-blue, lavender, blush-white glass world, iridescent swooping ribbon rings, reflective floor, right-hand floating frosted-glass analytics dashboard on a crystal pedestal. Preserve the composition closely: the dashboard entirely in the rightmost 57%, ample clear luminous negative space in leftmost 40%. Remove the entire top navigation strip including logo, all navigation words and top button, fill that area with the luminous background seamlessly. Remove the huge left headline AI运营分析台 and left CTA button completely; leave that region clear for live HTML text and buttons. On the dashboard retain tasteful purple line-chart and donut-chart shapes and simple icons, but replace ALL numerical data, percentages, dates and axes numbers with subtle short horizontal placeholder strokes, no fabricated quantitative claims. Retain only small crisp Chinese labels 数据概览, 内容分析, 趋势分析 if useful. No other text, no tagline, no watermarks. Premium polished realistic 3D glass render, delicate refractions, restrained luminous highlights, reference-quality composition, not flat generic vector art. Output landscape 16:9 at high resolution.

## 独立看板

按最新反馈，右侧加入 `assets/cover-dashboard-panel-v1.png` 透明面板，桌面端左右排列，手机端位于标题和按钮下方。原渐变背景保持不变。素材及内置 imagegen 提示词见 `assets/cover-dashboard-panel-v1.md`。
