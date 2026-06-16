"""
Skill: scrape_jobs

对 boss_scraper.scrape_jobs() 的薄封装：
  输入验证 → 逐关键词爬取 → upsert 入库 → 返回新增 ID
"""
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from ...automation.boss_scraper import scrape_jobs
from ...automation.browser import run_in_browser_loop
from ...db.crud import upsert_job


class ScrapeJobsSkill:
    NAME = "scrape_jobs"

    async def execute(self, inputs: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        keywords: List[str] = inputs["keywords"]
        city: str = inputs["city"]
        salary_code: str = inputs.get("salary_code", "")
        max_pages: int = inputs.get("max_pages", 3)

        new_ids: List[int] = []
        errors: List[str] = []
        stopped_reason = ""

        for keyword in keywords:
            result = await run_in_browser_loop(scrape_jobs(
                keyword=keyword,
                city=city,
                salary_code=salary_code,
                max_pages=max_pages,
            ))
            for scraped_job in result.jobs:
                job_record, is_new = await upsert_job(session, scraped_job)
                if is_new:
                    new_ids.append(job_record.id)

            errors.extend(result.errors)
            if result.stopped_reason:
                stopped_reason = result.stopped_reason
                break  # 遇到风控/验证码，停止后续关键词

        return {
            "new_count": len(new_ids),
            "new_job_ids": new_ids,
            "errors": errors,
            "stopped_reason": stopped_reason,
        }
