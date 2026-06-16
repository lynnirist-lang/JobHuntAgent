"""
Skill: adapt_resume

对现有 resume_agent.ResumeAgent.adapt_to_jd() 的薄封装。
"""
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ...agents.resume_agent import ResumeAgent
from ...db.models import Job
from ...core.profile import load_profile


class AdaptResumeSkill:
    NAME = "adapt_resume"

    def __init__(self):
        self._agent = ResumeAgent()

    async def execute(self, inputs: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        job_id: int = inputs["job_id"]

        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        jd_text = f"{job.description}\n{job.requirements}"
        profile = load_profile()

        adapted = await self._agent.adapt_to_jd(jd_text=jd_text, profile=profile)
        return adapted
