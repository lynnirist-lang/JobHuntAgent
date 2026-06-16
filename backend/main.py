"""
FastAPI 应用入口。

挂载所有路由，配置 CORS（允许 Next.js 前端跨域请求），
注册 lifespan 事件（数据库初始化、浏览器启动/关闭）。

启动命令：
  cd /path/to/job-hunt-agent
  uvicorn backend.main:app --reload --port 8080
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

# Patchright needs ProactorEventLoop to launch subprocesses on Windows.
# run.py explicitly creates ProactorEventLoop; this fallback covers direct uvicorn CLI usage.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import apply, auth, jobs, resume, settings as settings_api
from .api import agent as agent_api
from .api import analytics as analytics_api
from .agent.scheduler import start_scheduler, stop_scheduler
from .automation.browser import close_browser
from .core.config import get_settings
from .db.engine import init_db

# 配置日志格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _warm_embedder() -> None:
    """在线程池中预热 embedding 模型，避免首次请求时阻塞事件循环。"""
    try:
        from .scoring.embedder import get_embedder
        get_embedder()
        logger.info("Embedding 模型预热完成")
    except Exception as exc:
        logger.warning("Embedding 模型预热失败（不影响启动）: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan 事件。

    启动时：初始化数据库（建表 + WAL 模式）
    关闭时：关闭 Patchright 浏览器，释放系统资源
    """
    logger.info("求职助手后端启动中…")

    # Diagnose event loop type — informational only; browser.py always uses ProactorEventLoop
    if sys.platform == "win32":
        loop = asyncio.get_running_loop()
        if isinstance(loop, asyncio.ProactorEventLoop):
            logger.info("EventLoop: ProactorEventLoop ✓")
        else:
            logger.info(
                "EventLoop: %s（浏览器自动化将使用独立 ProactorEventLoop 线程，无需手动切换）",
                type(loop).__name__,
            )

    await init_db()
    start_scheduler()
    # 在后台线程预热 embedding 模型，避免首次简历上传时阻塞事件循环
    asyncio.get_running_loop().run_in_executor(None, _warm_embedder)
    logger.info("数据库初始化完成，调度器已启动")
    yield
    # 关闭阶段
    logger.info("后端关闭，清理资源…")
    stop_scheduler()
    await close_browser()
    logger.info("资源释放完成")


def create_app() -> FastAPI:
    """工厂函数，方便测试时创建独立的 App 实例。"""
    settings = get_settings()

    app = FastAPI(
        title="求职助手 Job Hunt Agent",
        description=(
            "自动化处理 BOSS 直聘全流程：岗位爬取→AI 匹配评分→"
            "打招呼生成→人工审批→自动投递"
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────
    # 允许 Next.js 前端（localhost:3000）跨域调用 API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://localhost:{settings.frontend_port}",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 路由挂载 ──────────────────────────────────────────────
    app.include_router(auth.router)
    app.include_router(jobs.router)
    app.include_router(apply.router)
    app.include_router(resume.router)
    app.include_router(settings_api.router)
    app.include_router(agent_api.router)
    app.include_router(analytics_api.router)

    @app.get("/health", tags=["系统"])
    async def health_check():
        """健康检查接口，供前端和监控工具调用。"""
        return {"status": "ok", "service": "job-hunt-agent"}

    return app


# 创建全局 App 实例（uvicorn 直接导入）
app = create_app()
