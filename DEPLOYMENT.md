# V3 公开部署版本

本版本在原版功能基础上增加云端适配。默认是公开演示模式，入口为 `app.py`，建议使用 Python 3.12。

## 在线可体验

- Excel 多工作表与表头识别、字段映射、数字精度处理、缺失值与零值区分。
- 指标概览、排行榜、主题分组、可视化、曝光/观看/涨粉等后台指标。
- 账号画像、内容结构、高互动规律、内容包装、运营诊断与人工修订。
- 四类模拟账号，一键加载；每类18篇模拟笔记，页面和导出均标注数据性质。
- AI助手规则演示：生成、编辑、采纳、固定规则问答、报告附录；不调用付费API，不代表大模型实际效果。
- Excel、Markdown报告与可恢复的JSON项目存档。

## 公共部署安全策略

- 默认 `APP_MODE=public`；未知配置值也按公开模式处理。
- 公开模式在服务端跳过密钥加载和外部AI调用，即使存在 `OPENAI_API_KEY` 也不会调用付费服务。
- 各访客项目及分析缓存保存在各自会话内，不读取或写入共享的 `.local/analysis-projects`。
- 不创建共享小红书登录浏览器，也不在公开服务器接收密码或登录Cookie。
- 上传上限10MB、解压内容40MB、工作簿归档条目500个、单次分析1000行。单会话最多保存5个项目。
- 报告中的文本以字符串写入Excel，保留原有公式注入防护。
- `.gitignore` 排除密钥、环境配置、私钥、浏览器资料、存档和测试产物。不要把真实运营数据放进仓库。

会话存储不是持久数据库；断线、刷新、休眠、重启后可能丢失。访客应下载存档自行保管。上传的数据及报告可能包含访客自己的隐私，下载前应自行核对。

## Streamlit Community Cloud 配置

- Repository：此项目所在GitHub仓库。
- Branch：`main`。
- Main file path：`app.py`。
- Python：`3.12`。
- Secrets：公开演示不需要任何密钥。不要设置 `APP_MODE="local"`。
- 访问权限：公开。

依赖由根目录 `requirements.txt` 安装；无需安装Chromium或Linux桌面。
Community Cloud适合展示，但不能保证永久在线或可用性SLA；平台限制、休眠和规则以官方文档为准。

官方说明：[部署](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)、[依赖](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)、[状态与限制](https://docs.streamlit.io/deploy/streamlit-community-cloud/status)。

## 保留的本地功能

`start.cmd` 显式设置 `APP_MODE=local` 并只绑定本机地址；原版小红书公开主页读取、后台同步、本地持久存档和真实AI调用保持可用。实际账号读取仍依赖平台登录、网络及页面结构。

需要命令行启动本地完整模式时：

```powershell
$env:APP_MODE = 'local'
python -m streamlit run app.py --server.address=127.0.0.1
```

真实AI密钥只放在环境变量或未提交的 `.streamlit/secrets.toml`，模板见 `.streamlit/secrets.toml.example`。本地付费模式不是公开服务，不要把该模式开放到公网。无需为作品集演示购买API额度。

## 自动化测试

Windows PowerShell：

```powershell
$env:APP_MODE = 'local'
python -m unittest discover -s tests -v
$env:APP_MODE = 'public'
python -m unittest discover -s cloud_tests -v
```

GitHub Actions在Linux与Python 3.12上运行相同检查。测试中的SDK调用使用模拟传输，不产生付费请求。真实公开网址验证与本地测试是不同验收项，不能相互替代。

## 免费语义主题归纳

- `smart_topics.py` 为统一入口。固定案例通过来源链接与文字指纹核对后采用 `reviewed_topics.json` 的逐篇复核标签；改变源文字便不会继续声称已复核。
- 新材料采用 `Xenova/paraphrase-multilingual-MiniLM-L12-v2` 的量化 ONNX 文件，在 CPU 上计算文本语义向量，再匹配 `topic_catalog.py` 的领域描述。明确关键词用于辅助弱匹配；不确定的笔记保留“其他/待确认”。这不是生成式大模型，也不保证任意领域的分类质量。
- 首次需要从 Hugging Face 下载约 136 MB 公共模型文件，固定提交版本并校验 SHA-256；缓存到系统临时目录，不进入 Git。仅下载权重，不发送访客文本；推理批量 8 条、CPU 两线程、文本最多 128 tokens。正文过长会截断，因此仍需复核。
- 模型资源可跨会话复用，访客分析结果仍按会话隔离。下载或推理失败会明确显示文本归纳回退，不调用付费 API。新开会话可重试。无网络环境可设置 `TOPIC_ENGINE=rules`，不会尝试加载语义模型。
- 自动化回归使用 `TOPIC_ENGINE=rules` 避免联网依赖，并单独测试语义分支和故障回退。真实模型集成测试：`python -m unittest discover -s integration_tests -v`；首次需可访问模型下载站点。
- 更改代码会继续使用当前地址 https://ai-operations-workbench.streamlit.app/ 。只有在云端主动改名、删除或迁移应用时才需要更换链接。
