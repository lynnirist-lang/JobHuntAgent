"""
APScheduler 定时任务管理。

两种运行模式（对应前端「策略配置」页的设置）：
  - 手动模式：只有用户点按钮才触发 scrape_pipeline
  - 定时模式：按用户设置的时间段自动运行 scrape_pipeline

无论哪种模式，cooldown flush 都每5分钟运行一次（保证冷却期满的岗位准时发出）。
"""
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    return _scheduler


def start_scheduler() -> None:
    """FastAPI startup 时调用，启动调度器并注册冷却期刷新任务。"""
    from .orchestrator import get_orchestrator
    from ..db.engine import get_async_session

    scheduler = get_scheduler()

    async def _flush_job():
        orchestrator = get_orchestrator()
        async with get_async_session() as session:
            result = await orchestrator.flush_cooldown_queue(session)
            if result["sent"] > 0:
                logger.info("冷却期刷新：发出 %d 份，失败 %d 份", result["sent"], result["failed"])

    # 每5分钟检查一次冷却队列（固定，不受用户设置影响）
    scheduler.add_job(
        _flush_job,
        trigger=IntervalTrigger(minutes=5),
        id="cooldown_flush",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("APScheduler 已启动，冷却期检查间隔 5 分钟")


def add_auto_scrape_job(cron_hour: int, cron_minute: int = 0) -> None:
    """
    添加/更新定时爬取任务。
    前端「策略配置」页切换到定时模式时调用。
    """
    from apscheduler.triggers.cron import CronTrigger
    from .orchestrator import get_orchestrator
    from ..core.config import get_settings
    from ..db.engine import get_async_session

    scheduler = get_scheduler()

    async def _scrape_job():
        settings = get_settings()
        orchestrator = get_orchestrator()
        async with get_async_session() as session:
            await orchestrator.run_scrape_pipeline(
                keywords=settings.keywords_list,
                city=settings.boss_search_city,
                salary_code=settings.boss_search_salary,
                session=session,
            )

    scheduler.add_job(
        _scrape_job,
        trigger=CronTrigger(hour=cron_hour, minute=cron_minute),
        id="auto_scrape",
        replace_existing=True,
    )
    logger.info("定时爬取任务已设置：每天 %02d:%02d", cron_hour, cron_minute)


def remove_auto_scrape_job() -> None:
    """切换到手动模式时移除定时爬取任务。"""
    scheduler = get_scheduler()
    if scheduler.get_job("auto_scrape"):
        scheduler.remove_job("auto_scrape")
        logger.info("定时爬取任务已移除（切换为手动模式）")


def stop_scheduler() -> None:
    """FastAPI shutdown 时调用。"""
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown()
