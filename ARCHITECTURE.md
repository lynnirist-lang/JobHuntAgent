# 代码架构索引

> 本文档是代码库的导航地图，适合快速定位某个功能的实现位置，或理解系统各层之间的调用关系。

---

## 一、整体数据流

```
BOSS 直聘页面
     │  Patchright（Undetected Playwright）
     ▼
ScrapeJobsSkill          → 爬取 + 去重写库（PENDING）
     │
     ▼
ScoreJobsSkill           → 向量相似度 + 关键词匹配 + 薪资/经验/城市评分
     │  score < 30 → SKIPPED
     │  30-49     → LOW_PRIORITY
     │  ≥ 50      → 进入下一步
     ▼
GenerateGreetingSkill    → 并发生成打招呼语（MATCHED）
     │
     ▼
  用户审批（Web UI 或 Agent 对话）
     │  approve → APPROVED
     │  skip    → SKIPPED
     ▼
HermesOrchestrator       → 写入冷却截止时间（PENDING_SEND）
     │  APScheduler 每 5 分钟轮询
     ▼
ApplyJobSkill            → 浏览器自动填写 + 发送（SENT）
```

---

## 二、后端模块索引

### 启动 & 配置

| 文件 | 作用 |
|---|---|
| `backend/run.py` | Windows 入口，设置 `ProactorEventLoop` 后再启动 uvicorn，确保 Patchright 能创建子进程 |
| `backend/main.py` | FastAPI 工厂 + lifespan：初始化 DB、启动调度器、预热 Embedding 模型（放线程池，不阻塞事件循环） |
| `backend/core/config.py` | Pydantic Settings，从 `.env` 读取所有环境变量；`LLM_API_KEY` 兼容 `DEEPSEEK_API_KEY` |
| `backend/core/settings_store.py` | `AgentSettings` 模型 + `load_settings()` / `save_settings()`，每次调用都重新读文件，支持热更新 |
| `backend/core/profile.py` | `UserProfile` 数据模型 + 读写 `user_profile.json` |

### 流水线编排

| 文件 | 作用 |
|---|---|
| `backend/agent/orchestrator.py` | `HermesOrchestrator`：协调五个 Skill 的执行顺序，管理冷却队列，维护 `scrape_status` 字典供前端轮询 |
| `backend/agent/scheduler.py` | APScheduler 封装：定时触发 `run_scrape_pipeline`（工作时段内）+ 每 5 分钟触发 `flush_cooldown_queue` |
| `backend/agent/hermes_agent.py` | LLM 驱动的自然语言控制层，把用户的聊天指令转换为工具调用 |
| `backend/agent/tools.py` | Hermes 可调用的工具集：`start_scrape`、`batch_approve_jobs`、`enqueue_jobs`、`update_settings` 等 12 个工具 |

### 技能单元（Skills）

每个 Skill 是独立可测试的类，`execute()` 接收 session + 参数，返回统计结果。

| 文件 | 核心逻辑 |
|---|---|
| `backend/skills/scrape_jobs/skill.py` | 按关键词遍历爬取，通过 `run_in_browser_loop()` 跨越 asyncio/ProactorEventLoop 边界，upsert 写库 |
| `backend/skills/score_jobs/skill.py` | 调用 `JobScorer`，按阈值分档；评分失败时降级为合格（不阻断流水线） |
| `backend/skills/generate_greeting/skill.py` | `asyncio.Semaphore` 控制并发数，`asyncio.wait_for` 单任务超时，超时和异常分别统计 |
| `backend/skills/apply_job/skill.py` | 包装 `apply_batch`，处理投递结果写库 |
| `backend/skills/adapt_resume/skill.py` | 包装 `ResumeAgent.adapt_to_jd()`，供 API 手动触发 |
| `backend/skills/parse_resume_pdf/skill.py` | PDF/DOCX 文本提取 → 结构化为 `UserProfile` |

### AI Agent 实现

| 文件 | 核心逻辑 |
|---|---|
| `backend/agents/message_agent.py` | 三阶段生成：① 提取 JD 关键词 → ② 按关键词命中数排序简历片段 → ③ LLM 生成；`tenacity` 重试 3 次 |
| `backend/agents/resume_agent.py` | 三阶段适配：① 关键词 → ② 选 top-N 经历/项目 → ③ 仅改写 bullet points，原字段（公司/时间/技术栈）从模板还原，防止 AI 幻觉 |

### 评分引擎

| 文件 | 核心逻辑 |
|---|---|
| `backend/scoring/scorer.py` | 四维加权评分：技能 40% + 经验 25% + 薪资 20% + 城市 15%；`asyncio.to_thread` 将 embedding 推到线程池 |
| `backend/scoring/embedder.py` | `sentence-transformers` 单例封装，首次调用时懒加载 |
| `backend/scoring/salary_parser.py` | 正则解析薪资范围（支持 "15-25k·13薪" 格式），计算目标区间与岗位区间的重叠率 |

**技能评分的两路融合：**
```
语义相似度（embedding cosine × 1.4）  ×  0.6
+
关键词命中率（matched / min(total, 5)）×  0.4
= 技能分（0-100）
```
> ×1.4 是因为多语言模型在中文上余弦相似度普遍偏低，经验补偿系数。

### 浏览器自动化

