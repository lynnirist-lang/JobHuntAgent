"""
Hermes Agent 核心编排器。

完整半自动投递流水线：
  Step 1: scrape_jobs  → 爬取新岗位入库
  Step 2: generate_greeting → 批量生成打招呼语，状态变 MATCHED
  Step 3: 用户在 UI 审批（MATCHED → APPROVED，或跳过）
  Step 4: 用户点「启动投递」→ APPROVED → PENDING_SEND（30分钟冷却）
  Step 5: APScheduler 每5分钟调用 flush_cooldown → PENDING_SEND → SENT

Hermes 特性映射：
  Memory  → SQLite DB（Job/Application 表记录所有历史）
  Skills  → backend/skills/ 下的5个 Skill 类
  Learning → Application 表记录投递结果，后续可用于优化策略
  Human-in-the-loop → Step 3 用户审批 + Step 4 冷却期取消窗口
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..skills.scrape_jobs.skill import ScrapeJobsSkill
from ..skills.score_jobs.skill import ScoreJobsSkill
from ..skills.generate_greeting.skill import GenerateGreetingSkill
from ..skills.apply_job.skill import ApplyJobSkill
from ..db.models import Job, JobStatus
from ..core.settings_store import load_settings

logger = logging.getLogger(__name__)


class HermesOrchestrator:
    """
    Hermes Agent 主编排器。

    不持有自己的 DB session，由调用方（FastAPI 路由）传入，
    确保事务边界清晰。
    """

    def __init__(self):
        self.scrape_skill = ScrapeJobsSkill()
        self.score_skill = ScoreJobsSkill()
        self.greeting_skill = GenerateGreetingSkill()
        self.apply_skill = ApplyJobSkill()
        # 爬取任务运行状态（供 tools.py 和 agent.py 共享）
        self.scrape_status: dict = {"running": False, "last_result": None, "error": None}

    # ── Step 1+2: 爬取 + 生成打招呼（流水线前半段）──────────────

    async def run_scrape_pipeline(
        self,
        keywords: List[str],
        city: str,
        salary_code: str = "",
        max_pages: int = 0,
        session: AsyncSession = None,
    ) -> Dict[str, Any]:
        """
        爬取新岗位 → 批量生成打招呼语。
        结果写入 DB，前端轮询 /api/jobs 看进展。
        """
        agent_settings = load_settings()
        actual_max_pages = max_pages or agent_settings.max_pages
        logger.info(
            "[Hermes] scrape_jobs — keywords=%s city=%s max_pages=%d",
            keywords, city, actual_max_pages,
        )
        scrape_result = await self.scrape_skill.execute(
            {"keywords": keywords, "city": city, "salary_code": salary_code, "max_pages": actual_max_pages},
            session=session,
        )

        new_ids = scrape_result["new_job_ids"]
        score_result = {"eligible_ids": [], "low_priority_count": 0, "skipped_count": 0}
        greeting_result = {"success_count": 0, "failed_ids": [], "timeout_ids": []}

        if new_ids:
            logger.info("[Hermes] score_jobs — %d new jobs", len(new_ids))
            score_result = await self.score_skill.execute(
                {"job_ids": new_ids},
                session=session,
            )

            eligible_ids = score_result["eligible_ids"]
            if eligible_ids:
                logger.info("[Hermes] generate_greeting — %d eligible jobs", len(eligible_ids))
                greeting_result = await self.greeting_skill.execute(
                    {"job_ids": eligible_ids},
                    session=session,
                )

        return {
            "scraped_new": scrape_result["new_count"],
            "eligible_for_greeting": len(score_result["eligible_ids"]),
            "low_priority": score_result["low_priority_count"],
            "auto_skipped": score_result["skipped_count"],
            "greetings_generated": greeting_result["success_count"],
            "errors": scrape_result["errors"],
        }

    # ── Step 4: 启动投递 → 进入冷却队列 ─────────────────────────

    async def enqueue_for_sending(
        self,
        job_ids: List[int],
        session: AsyncSession,
        cooldown_minutes: int = 0,
    ) -> int:
        """
        将已批准的岗位加入冷却队列（APPROVED → PENDING_SEND）。
        冷却时长由 AgentSettings.cooldown_minutes 驱动，可通过 UI 热更新。
        """
        minutes = cooldown_minutes or load_settings().cooldown_minutes
        cooldown_until = datetime.utcnow() + timedelta(minutes=minutes)

        result = await session.execute(
            select(Job).where(Job.id.in_(job_ids), Job.status == JobStatus.APPROVED)
        )
        jobs = result.scalars().all()

        for job in jobs:
            job.status = JobStatus.PENDING_SEND
            job.cooldown_until = cooldown_until

        await session.commit()
        logger.info("[Hermes] enqueued %d jobs, cooldown_until=%s", len(jobs), cooldown_until)
        return len(jobs)

    # ── Step 4b: 用户撤销 → 从冷却队列移除 ──────────────────────

    async def cancel_pending(self, job_ids: List[int], session: AsyncSession) -> int:
        """冷却期内用户点「撤销」，回退到 APPROVED 状态。"""
        result = await session.execute(
            select(Job).where(Job.id.in_(job_ids), Job.status == JobStatus.PENDING_SEND)
        )
        jobs = result.scalars().all()

        for job in jobs:
            job.status = JobStatus.APPROVED
            job.cooldown_until = None

        await session.commit()
        return len(jobs)

    # ── Step 4c: 立即发送冷却队列（跳过剩余冷却时间）────────────

    async def flush_now(self, session: AsyncSession) -> Dict[str, Any]:
        """将所有 PENDING_SEND 岗位的冷却截止时间重置为过去，立即触发投递。"""
        result = await session.execute(
            select(Job).where(Job.status == JobStatus.PENDING_SEND)
        )
        jobs = result.scalars().all()
        if not jobs:
            return {"sent": 0, "failed": 0}

        past = datetime.utcnow() - timedelta(seconds=1)
        for job in jobs:
            job.cooldown_until = past
        await session.commit()

        logger.info("[Hermes] flush_now — 强制发送 %d 个冷却中岗位", len(jobs))
        return await self.flush_cooldown_queue(session)

    # ── Step 5: APScheduler 定时调用，执行冷却期满的投递 ─────────

    async def flush_cooldown_queue(self, session: AsyncSession) -> Dict[str, Any]:
        """
        将冷却期已过的 PENDING_SEND 岗位实际投递出去。
        由 scheduler.py 每5分钟调用一次。
        """
        result = await session.execute(
            select(Job).where(
                Job.status == JobStatus.PENDING_SEND,
                Job.cooldown_until <= datetime.utcnow(),
            )
        )
        ready_jobs = result.scalars().all()

        if not ready_jobs:
            return {"sent": 0, "failed": 0}

        logger.info("[Hermes] flush_cooldown — %d jobs ready", len(ready_jobs))
        apply_result = await self.apply_skill.execute(
            {"job_ids": [j.id for j in ready_jobs]},
            session=session,
        )

        return {
            "sent": apply_result["success_count"],
            "failed": len(apply_result["failed_ids"]),
        }


# 单例
_orchestrator: Optional[HermesOrchestrator] = None


def get_orchestrator() -> HermesOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = HermesOrchestrator()
    return _orchestrator
