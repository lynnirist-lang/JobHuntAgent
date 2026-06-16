"""
岗位相关 API 路由。

GET  /jobs               — 查询岗位列表（支持状态筛选）
GET  /jobs/{id}          — 查询单个岗位详情
POST /jobs/scrape        — 触发爬取（委托给 HermesOrchestrator）
POST /jobs/retry-greetings — 为已抓取但缺少打招呼语的 PENDING 岗位重新生成
POST /jobs/{id}/approve  — 人工批准岗位（设为 APPROVED 状态）
POST /jobs/{id}/skip     — 人工跳过岗位
PATCH /jobs/{id}/greeting — 编辑打招呼语
GET  /jobs/scrape/status  — 查询当前爬取任务状态
POST /jobs/{id}/resume-adapt — 根据 JD 适配简历内容（不写库，仅返回预览）
"""

import asyncio
import logging
import sys
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from ..agents.resume_agent import ResumeAgent
from ..agent.orchestrator import get_orchestrator
from ..core.config import get_settings
from ..core.profile import load_profile
from ..core.settings_store import load_settings
from ..db.crud import get_jobs, get_job_by_id, update_job_greeting, update_job_status
from ..db.models import Job, JobStatus
from ..db.engine import get_async_session
from .deps import get_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["岗位"])

# 爬取任务状态（直接复用 agent.py 中的 _task_status，或保留独立状态供旧前端轮询）
_scrape_status: Dict[str, Any] = {
    "running": False,
    "progress": "",
    "total": 0,
    "errors": [],
    "stopped_reason": None,
}


# ─────────────────────────── 请求/响应模型 ───────────────────────

class ScrapeRequest(BaseModel):
    keywords: Optional[List[str]] = None
    city: Optional[str] = None
    salary_code: str = ""
    max_pages: int = 3


class GreetingUpdateRequest(BaseModel):
    message: str


# ─────────────────────────── 路由 ────────────────────────────────

@router.get("", summary="查询岗位列表")
async def list_jobs(
    status: Optional[JobStatus] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """返回岗位列表，可按状态筛选，按爬取时间倒序。"""
    jobs = await get_jobs(session, status=status, limit=limit, offset=offset)
    return {
        "items": [_job_to_dict(j) for j in jobs],
        "count": len(jobs),
    }


@router.get("/scrape/status", summary="查询爬取任务状态")
async def get_scrape_status():
    """返回当前（或最近一次）爬取任务的运行状态。"""
    return _scrape_status


@router.post("/retry-greetings", summary="为 PENDING 岗位重新生成打招呼语")
async def retry_greetings(background_tasks: BackgroundTasks):
    """
    对数据库中所有 PENDING 状态且无打招呼语的岗位重新触发生成。
    适用于 API 余额不足等原因导致生成失败的情况，无需重新爬取。
    """
    if _scrape_status["running"]:
        raise HTTPException(status_code=409, detail="爬取任务正在运行中，请等待完成后再触发")

    async def _retry():
        _scrape_status["running"] = True
        _scrape_status["stopped_reason"] = None
        try:
            from ..skills.generate_greeting.skill import GenerateGreetingSkill
            from sqlmodel import select

            async def _pipeline():
                async with get_async_session() as session:
                    result = await session.execute(
                        select(Job).where(
                            Job.status == JobStatus.PENDING,
                            Job.greeting_message.is_(None),
                        )
                    )
                    pending_jobs = result.scalars().all()
                    if not pending_jobs:
                        return {"success_count": 0, "failed_ids": [], "timeout_ids": []}
                    job_ids = [j.id for j in pending_jobs]
                    logger.info("retry-greetings: %d 个 PENDING 岗位待生成", len(job_ids))
                    skill = GenerateGreetingSkill()
                    return await skill.execute({"job_ids": job_ids}, session=session)

            if sys.platform == "win32":
                from ..automation.browser import get_proactor_loop
                proactor = get_proactor_loop()
                fut = asyncio.run_coroutine_threadsafe(_pipeline(), proactor)
                gr = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: fut.result(timeout=300)
                )
            else:
                gr = await _pipeline()

            _scrape_status["total"] = gr["success_count"]
            logger.info("retry-greetings 完成：成功 %d", gr["success_count"])
        except Exception as e:
            logger.exception("retry-greetings 任务异常")
            _scrape_status["stopped_reason"] = str(e)
        finally:
            _scrape_status["running"] = False
            _scrape_status["progress"] = "打招呼重新生成完成"

    background_tasks.add_task(_retry)
    return {"message": "打招呼重新生成任务已启动，可通过 /jobs/scrape/status 查询进度"}


