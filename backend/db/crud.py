"""
数据库 CRUD 操作封装。

所有函数接收 AsyncSession，由 FastAPI 依赖注入（get_session）提供。
WAL 模式在 engine 初始化时启用，支持爬虫并发写入与 API 读取。
"""

import logging
from datetime import datetime, date
from typing import TYPE_CHECKING, List, Optional, Sequence

from sqlalchemy import func, select
from sqlmodel import col
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import Application, ApplicationStatus, Job, JobStatus, ResumeSnapshot

if TYPE_CHECKING:
    from ..core.profile import UserProfile
    from ..automation.boss_scraper import ScrapedJob
    from ..scoring.models import ScoreResult

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Job CRUD
# ═══════════════════════════════════════════════════════════════

async def get_jobs(
    session: AsyncSession,
    status: Optional[JobStatus] = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[Job]:
    """查询岗位列表，支持状态过滤，按爬取时间倒序。"""
    stmt = select(Job).order_by(col(Job.scraped_at).desc())
    if status:
        stmt = stmt.where(Job.status == status)
    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_job_by_id(session: AsyncSession, job_id: int) -> Optional[Job]:
    """按主键查询单个岗位。"""
    return await session.get(Job, job_id)


async def get_job_by_boss_id(session: AsyncSession, boss_job_id: str) -> Optional[Job]:
    """按 BOSS 平台 job_id 查询，用于爬虫去重判断。"""
    stmt = select(Job).where(Job.boss_job_id == boss_job_id)
    result = await session.execute(stmt)
    return result.scalars().first()


async def upsert_job(session: AsyncSession, scraped: "ScrapedJob") -> tuple["Job", bool]:
    """
    插入或更新岗位，返回 (Job, is_new)。

    若 boss_job_id 已存在，仅更新描述类字段（不覆盖状态和打招呼语）。
    若是新岗位，直接插入，返回 is_new=True。
    """
    existing = await get_job_by_boss_id(session, scraped.boss_job_id)
    if existing:
        existing.title = scraped.title
        existing.salary = scraped.salary
        existing.description = scraped.description
        existing.requirements = scraped.requirements
        existing.boss_url = scraped.boss_url
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing, False
    job = Job(
        boss_job_id=scraped.boss_job_id,
        title=scraped.title,
        company=scraped.company,
        salary=scraped.salary,
        location=scraped.location,
        description=scraped.description,
        requirements=scraped.requirements,
        boss_url=scraped.boss_url,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job, True


async def update_job_match_result(
    session: AsyncSession,
    job_id: int,
    greeting_message: Optional[str],
) -> Optional[Job]:
    """保存打招呼草稿并将岗位状态设为 MATCHED（待审核）。"""
    job = await get_job_by_id(session, job_id)
    if not job:
        return None
    job.greeting_message = greeting_message
    job.status = JobStatus.MATCHED
    job.updated_at = datetime.utcnow()
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def update_job_status(
    session: AsyncSession, job_id: int, status: JobStatus
) -> Optional[Job]:
    """更新岗位状态（如用户批准/跳过）。"""
    job = await get_job_by_id(session, job_id)
    if not job:
        return None
    job.status = status
    job.updated_at = datetime.utcnow()
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def update_job_score(
    session: AsyncSession,
    job_id: int,
    score_result: "ScoreResult",
) -> Optional[Job]:
    """
    将评分结果写入 Job 行，但不提交事务。
    调用方（ScoreJobsSkill）在批量处理完成后统一 commit，减少 DB 往返。
    """
    import json as _json
    job = await get_job_by_id(session, job_id)
    if not job:
        return None
    job.score = score_result.total_score
    job.match_reason = score_result.match_reason
    job.missing_skills = _json.dumps(score_result.missing_skills, ensure_ascii=False)
    job.red_flags = _json.dumps(score_result.red_flags, ensure_ascii=False)
    job.score_breakdown = score_result.breakdown.model_dump_json()
    job.updated_at = datetime.utcnow()
    session.add(job)
    return job


async def update_job_greeting(
    session: AsyncSession, job_id: int, message: str
) -> Optional[Job]:
    """用户在 UI 编辑打招呼语后调用此接口保存。"""
    job = await get_job_by_id(session, job_id)
    if not job:
        return None
    job.greeting_message = message
    job.updated_at = datetime.utcnow()
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


# ═══════════════════════════════════════════════════════════════
# Application CRUD
# ═══════════════════════════════════════════════════════════════

async def create_application(
    session: AsyncSession,
    job_id: int,
    greeting_message: str,
    resume_snapshot_id: Optional[int] = None,
) -> Application:
    """创建新投递记录（状态 APPROVED，待发送）。"""
    app = Application(
        job_id=job_id,
        greeting_message=greeting_message,
        resume_snapshot_id=resume_snapshot_id,
        status=ApplicationStatus.APPROVED,
    )
    session.add(app)
    await session.commit()
    await session.refresh(app)
    return app


async def get_applications(
    session: AsyncSession,
    status: Optional[ApplicationStatus] = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[Application]:
    """查询投递记录，可按状态筛选。"""
    stmt = (
        select(Application)
        .order_by(col(Application.created_at).desc())
    )
    if status:
        stmt = stmt.where(Application.status == status)
    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_application_status(
    session: AsyncSession,
    app_id: int,
    status: ApplicationStatus,
    error_message: Optional[str] = None,
) -> Optional[Application]:
    """更新投递状态，发送成功时记录 sent_at，失败时记录错误信息。"""
    app = await session.get(Application, app_id)
    if not app:
        return None
    app.status = status
    if status == ApplicationStatus.SENT:
        app.sent_at = datetime.utcnow()
    if error_message:
        app.error_message = error_message
    app.updated_at = datetime.utcnow()
    session.add(app)
    await session.commit()
    await session.refresh(app)
    return app


async def count_today_sent(session: AsyncSession) -> int:
    """统计今日已发送投递数量（以 job 状态为准，确保不超过总投递量）。"""
    today = date.today()
    stmt = (
        select(func.count(Application.job_id.distinct()))  # type: ignore[attr-defined]
        .join(Job, Job.id == Application.job_id)
        .where(
            Application.status.in_([  # type: ignore[attr-defined]
                ApplicationStatus.SENT,
                ApplicationStatus.READ,
                ApplicationStatus.REPLIED,
            ]),
            func.date(Application.sent_at) == today.isoformat(),
            Job.status.in_([JobStatus.SENT, JobStatus.READ, JobStatus.REPLIED]),  # type: ignore[attr-defined]
        )
    )
    result = await session.execute(stmt)
    return result.scalar() or 0


async def count_total_sent(session: AsyncSession) -> int:
    """统计历史累计已投递岗位数（以 job 表状态为准，与效果分析页一致）。"""
    stmt = select(func.count()).select_from(Job).where(
        Job.status.in_([JobStatus.SENT, JobStatus.READ, JobStatus.REPLIED])  # type: ignore[attr-defined]
    )
    result = await session.execute(stmt)
    return result.scalar() or 0


# ═══════════════════════════════════════════════════════════════
# ResumeSnapshot CRUD
# ═══════════════════════════════════════════════════════════════

async def create_resume_snapshot(
    session: AsyncSession, profile: "UserProfile"
) -> ResumeSnapshot:
    """在批量投递前保存当前简历快照，返回快照 ID 供 Application 关联。"""
    snapshot = ResumeSnapshot(content=profile.model_dump_json())
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    return snapshot


async def get_pending_send_ready(session: AsyncSession) -> Sequence[Job]:
    """查询冷却期已过、可立即投递的 PENDING_SEND 岗位。"""
    stmt = select(Job).where(
        Job.status == JobStatus.PENDING_SEND,
        Job.cooldown_until <= datetime.utcnow(),
    )
    result = await session.execute(stmt)
    return result.scalars().all()
