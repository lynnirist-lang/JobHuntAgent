"""
Skill: generate_greeting

批量为 PENDING 状态的岗位生成打招呼语。
并发参数和生成行为均由 AgentSettings.greeting（GreetingConfig）驱动：
  concurrency / timeout → 并发控制
  tone / word_count / include_* / suffix / extra_instruction → AI 生成行为
"""
import asyncio
import logging
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ...agents.message_agent import MessageAgent
from ...db.models import Job, JobStatus
from ...db.crud import update_job_match_result
from ...core.profile import load_profile
from ...core.settings_store import load_settings

logger = logging.getLogger(__name__)


class GenerateGreetingSkill:
    NAME = "generate_greeting"

    def __init__(self):
        self._agent = MessageAgent()

    async def execute(self, inputs: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        job_ids: List[int] = inputs["job_ids"]

        result = await session.execute(
            select(Job).where(Job.id.in_(job_ids), Job.status == JobStatus.PENDING)
        )
        jobs = result.scalars().all()

        if not jobs:
            return {"success_count": 0, "failed_ids": [], "timeout_ids": []}

        profile = load_profile()
        greeting_cfg = load_settings().greeting  # 运行时读取，支持热更新
        sem = asyncio.Semaphore(greeting_cfg.concurrency)

        total        = len(jobs)
        success_count = 0
        failed_ids:  List[int] = []
        timeout_ids: List[int] = []

        logger.info(
            "开始批量生成打招呼语：共 %d 个岗位，并发=%d，超时=%ds，语气=%s，目标字数=%d",
            total, greeting_cfg.concurrency, greeting_cfg.timeout,
            greeting_cfg.tone, greeting_cfg.word_count,
        )

        async def _generate_one(job: Job, idx: int) -> None:
            nonlocal success_count
            async with sem:
                jd_text = f"{job.description}\n{job.requirements}"
                try:
                    greeting = await asyncio.wait_for(
                        self._agent.generate(
                            jd_text=jd_text,
                            profile=profile,
                            config=greeting_cfg,
                        ),
                        timeout=greeting_cfg.timeout,
                    )
                    await update_job_match_result(session, job.id, greeting)
                    success_count += 1
                    logger.info(
                        "[%d/%d] job_id=%-5d 生成成功（%d 字）",
                        idx, total, job.id, len(greeting),
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "[%d/%d] job_id=%-5d 超时（>%ds）",
                        idx, total, job.id, greeting_cfg.timeout,
                    )
                    timeout_ids.append(job.id)
                except Exception as e:
                    logger.warning(
                        "[%d/%d] job_id=%-5d 失败：%s",
                        idx, total, job.id, e,
                    )
                    failed_ids.append(job.id)

        await asyncio.gather(
            *[_generate_one(job, i + 1) for i, job in enumerate(jobs)]
        )

        logger.info(
            "打招呼生成完成：成功 %d / %d，失败 %d，超时 %d",
            success_count, total, len(failed_ids), len(timeout_ids),
        )
        return {
            "success_count": success_count,
            "failed_ids":    failed_ids,
            "timeout_ids":   timeout_ids,
        }
