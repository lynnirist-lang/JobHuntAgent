"""
Skill: apply_job

对 boss_apply.apply_batch() 的薄封装，专门处理 PENDING_SEND → SENT 的流转。
"""
import logging
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ...automation.boss_apply import apply_batch, ApplyTarget
from ...automation.browser import run_in_browser_loop
from ...db.models import Job, JobStatus, Application, ApplicationStatus, ResumeSnapshot
from ...db.crud import create_resume_snapshot
from ...core.profile import load_profile

logger = logging.getLogger(__name__)


class ApplyJobSkill:
    NAME = "apply_job"

    async def execute(self, inputs: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        job_ids: List[int] = inputs["job_ids"]

        result = await session.execute(
            select(Job).where(
                Job.id.in_(job_ids),
                Job.status == JobStatus.PENDING_SEND,
                Job.cooldown_until <= datetime.utcnow(),
            )
        )
        jobs = result.scalars().all()

        if not jobs:
            return {"success_count": 0, "success_ids": [], "failed_ids": [], "stopped_reason": "no_ready_jobs"}

        # 创建简历快照（本批次共用一份）
        profile = load_profile()
        snapshot = await create_resume_snapshot(session, profile)

        # 构造投递目标列表
        targets = [
            ApplyTarget(
                application_id=job.id,
                job_id=job.id,
                boss_url=job.boss_url,
                greeting_message=job.greeting_message or "",
            )
            for job in jobs
        ]

        # 今日已投数
        today_sent = await _count_today_sent(session)

        apply_result = await run_in_browser_loop(apply_batch(targets, today_already_sent=today_sent))

        # 写投递记录，更新状态
        for job in jobs:
            if job.id in apply_result.success_ids:
                app = Application(
                    job_id=job.id,
                    resume_snapshot_id=snapshot.id,
                    status=ApplicationStatus.SENT,
                    greeting_message=job.greeting_message or "",
                    sent_at=datetime.utcnow(),
                )
                session.add(app)
                job.status = JobStatus.SENT
            elif job.id in apply_result.failed_ids:
                job.status = JobStatus.FAILED

        await session.commit()

        return {
            "success_count": len(apply_result.success_ids),
            "success_ids": apply_result.success_ids,
            "failed_ids": apply_result.failed_ids,
            "stopped_reason": apply_result.stopped_reason or "",
        }


async def _count_today_sent(session: AsyncSession) -> int:
    from datetime import date
    from sqlmodel import func
    today_start = datetime.combine(date.today(), datetime.min.time())
    result = await session.execute(
        select(func.count()).where(
            Application.status == ApplicationStatus.SENT,
            Application.sent_at >= today_start,
        )
    )
    return result.scalar() or 0