@router.post("/scrape", summary="触发爬取任务（委托给 HermesOrchestrator）")
async def trigger_scrape(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
):
    """
    触发 BOSS 直聘爬取 + 打招呼生成任务（异步后台执行）。
    内部委托给 HermesOrchestrator.run_scrape_pipeline()。
    若已有任务在运行，返回 409 冲突。
    """
    if _scrape_status["running"]:
        raise HTTPException(status_code=409, detail="爬取任务正在运行中，请等待完成后再触发")

    settings = get_settings()
    keywords = request.keywords or settings.keywords_list
    city = request.city or settings.boss_search_city

    async def _run():
        _scrape_status["running"] = True
        _scrape_status["errors"] = []
        _scrape_status["stopped_reason"] = None
        try:
            orchestrator = get_orchestrator()

            async def _pipeline():
                async with get_async_session() as session:
                    return await orchestrator.run_scrape_pipeline(
                        keywords=keywords,
                        city=city,
                        salary_code=request.salary_code,
                        max_pages=request.max_pages,
                        session=session,
                    )

            # On Windows, Patchright requires ProactorEventLoop for subprocess creation.
            # Route the entire pipeline (including DB session) through a dedicated
            # ProactorEventLoop thread so it works regardless of uvicorn's loop type.
            if sys.platform == "win32":
                from ..automation.browser import get_proactor_loop
                proactor = get_proactor_loop()
                fut = asyncio.run_coroutine_threadsafe(_pipeline(), proactor)
                result = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: fut.result(timeout=600)
                )
            else:
                result = await _pipeline()

            _scrape_status["total"] = result["scraped_new"]
            _scrape_status["errors"] = result["errors"]
        except Exception as e:
            logger.exception("爬取任务异常")
            _scrape_status["stopped_reason"] = str(e)
        finally:
            _scrape_status["running"] = False
            _scrape_status["progress"] = "任务完成"

    background_tasks.add_task(_run)
    return {"message": "爬取任务已启动，可通过 /jobs/scrape/status 查询进度"}


@router.get("/{job_id}", summary="查询单个岗位详情")
async def get_job(job_id: int, session: AsyncSession = Depends(get_session)):
    """返回单个岗位的完整信息。"""
    job = await get_job_by_id(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return _job_to_dict(job)


@router.post("/{job_id}/approve", summary="批准岗位（加入待投递队列）")
async def approve_job(job_id: int, session: AsyncSession = Depends(get_session)):
    """将岗位状态设为 APPROVED，进入待投递队列。"""
    job = await update_job_status(session, job_id, JobStatus.APPROVED)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return {"message": "已批准", "job_id": job_id}


@router.post("/{job_id}/skip", summary="跳过岗位")
async def skip_job(job_id: int, session: AsyncSession = Depends(get_session)):
    """将岗位状态设为 SKIPPED。"""
    job = await update_job_status(session, job_id, JobStatus.SKIPPED)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return {"message": "已跳过", "job_id": job_id}


@router.patch("/{job_id}/greeting", summary="更新打招呼语")
async def update_greeting(
    job_id: int,
    body: GreetingUpdateRequest,
    session: AsyncSession = Depends(get_session),
):
    """用户在 UI 编辑打招呼语后调用，保存修改后的版本。"""
    job = await update_job_greeting(session, job_id, body.message)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return {"message": "打招呼语已更新", "job_id": job_id}


@router.post("/{job_id}/resume-adapt", summary="根据 JD 适配简历内容（预览，不写库）")
async def adapt_resume_for_job(
    job_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    根据指定岗位的 JD，对当前 user_profile 中的工作经历和项目进行改写。

    只调整措辞和侧重点，不新增用户没有的内容。
    结果仅作为预览返回，不修改任何数据库记录或档案文件。
    """
    job = await get_job_by_id(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")

    jd_text = f"{job.description}\n{job.requirements}".strip()
    if not jd_text:
        raise HTTPException(status_code=400, detail="该岗位暂无 JD 内容，无法适配")

    profile = load_profile()
    agent = ResumeAgent()
    resume_adapt_cfg = load_settings().resume_adapt
    try:
        result = await agent.adapt_to_jd(jd_text, profile, config=resume_adapt_cfg)
    except Exception as e:
        logger.error("简历适配失败 job_id=%d: %s", job_id, e)
        raise HTTPException(status_code=500, detail=f"简历适配失败：{e}")

    return result


# ─────────────────────────── 工具函数 ────────────────────────────

def _job_to_dict(job: Job) -> dict:
    """将 Job ORM 对象转为可序列化的字典。"""
    return {
        "id": job.id,
        "boss_job_id": job.boss_job_id,
        "title": job.title,
        "company": job.company,
        "salary": job.salary,
        "location": job.location,
        "description": job.description,
        "requirements": job.requirements,
        "boss_url": job.boss_url,
        "status": job.status.value,
        "greeting_message": job.greeting_message,
        "scraped_at": job.scraped_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }
