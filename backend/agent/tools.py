"""
Hermes 工具集 — schema 定义 + 实现。

TOOL_DEFS      : OpenAI function-calling 格式的工具描述（LLM 可见）
execute_tool   : 工具名 → 实现函数分发（注入 session + orchestrator）

实现函数不暴露给 LLM，只有 schema 暴露。
session 和 orchestrator 由 hermes_agent.run() 注入，不出现在 schema 参数里。
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db.models import Application, Job, JobStatus
from ..core.settings_store import load_settings, save_settings
from ..db.engine import get_async_session

logger = logging.getLogger(__name__)


# ─────────────────────── 工具 Schema（LLM 可见）──────────────────────────

TOOL_DEFS: List[Dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_jobs",
            "description": "查询岗位列表，可按状态筛选。返回 ID、职位名、公司、薪资、匹配分、状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "matched", "approved", "pending_send",
                                 "sent", "skipped", "low_priority", "failed"],
                        "description": "按状态过滤，不传则返回所有状态",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回上限，默认 15",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_detail",
            "description": "查询单个岗位的完整信息：JD、匹配理由、缺失技能、打招呼文案。",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer", "description": "岗位 ID"},
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_job",
            "description": "批准单个岗位（MATCHED → APPROVED），等待后续加入投递队列。",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer", "description": "岗位 ID"},
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skip_job",
            "description": "跳过单个岗位（→ SKIPPED）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer", "description": "岗位 ID"},
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "batch_approve_jobs",
            "description": (
                "批量批准岗位。传 job_ids 则按列表批准；不传则批准所有 MATCHED 状态岗位。"
                "执行前应告知用户将批准的数量。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "要批准的岗位 ID 列表，不传则批准全部 MATCHED",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_greeting",
            "description": "修改指定岗位的打招呼文案内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer", "description": "岗位 ID"},
                    "message": {"type": "string", "description": "新的打招呼文案"},
                },
                "required": ["job_id", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_scrape",
            "description": (
                "启动岗位抓取 + 评分 + 打招呼生成全流水线（后台异步，立即返回）。"
                "完成后岗位状态变为 MATCHED，可用 get_scrape_status 查进度。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "搜索关键词，如 ['Python后端', 'AI工程师']",
                    },
                    "city": {"type": "string", "description": "城市名，如 '上海'、'北京'"},
                    "salary_code": {"type": "string", "description": "薪资筛选代码，可留空"},
                    "max_pages": {"type": "integer", "description": "最多抓取页数，默认 3"},
                },
                "required": ["keywords", "city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enqueue_jobs",
            "description": (
                "将已 APPROVED 的岗位加入冷却投递队列，冷却期满后自动发送打招呼。"
                "危险操作：执行前务必告知用户将投递的数量，确认后再调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "要加入队列的岗位 ID 列表",
                    },
                    "cooldown_minutes": {
                        "type": "integer",
                        "description": "冷却时间（分钟），默认 30",
                    },
                },
                "required": ["job_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_scrape_status",
            "description": "查询爬取任务的当前状态和上次结果。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_stats",
            "description": "查询今日投递统计：已投数量、日限额、剩余配额。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_settings",
            "description": "读取当前 Agent 策略配置（冷却时间、日限额、打招呼风格等）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_settings",
            "description": "修改 Agent 策略配置字段。执行前必须告知用户变更内容。支持子模型用点号分隔（如 apply.daily_limit）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": [
                            "mode", "cooldown_minutes", "max_pages",
                            "captcha_strategy", "fail_strategy",
                            "apply.daily_limit", "apply.delay_mean", "apply.consecutive_fail_limit",
                            "score.eligible_threshold", "score.skip_threshold",
                            "greeting.tone", "greeting.word_count", "greeting.concurrency",
                            "greeting.include_project", "resume_adapt.top_n",
                        ],
                        "description": "要修改的字段路径",
                    },
                    "value": {"description": "新值（数字、字符串或布尔值）"},
                },
                "required": ["field", "value"],
            },
        },
    },
]

# 工具名 → 用户可读的中文描述（用于流式进度提示）
TOOL_DISPLAY_NAMES: Dict[str, str] = {
    "list_jobs":          "查询岗位列表",
    "get_job_detail":     "查询岗位详情",
    "approve_job":        "批准岗位",
    "skip_job":           "跳过岗位",
    "batch_approve_jobs": "批量批准岗位",
    "update_greeting":    "更新打招呼文案",
    "start_scrape":       "启动爬取流水线",
    "enqueue_jobs":       "加入投递队列",
    "get_scrape_status":  "查询爬取状态",
    "get_today_stats":    "查询今日统计",
    "get_settings":       "读取策略配置",
    "update_settings":    "修改策略配置",
}


# ─────────────────────── 工具实现（不暴露给 LLM）────────────────────────

async def _list_jobs(
    session: AsyncSession,
    status: Optional[str] = None,
    limit: int = 15,
) -> str:
    stmt = select(Job)
    if status:
        try:
            stmt = stmt.where(Job.status == JobStatus(status))
        except ValueError:
            return f"⚠️ 未知状态值：{status}"
    # SQLite DESC 天然把 NULL 排最后，不需要 nullslast()
    stmt = stmt.order_by(Job.score.desc(), Job.scraped_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        filter_hint = f"（状态={status}）" if status else ""
        return f"无符合条件的岗位{filter_hint}。"

    lines = [f"共 {len(rows)} 条："]
    for j in rows:
        score_str = f"{j.score}分" if j.score is not None else "-"
        lines.append(
            f"• ID={j.id} [{j.status}] {j.title} @ {j.company}  {j.salary}  {score_str}"
        )
    return "\n".join(lines)


async def _get_job_detail(session: AsyncSession, job_id: int) -> str:
    job = await session.get(Job, job_id)
    if not job:
        return f"⚠️ 未找到 ID={job_id} 的岗位。"
    return "\n".join([
        f"**{job.title}** @ {job.company}",
        f"薪资：{job.salary}　地点：{job.location}　状态：{job.status}　匹配分：{job.score}",
        f"匹配理由：{job.match_reason or '（无）'}",
        f"缺失技能：{', '.join(job.missing_skills_list) or '无'}",
        f"风险提示：{', '.join(job.red_flags_list) or '无'}",
        f"打招呼文案：{job.greeting_message or '（未生成）'}",
    ])


async def _approve_job(session: AsyncSession, job_id: int) -> str:
    job = await session.get(Job, job_id)
    if not job:
        return f"⚠️ 未找到 ID={job_id} 的岗位。"
    if job.status not in (JobStatus.MATCHED, JobStatus.LOW_PRIORITY):
        return f"⚠️ 当前状态 {job.status} 无法批准（需为 matched）。"
    job.status = JobStatus.APPROVED
    job.updated_at = datetime.utcnow()
    await session.commit()
    return f"✅ 已批准：{job.title} @ {job.company}（ID={job_id}）"


async def _skip_job(session: AsyncSession, job_id: int) -> str:
    job = await session.get(Job, job_id)
    if not job:
        return f"⚠️ 未找到 ID={job_id} 的岗位。"
    job.status = JobStatus.SKIPPED
    job.updated_at = datetime.utcnow()
    await session.commit()
    return f"✅ 已跳过：{job.title} @ {job.company}（ID={job_id}）"


async def _batch_approve_jobs(
    session: AsyncSession,
    job_ids: Optional[List[int]] = None,
) -> str:
    stmt = select(Job).where(Job.status == JobStatus.MATCHED)
    if job_ids:
        stmt = stmt.where(Job.id.in_(job_ids))
    jobs = (await session.execute(stmt)).scalars().all()

    if not jobs:
        return "无 MATCHED 状态的岗位可批准。"

    for j in jobs:
        j.status = JobStatus.APPROVED
        j.updated_at = datetime.utcnow()
    await session.commit()

    sample = "、".join(f"{j.title}@{j.company}" for j in jobs[:3])
    suffix = f"等 {len(jobs)} 个" if len(jobs) > 3 else f"{len(jobs)} 个"
    return f"✅ 已批准 {suffix}岗位：{sample}{'...' if len(jobs) > 3 else ''}"


async def _update_greeting(session: AsyncSession, job_id: int, message: str) -> str:
    job = await session.get(Job, job_id)
    if not job:
        return f"⚠️ 未找到 ID={job_id} 的岗位。"
    job.greeting_message = message
    job.updated_at = datetime.utcnow()
    await session.commit()
    preview = message[:60] + ("…" if len(message) > 60 else "")
    return f"✅ 打招呼文案已更新（ID={job_id}）：{preview}"


async def _start_scrape(
    session: AsyncSession,
    orchestrator,
    keywords: List[str],
    city: str,
    salary_code: str = "",
    max_pages: int = 3,
) -> str:
    if orchestrator.scrape_status["running"]:
        return "⚠️ 已有爬取任务运行中，可用 get_scrape_status 查询进度。"

    async def _run():
        orchestrator.scrape_status.update(running=True, error=None)
        try:
            async with get_async_session() as s:
                result = await orchestrator.run_scrape_pipeline(
                    keywords=keywords, city=city,
                    salary_code=salary_code, max_pages=max_pages, session=s,
                )
            orchestrator.scrape_status["last_result"] = result
        except Exception as exc:
            logger.exception("[tools] start_scrape 失败")
            orchestrator.scrape_status["error"] = str(exc)
        finally:
            orchestrator.scrape_status["running"] = False

    asyncio.create_task(_run())
    return (
        f"✅ 爬取任务已启动 — 关键词：{keywords}，城市：{city}，最大 {max_pages} 页。\n"
        "预计 2-5 分钟完成，用 `get_scrape_status` 查进度。"
    )


async def _enqueue_jobs(
    session: AsyncSession,
    orchestrator,
    job_ids: List[int],
    cooldown_minutes: int = 30,
) -> str:
    count = await orchestrator.enqueue_for_sending(
        job_ids=job_ids, session=session, cooldown_minutes=cooldown_minutes
    )
    if count == 0:
        return "⚠️ 无 APPROVED 状态岗位被加入队列（请确认岗位已批准）。"
    return (
        f"✅ 已将 {count} 个岗位加入投递队列，"
        f"冷却 {cooldown_minutes} 分钟后自动发送打招呼。"
    )


async def _get_scrape_status(session: AsyncSession, orchestrator) -> str:
    s = orchestrator.scrape_status
    if s["running"]:
        return "⏳ 爬取任务正在运行中…"
    if s["error"]:
        return f"❌ 上次任务出错：{s['error']}"
    if s["last_result"]:
        r = s["last_result"]
        return (
            f"✅ 上次爬取结果：\n"
            f"• 新增岗位：{r.get('scraped_new', 0)}\n"
            f"• 符合条件：{r.get('eligible_for_greeting', 0)}\n"
            f"• 自动跳过：{r.get('auto_skipped', 0)}\n"
            f"• 打招呼已生成：{r.get('greetings_generated', 0)}"
        )
    return "暂无爬取记录，当前空闲。"


async def _get_today_stats(session: AsyncSession, orchestrator) -> str:
    from datetime import date
    from sqlalchemy import func

    today_start = datetime.combine(date.today(), datetime.min.time())
    result = await session.execute(
        select(func.count()).select_from(Application).where(
            Application.sent_at >= today_start,
        )
    )
    today_sent = result.scalar() or 0

    daily_limit = load_settings().apply.daily_limit
    remaining = max(0, daily_limit - today_sent)
    return f"今日已投：{today_sent} / {daily_limit}，剩余配额：{remaining}"


async def _get_settings(session: AsyncSession, orchestrator) -> str:
    s = load_settings()
    return (
        f"当前策略配置：\n"
        f"• 模式：{s.mode}\n"
        f"• 冷却时间：{s.cooldown_minutes} 分钟\n"
        f"• 最大抓取页数：{s.max_pages}\n"
        f"• 验证码策略：{s.captcha_strategy}  失败策略：{s.fail_strategy}\n"
        f"• 日投递上限：{s.apply.daily_limit}  连续失败上限：{s.apply.consecutive_fail_limit}\n"
        f"• 评分阈值：合格≥{s.score.eligible_threshold} / 跳过<{s.score.skip_threshold}\n"
        f"• 打招呼字数：{s.greeting.word_count}  语气：{s.greeting.tone}\n"
        f"• 简历适配 top_n：{s.resume_adapt.top_n}"
    )


# 支持的可修改字段：(parent_key_or_None, field_name, type_fn)
_UPDATABLE: dict = {
    "mode":                          (None,            "mode",                       str),
    "cooldown_minutes":              (None,            "cooldown_minutes",           int),
    "max_pages":                     (None,            "max_pages",                  int),
    "captcha_strategy":              (None,            "captcha_strategy",           str),
    "fail_strategy":                 (None,            "fail_strategy",              str),
    "apply.daily_limit":             ("apply",         "daily_limit",                int),
    "apply.delay_mean":              ("apply",         "delay_mean",                 float),
    "apply.consecutive_fail_limit":  ("apply",         "consecutive_fail_limit",     int),
    "score.eligible_threshold":      ("score",         "eligible_threshold",         int),
    "score.skip_threshold":          ("score",         "skip_threshold",             int),
    "greeting.tone":                 ("greeting",      "tone",                       str),
    "greeting.word_count":           ("greeting",      "word_count",                 int),
    "greeting.concurrency":          ("greeting",      "concurrency",                int),
    "greeting.include_project":      ("greeting",      "include_project",            bool),
    "resume_adapt.top_n":            ("resume_adapt",  "top_n",                      int),
}


async def _update_settings(
    session: AsyncSession,
    orchestrator,
    field: str,
    value: Any,
) -> str:
    if field not in _UPDATABLE:
        keys = ", ".join(sorted(_UPDATABLE.keys()))
        return f"⚠️ 不支持修改字段 `{field}`。可修改：{keys}"
    parent_key, attr_name, type_fn = _UPDATABLE[field]
    try:
        s = load_settings()
        if type_fn is bool:
            coerced = str(value).lower() in ("true", "1", "yes", "是")
        else:
            coerced = type_fn(value)
        if parent_key:
            setattr(getattr(s, parent_key), attr_name, coerced)
        else:
            setattr(s, attr_name, coerced)
        save_settings(s)
        return f"✅ 已将 `{field}` 更新为 `{coerced}`。"
    except (ValueError, TypeError) as exc:
        return f"⚠️ 值 `{value}` 类型错误（期望 {type_fn.__name__}）：{exc}"
    except Exception as exc:
        return f"⚠️ 修改失败：{exc}"


# ─────────────────────── 分发器 ──────────────────────────────────────────

async def execute_tool(
    name: str,
    args: Dict[str, Any],
    session: AsyncSession,
    orchestrator,
) -> str:
    """将 LLM 的工具调用路由到对应实现，统一注入 session 和 orchestrator。"""
    _DISPATCH = {
        "list_jobs":          lambda: _list_jobs(session, **args),
        "get_job_detail":     lambda: _get_job_detail(session, **args),
        "approve_job":        lambda: _approve_job(session, **args),
        "skip_job":           lambda: _skip_job(session, **args),
        "batch_approve_jobs": lambda: _batch_approve_jobs(session, **args),
        "update_greeting":    lambda: _update_greeting(session, **args),
        "start_scrape":       lambda: _start_scrape(session, orchestrator, **args),
        "enqueue_jobs":       lambda: _enqueue_jobs(session, orchestrator, **args),
        "get_scrape_status":  lambda: _get_scrape_status(session, orchestrator),
        "get_today_stats":    lambda: _get_today_stats(session, orchestrator),
        "get_settings":       lambda: _get_settings(session, orchestrator),
        "update_settings":    lambda: _update_settings(session, orchestrator, **args),
    }

    fn = _DISPATCH.get(name)
    if fn is None:
        return f"⚠️ 未知工具：{name}"

    try:
        return await fn()
    except TypeError as exc:
        logger.error("[tools] %s 参数错误 args=%s: %s", name, args, exc)
        return f"⚠️ 工具 `{name}` 参数错误：{exc}"
    except Exception as exc:
        logger.exception("[tools] %s 执行失败", name)
        return f"⚠️ 工具 `{name}` 执行出错：{exc}"
