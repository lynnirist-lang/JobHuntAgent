# 求职助手 — Job Hunt Agent

> 自动化处理 BOSS 直聘全流程：岗位爬取 → AI 匹配评分 → 打招呼生成 → 人工审批 → 自动投递

## 功能特性

- **岗位爬取**：Patchright（Undetected Playwright）按关键词/城市/薪资自动抓取 BOSS 直聘职位
- **AI 匹配评分**：Sentence-Transformers 向量相似度 + 技能门槛打分（0-100），自动分档（跳过/低优先/匹配）
- **简历定制**：ResumeAgent 根据 JD 关键词自动改写简历要点，保留结构字段；可在岗位详情页手动触发
- **打招呼生成**：MessageAgent 根据 JD 和个人档案生成约 120 字个性化打招呼语，UI 可编辑
- **人工在环**：所有投递必须在 Web UI 批准后才执行，保证账号安全
- **自动投递**：Gaussian 抖动限速 + 单日上限，模拟人工操作节奏
- **定时调度**：APScheduler 支持设置工作时段，按间隔自动执行全流程
- **状态追踪**：记录每条投递的发送状态（已发/已读/已回复）

## 快速开始

### 1. 安装依赖

```bash
# Python 后端
pip install -r requirements.txt

# 安装 Patchright 浏览器
python -m patchright install chromium

# Next.js 前端
cd frontend && npm install
```

### 2. 配置

```bash
# 后端配置
cp .env.example .env
# 编辑 .env，至少填写 DEEPSEEK_API_KEY（或其他兼容 OpenAI 协议的 LLM 服务）

# 前端配置
cp frontend/.env.local.example frontend/.env.local
# 默认指向 http://localhost:8080，通常无需修改

# 个人档案
cp user_profile.example.json user_profile.json
# 编辑 user_profile.json，填写个人经历、项目和求职目标
```

`.env` 关键字段：

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | LLM API Key（必填） | — |
| `DEEPSEEK_MODEL` | 模型名称 | `deepseek-v4-flash` |
| `DEEPSEEK_BASE_URL` | API Base URL（换其他服务改此处） | `https://api.deepseek.com/v1` |
| `BOSS_SEARCH_KEYWORDS` | 搜索关键词，逗号分隔 | `AI全栈` |
| `BOSS_SEARCH_CITY` | 搜索城市 | `广州` |
| `DAILY_APPLY_LIMIT` | 单日投递上限 | `30` |
| `HF_HUB_OFFLINE` | 模型已缓存后设为 `1`，禁止联网检查 | `1` |

### 3. 启动

```bash
# Linux / macOS：同时启动后端 + 前端
./start.sh

# Windows（推荐分别启动）：
python run.py              # 后端（必须用此命令，设置 ProactorEventLoop）
cd frontend && npm run dev  # 前端（另开终端）
```

打开浏览器访问 http://localhost:3001

### 4. 首次使用

1. 在仪表板点击「开始爬取」；若尚未登录 BOSS，会自动弹出浏览器窗口，请扫码登录
2. 等待 AI 评分和打招呼生成完成（可在进度条查看）
3. 在岗位列表对匹配岗位点击「批准投递」或「跳过」
4. 点击「一键投递已批准」开始自动发送

## 技术架构

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 14 + shadcn/ui + Tailwind CSS |
| 后端 | FastAPI + SQLModel (SQLite WAL) |
| 浏览器自动化 | Patchright (Undetected Playwright) |
| AI / LLM | LangChain + DeepSeek v4-flash（兼容任意 OpenAI 协议服务）|
| 向量匹配 | sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2) |
| 定时调度 | APScheduler 3.10 |
| 数据库 | SQLite (WAL 模式) |

## 项目结构

```
├── backend/
│   ├── main.py              # FastAPI 入口 + lifespan 事件
│   ├── run.py               # Windows 启动入口（设置 ProactorEventLoop）
│   ├── core/                # 配置 / LLM / 用户档案 / 运行时设置
│   ├── db/                  # 数据库模型 (Job/Application/ResumeSnapshot) + CRUD
│   ├── automation/          # Patchright 爬虫 + 登录 + 投递
│   ├── agents/              # AI Agent（MessageAgent 打招呼 + ResumeAgent 简历定制）
│   ├── scoring/             # 向量评分 + 薪资解析
│   ├── skills/              # 可组合技能单元（爬取/评分/生成/投递/简历解析）
│   ├── agent/               # HermesOrchestrator + APScheduler 调度器
│   ├── resume_parser/       # PDF 简历解析
│   └── api/                 # REST API 路由（jobs/apply/resume/auth/settings/analytics）
├── frontend/
│   └── app/                 # Next.js 页面（dashboard/jobs/records/analytics/profile/settings）
├── agent_settings.json      # Agent 运行时设置（搜索参数、评分阈值、打招呼配置等）
├── user_profile.example.json
├── .env.example
└── requirements.txt
```

## 安全说明

- Cookie 本地存储，不进 git（`.gitignore` 已覆盖）
- 不保存账号密码
- 单日投递上限 30 份（`DAILY_APPLY_LIMIT` 可调）
- 验证码出现时自动暂停，等待人工处理
- 手机验证码弹窗等待最长 120 秒后继续
- 通过岗位列表页操作时，投递必须经人工逐一审批；通过 Agent 对话界面可指示 AI 批量批准并自动投递，属于全自动模式

## 运行测试

```bash
pytest backend/tests/ -v
# 跳过需要真实 API Key 的测试：
pytest backend/tests/ -v -m "not slow"
```
