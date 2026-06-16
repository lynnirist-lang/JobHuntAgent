"""
Skill: score_jobs

批量对 PENDING 岗位进行本地评分（sentence-transformers，无 API 调用）。
评分结果写入 DB；按分数设定岗位状态：

  score >= 50  → 保持 PENDING，纳入 eligible_ids（后续生成打招呼）
  score 30-49  → LOW_PRIORITY，跳过打招呼生成
  score < 30   → SKIPPED，自动忽略

降级策略：单个岗位评分失败时，纳入 eligible_ids 而非丢弃，
确保模型首次加载延迟或网络异常时不影响整体流程。
"""

import logging
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ...db.crud import update_job_score
from ...db.models import Job, JobStatus
from ...core.profile import load_profile
from ...core.settings_store import load_settings
from ...scoring.scorer import JobScorer

logger = logging.getLogger(__name__)


class ScoreJobsSkill:
    NAME = "score_jobs"

    def __init__(self):
        self._scorer = JobScorer()

    async def execute(self, inputs: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        job_ids: List[int] = inputs["job_ids"]

        result = await session.execute(
            select(Job).where(Job.id.in_(job_ids), Job.status == JobStatus.PENDING)
        )
        jobs = result.scalars().all()

        profile = load_profile()
        score_cfg = load_settings().score  # 运行时读取，支持热更新
        eligible_ids: List[int] = []
        low_priority_count = 0
        skipped_count = 0

        logger.info(
            "[score_jobs] 阈值：skip<%d  low_priority<%d  eligible>=%d",
            score_cfg.skip_threshold, score_cfg.eligible_threshold, score_cfg.eligible_threshold,
        )

        for job in jobs:
            try:
                score_result = await self._scorer.score(job, profile)
                await update_job_score(session, job.id, score_result)

                skill_s = score_result.breakdown.skill_score
                total_s = score_result.total_score
                if total_s < score_cfg.skip_threshold:
                    job.status = JobStatus.SKIPPED
                    skipped_count += 1
                elif total_s < score_cfg.eligible_threshold or skill_s < score_cfg.skill_gate:
                    # 技能分低于 skill_gate 时强制 LOW_PRIORITY，
                    # 防止城市/经验高分掩盖技能不符
                    if skill_s < score_cfg.skill_gate:
                        logger.debug(
                            "job_id=%d skill_score=%d < gate=%d → LOW_PRIORITY",
                            job.id, skill_s, score_cfg.skill_gate,
                        )
                    job.status = JobStatus.LOW_PRIORITY
                    low_priority_count += 1
                else:
                    eligible_ids.append(job.id)

            except Exception as e:
                logger.warning(
                    "评分失败 job_id=%d，降级为 eligible: %s", job.id, e
                )
                # 评分失败时纳入 eligible，避免因模型问题丢失岗位
                eligible_ids.append(job.id)

        await session.commit()

        logger.info(
            "[score_jobs] 完成: eligible=%d low_priority=%d skipped=%d",
            len(eligible_ids), low_priority_count, skipped_count,
        )
        return {
            "eligible_ids": eligible_ids,
            "low_priority_count": low_priority_count,
            "skipped_count": skipped_count,
        }
