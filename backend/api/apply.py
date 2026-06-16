"""
投递相关 API 路由。

POST /apply/batch    — 批量投递已批准的岗位
GET  /apply/status   — 查询投递记录列表
GET  /apply/today    — 今日投递统计
"""

import asyncio
import logging
import sys
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from ..automation.boss_apply import ApplyResult, ApplyTarget, apply_batch
from ..db.crud import (
    count_today_sent,
    count_total_sent,
    create_application,
    create_resume_snapshot,
    get_applications,
    get_jobs,
    update_application_status,
    update_job_status,
)
from ..db.engine import get_async_session
from ..db.models import Application, ApplicationStatus, JobStatus
from ..core.profile import load_profile
from .deps import get_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/apply", tags=["投递"])

# 全局批量投递任务状态
_apply_status: Dict[str, Any] = {
    "running": False,
    "progress": "",
    "success_count": 0,
    "fail_count": 0,
    "total_jobs": 0,
    "stopped_reason": None,
    "alert": None,
}


# ─────────────────────────── 请求模型 ────────────────────────────

class BatchApplyRequest(BaseModel):
    job_ids: Optional[List[int]] = None  # None 表示投递所有 APPROVED 状态的岗位


# ─────────────────────────── 后台任务 ────────────────────────────

async def _run_batch_apply(job_ids: Optional[List[int]]) -> None:
    """
    后台执行批量投递。

    1. 查询所有 APPROVED 状态的岗位（或指定 job_ids）
    2. 为每个岗位创建 Application 记录
    3. 保存简历快照
    4. 调用 apply_batch 执行投递
    5. 根据结果更新数据库状态

    在 Windows 上通过独立的 ProactorEventLoop 线程运行，确保 Patchright 能正常创建浏览器子进程。
    """
    global _apply_status
    _apply_status["running"] = True
    _apply_status["alert"] = None
    _apply_status["stopped_reason"] = None

    async def _pipeline() -> None:
        async with get_async_session() as session:
            # 查询已批准的岗位
            if job_ids:
                from ..db.crud import get_job_by_id
                approved_jobs = [
                    j for j in [await get_job_by_id(session, jid) for jid in job_ids]
                    if j and j.status == JobStatus.APPROVED
                ]
            else:
                approved_jobs = list(await get_jobs(session, status=JobStatus.APPROVED, limit=200))

            if not approved_jobs:
                _apply_status["progress"] = "无待投递岗位"
                return

            _apply_status["progress"] = f"准备投递 {len(approved_jobs)} 个岗位…"

            # 保存简历快照（批量投递共用同一快照）
            profile = load_profile()
            snapshot = await create_resume_snapshot(session, profile)

            # 创建 Application 记录并构造 ApplyTarget 列表
            targets: List[ApplyTarget] = []
            for job in approved_jobs:
                if not job.greeting_message:
                    logger.warning("岗位 %d 无打招呼语，跳过", job.id)
                    continue
                app_record = await create_application(
                    session=session,
                    job_id=job.id,  # type: ignore[arg-type]
                    greeting_message=job.greeting_message,
                    resume_snapshot_id=snapshot.id,
                )
                targets.append(ApplyTarget(
                    application_id=app_record.id,  # type: ignore[arg-type]
                    job_id=job.id,  # type: ignore[arg-type]
                    boss_url=job.boss_url,
                    greeting_message=job.greeting_message,
                ))

            _apply_status["total_jobs"] = len(targets)

            # 查询今日已发送数量（用于上限检查）
            today_sent = await count_today_sent(session)

            # 执行批量投递
            result: ApplyResult = await apply_batch(targets, today_already_sent=today_sent)

            # 更新成功投递的记录
            for app_id in result.success_ids:
                await update_application_status(session, app_id, ApplicationStatus.SENT)
                app_record = await session.get(Application, app_id)
                if app_record:
                    await update_job_status(session, app_record.job_id, JobStatus.SENT)

            # 更新失败投递的记录
            for app_id in result.failed_ids:
                error_msg = result.errors.get(app_id, "未知错误")
                await update_application_status(
                    session, app_id, ApplicationStatus.FAILED, error_msg
                )

            _apply_status["success_count"] = len(result.success_ids)
            _apply_status["fail_count"] = len(result.failed_ids)

            if result.stopped_reason:
                _apply_status["stopped_reason"] = result.stopped_reason
                _apply_status["alert"] = result.stopped_reason

    try:
        # On Windows, route through ProactorEventLoop so Patchright can launch the browser.
        if sys.platform == "win32":
            from ..automation.browser import get_proactor_loop
            proactor = get_proactor_loop()
            fut = asyncio.run_coroutine_threadsafe(_pipeline(), proactor)
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: fut.result(timeout=600)
            )
        else:
            await _pipeline()
    except Exception as e:
        logger.error("批量投递任务异常：%s", e, exc_info=True)
        _apply_status["alert"] = f"投递异常：{e}"
    finally:
        _apply_status["running"] = False
        _apply_status["progress"] = "投递任务结束"


# ─────────────────────────── 路由 ────────────────────────────────

@router.post("/batch", summary="批量投递已批准岗位")
async def batch_apply(
    request: BatchApplyRequest,
    background_tasks: BackgroundTasks,
):
    """
    触发批量投递（异步后台执行）。

    所有岗位必须已通过 /jobs/{id}/approve 审批才会被投递。
    可通过 /apply/status 实时查询投递进度。
    """
    if _apply_status["running"]:
        raise HTTPException(status_code=409, detail="投递任务正在运行中")
    background_tasks.add_task(_run_batch_apply, request.job_ids)
    return {"message": "批量投递任务已启动，可通过 /apply/status 查询进度"}


@router.get("/task-status", summary="查询当前投递任务状态")
async def get_apply_task_status():
    """返回后台投递任务的实时状态，包含进度、成功数、失败数和告警信息。"""
    return _apply_status


@router.get("/today", summary="今日投递统计")
async def today_stats(session: AsyncSession = Depends(get_session)):
    """返回今日已发送投递数量和剩余配额。"""
    from ..core.settings_store import load_settings as _load_settings
    daily_limit = _load_settings().apply.daily_limit
    sent_count = await count_today_sent(session)
    total_sent = await count_total_sent(session)
    return {
        "today_sent": sent_count,
        "total_sent": total_sent,
        "daily_limit": daily_limit,
        "remaining": max(0, daily_limit - sent_count),
    }


@router.get("/status", summary="查询投递记录列表")
async def list_applications(
    status: Optional[ApplicationStatus] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """返回投递记录列表，含对应岗位信息。"""
    from ..db.crud import get_job_by_id
    apps = await get_applications(session, status=status, limit=limit, offset=offset)
    result = []
    for app in apps:
        job = await get_job_by_id(session, app.job_id)
        result.append({
            "id": app.id,
            "job_id": app.job_id,
            "job_title": job.title if job else "",
            "company": job.company if job else "",
            "status": app.status.value,
            "greeting_message": app.greeting_message,
            "sent_at": app.sent_at.isoformat() if app.sent_at else None,
            "error_message": app.error_message,
            "created_at": app.created_at.isoformat(),
        })
    return {"items": result, "count": len(result)}
