"""
Hermes Agent HTTP 端点。

前端通过这些端点触发编排器各阶段，或通过 /agent/hermes 进行自然语言控制。
原有 /jobs/* 和 /apply/* 端点继续保留，用于 UI 查询/操作单条记录。
"""
import json as _json
import logging
from datetime import datetime, date
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from .deps import get_session
from ..db.engine import get_async_session
from ..db.models import Application, Job, JobStatus
from ..agent.orchestrator import get_orchestrator
from ..agent.scheduler import add_auto_scrape_job, remove_auto_scrape_job
from ..core.settings_store import load_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


# ── 请求/响应 Schema ──────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    keywords: List[str]
    city: str
    salary_code: str = ""
    max_pages: int = 3


class EnqueueRequest(BaseModel):
    job_ids: List[int]
    cooldown_minutes: int = 30


class ScheduleRequest(BaseModel):
    enabled: bool
    hour: int = 9
    minute: int = 0


class HermesChatRequest(BaseModel):
    messages: List[dict]


# ── Hermes 自然语言控制中枢 ───────────────────────────────────────

@router.post("/hermes", summary="Hermes 对话控制接口（流式）")
async def hermes_chat(
    req: HermesChatRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    接收用户自然语言消息，通过工具调用驱动求职流水线，流式返回结果。
    响应格式兼容 Vercel AI SDK v3 data stream（`0:"chunk"\\n`）。
    """
    from ..agent.hermes_agent import run as _hermes_run

    orchestrator = get_orchestrator()

    async def _generate():
        try:
            async for chunk in _hermes_run(req.messages, session, orchestrator):
                if chunk:
                    yield f"0:{_json.dumps(chunk, ensure_ascii=False)}\n"
        except Exception as exc:
            logger.exception("[/agent/hermes] 生成失败")
            error_msg = f"⚠️ Hermes 内部错误：{exc}"
            yield f"0:{_json.dumps(error_msg, ensure_ascii=False)}\n"
        finally:
            yield 'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'

    return StreamingResponse(
        _generate(),
        media_type="text/plain; charset=utf-8",
        headers={
            "X-Vercel-AI-Data-Stream": "v1",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ── Agent 控制台状态快照 ─────────────────────────────────────────

@router.get("/console-status", summary="Agent 控制台状态快照")
async def console_status(session: AsyncSession = Depends(get_session)):
    """
    一次性返回控制台所需的全部状态，供前端轮询（建议 15s 间隔）：
      job_counts    — 各状态岗位计数
      today_stats   — 今日投递统计
      scrape_status — 爬取任务运行状态
    """
    count_rows = (await session.execute(
        select(Job.status, func.count(Job.id)).group_by(Job.status)
    )).all()
    job_counts = {row[0].value: row[1] for row in count_rows}

    today_start = datetime.combine(date.today(), datetime.min.time())
    today_sent = (await session.execute(
        select(func.count()).select_from(Application).where(
            Application.sent_at >= today_start
        )
    )).scalar() or 0

    daily_limit = load_settings().apply.daily_limit

    return {
        "job_counts": job_counts,
        "today_stats": {
            "today_sent": today_sent,
            "daily_limit": daily_limit,
            "remaining": max(0, daily_limit - today_sent),
        },
        "scrape_status": get_orchestrator().scrape_status,
    }


# ── 原有手动触发端点（保留，供 UI 按钮使用）──────────────────────

@router.post("/run-scrape")
async def run_scrape(
    req: ScrapeRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """手动触发：爬取新岗位 + 生成打招呼语。"""
    orchestrator = get_orchestrator()
    if orchestrator.scrape_status["running"]:
        raise HTTPException(status_code=409, detail="已有任务运行中，请等待完成")

    async def _run():
        orchestrator.scrape_status.update(running=True, error=None)
        try:
            async with get_async_session() as s:
                result = await orchestrator.run_scrape_pipeline(
                    keywords=req.keywords,
                    city=req.city,
                    salary_code=req.salary_code,
                    max_pages=req.max_pages,
                    session=s,
                )
            orchestrator.scrape_status["last_result"] = result
        except Exception as e:
            logger.exception("scrape pipeline 失败")
            orchestrator.scrape_status["error"] = str(e)
        finally:
            orchestrator.scrape_status["running"] = False

    background_tasks.add_task(_run)
    return {"status": "started"}


@router.get("/task-status")
async def get_task_status():
    """前端轮询当前任务运行状态。"""
    return get_orchestrator().scrape_status


@router.post("/enqueue")
async def enqueue_jobs(
    req: EnqueueRequest,
    session: AsyncSession = Depends(get_session),
):
    """将已批准的岗位加入冷却队列（APPROVED → PENDING_SEND）。"""
    orchestrator = get_orchestrator()
    count = await orchestrator.enqueue_for_sending(
        job_ids=req.job_ids,
        session=session,
        cooldown_minutes=req.cooldown_minutes,
    )
    return {"enqueued": count}


@router.post("/cancel-pending")
async def cancel_pending(
    req: EnqueueRequest,
    session: AsyncSession = Depends(get_session),
):
    """冷却期内取消投递（PENDING_SEND → APPROVED）。"""
    orchestrator = get_orchestrator()
    count = await orchestrator.cancel_pending(
        job_ids=req.job_ids,
        session=session,
    )
    return {"cancelled": count}


@router.post("/restore-skipped")
async def restore_skipped(
    req: EnqueueRequest,
    session: AsyncSession = Depends(get_session),
):
    """将指定 SKIPPED 岗位恢复为 APPROVED，以便重新投递。"""
    result = await session.execute(
        select(Job).where(Job.id.in_(req.job_ids), Job.status == JobStatus.SKIPPED)
    )
    jobs = result.scalars().all()
    for job in jobs:
        job.status = JobStatus.APPROVED
    await session.commit()
    return {"restored": len(jobs)}


@router.post("/restore-failed")
async def restore_failed(
    req: EnqueueRequest,
    session: AsyncSession = Depends(get_session),
):
    """将指定 FAILED 岗位恢复为 APPROVED，以便重新投递。"""
    result = await session.execute(
        select(Job).where(Job.id.in_(req.job_ids), Job.status == JobStatus.FAILED)
    )
    jobs = result.scalars().all()
    for job in jobs:
        job.status = JobStatus.APPROVED
    await session.commit()
    return {"restored": len(jobs)}


@router.post("/flush-now")
async def flush_now(session: AsyncSession = Depends(get_session)):
    """跳过冷却时间，立即发送所有 PENDING_SEND 岗位。"""
    result = await get_orchestrator().flush_now(session)
    return result


@router.post("/schedule")
async def set_schedule(req: ScheduleRequest):
    """配置定时爬取任务。"""
    if req.enabled:
        add_auto_scrape_job(cron_hour=req.hour, cron_minute=req.minute)
        return {"status": "scheduled", "time": f"{req.hour:02d}:{req.minute:02d}"}
    else:
        remove_auto_scrape_job()
        return {"status": "removed"}