| 文件 | 核心逻辑 |
|---|---|
| `backend/automation/browser.py` | Patchright 单例 BrowserContext，持久化 cookies，Windows 下维护独立的 ProactorEventLoop 线程 |
| `backend/automation/boss_scraper.py` | 页面解析，选择器从 `data/selectors.json` 读取（与代码解耦，方便维护） |
| `backend/automation/boss_apply.py` | 核心投递逻辑：多选择器链查找按钮、分块模拟打字（30-80ms 间隔）、Gaussian 延迟、验证码/风控/连续失败熔断 |
| `backend/automation/boss_login.py` | Cookie 加载 → 有效性检测 → 失效时弹出浏览器等待扫码 |

### 数据库

| 文件 | 作用 |
|---|---|
| `backend/db/models.py` | 三张表：`Job`（岗位 + 状态机）、`Application`（投递记录）、`ResumeSnapshot`（投递时的简历快照） |
| `backend/db/engine.py` | 异步 SQLAlchemy 引擎，启动时开启 WAL 模式（支持读写并发），自动处理新增字段的 ALTER TABLE |
| `backend/db/crud.py` | 所有 DB 读写操作的统一入口 |

### API 路由

| 文件 | 路由前缀 | 主要端点 |
|---|---|---|
| `backend/api/jobs.py` | `/jobs` | 列表、详情、触发爬取、批准/跳过、修改打招呼、触发简历适配 |
| `backend/api/apply.py` | `/apply` | 批量投递（后台任务）、任务状态轮询、今日统计 |
| `backend/api/resume.py` | `/resume` | 上传 PDF 解析、读写 `user_profile.json` |
| `backend/api/settings.py` | `/settings` | 读写 `agent_settings.json`，支持全量更新和搜索参数局部更新 |
| `backend/api/agent.py` | `/agent` | Hermes 对话（SSE 流式）、控制台快照 |
| `backend/api/analytics.py` | `/analytics` | 汇总指标、每日趋势、岗位分类、评分分布 |
| `backend/api/auth.py` | `/auth` | BOSS 登录状态检查、触发登录、登出 |

---

## 三、前端页面索引

| 路径 | 文件 | 作用 |
|---|---|---|
| `/` | `app/page.tsx` | 控制台：一键爬取、待投队列倒计时、今日配额、操作日志；每 3 秒轮询（仅任务运行时） |
| `/jobs` | `app/jobs/page.tsx` | 岗位列表：展开查看 JD + 打招呼稿 + 简历适配结果，批准后立即触发投递 |
| `/records` | `app/records/page.tsx` | 投递记录：按状态筛选，查看每条投递详情 |
| `/analytics` | `app/analytics/page.tsx` | 效果分析：趋势图、岗位分类饼图、评分分布、智能洞察 |
| `/settings` | `app/settings/page.tsx` | 策略配置：评分阈值、打招呼风格、投递延迟等，保存后立即生效（无需重启） |
| `/profile` | `app/profile/page.tsx` | 个人档案编辑：上传 PDF 自动解析，或手动填写 |
| `/chat` | `app/chat/page.tsx` | Hermes Agent 对话界面：自然语言控制全流程 |

---

## 四、关键设计决策

**1. 两个事件循环**
Windows 上 FastAPI 运行在 asyncio 默认循环，而 Patchright 需要 `ProactorEventLoop` 才能创建浏览器子进程。解决方案：启动时另开一个线程专跑 ProactorEventLoop，所有浏览器操作通过 `asyncio.run_coroutine_threadsafe` 提交过去。

**2. 配置热更新**
所有 Skill 在 `execute()` 时调用 `load_settings()` 重新读文件，而不是在 `__init__` 缓存。前端改完配置保存，下一次运行就用新值，不需要重启。

**3. 简历适配的字段还原**
LLM 改写后容易微调公司名、时间等不应变动的字段。`ResumeAgent` 的做法是：改写前把原始字段存入模板，改写后用模糊匹配将这些字段逐一还原，只保留 AI 输出的 bullet points。

**4. Embedding 补偿系数**
`paraphrase-multilingual-MiniLM-L12-v2` 在中文文本上余弦相似度普遍比英文低 20-30%，直接用会导致评分虚低。评分时对相似度乘以 1.4 做经验补偿。

**5. 选择器外置**
BOSS 直聘页面结构会改变。CSS 选择器统一放在 `data/selectors.json`，改选择器不动代码。

---

## 五、快速定位

| 想查什么 | 去哪里找 |
|---|---|
| 岗位评分算法 | `backend/scoring/scorer.py` → `score()` |
| 打招呼如何生成 | `backend/agents/message_agent.py` → `generate()` |
| 简历改写逻辑 | `backend/agents/resume_agent.py` → `adapt_to_jd()` |
| 投递如何防封号 | `backend/automation/boss_apply.py` → `apply_batch()` |
| 定时任务如何触发 | `backend/agent/scheduler.py` |
| Agent 有哪些能力 | `backend/agent/tools.py` → `TOOL_DEFS` |
| 前端如何知道进度 | `frontend/app/page.tsx` → `fetchStatus()` 轮询 |
| 数据库表结构 | `backend/db/models.py` |
| 某个配置项在哪里用 | `backend/core/settings_store.py` → 字段注释 |
