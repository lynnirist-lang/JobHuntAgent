"""
数据库引擎初始化。

使用 SQLModel + aiosqlite 提供异步 SQLite 访问。
WAL 模式通过 connect_args 事件在连接创建时启用，
支持 FastAPI 异步 API 读取与后台爬虫并发写入。
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from ..core.config import get_settings

logger = logging.getLogger(__name__)

_engine = None


def get_engine():
    """获取（或创建）全局异步引擎，使用 lru_cache 语义。"""
    global _engine
    if _engine is None:
        settings = get_settings()

        # 确保 data/ 目录存在
        db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        _engine = create_async_engine(
            settings.database_url,
            echo=False,               # 生产环境关闭 SQL 日志
            connect_args={"check_same_thread": False},
        )
        logger.info("数据库引擎已初始化：%s", settings.database_url)
    return _engine


async def init_db() -> None:
    """
    创建所有表并启用 WAL 模式。

    FastAPI 启动时调用（lifespan 事件）。
    WAL（Write-Ahead Logging）允许读写并发，避免爬虫写入时 API 读取被阻塞。
    """
    engine = get_engine()
    async with engine.begin() as conn:
        # 创建所有 SQLModel 表（已存在则跳过）
        await conn.run_sync(SQLModel.metadata.create_all)
        # 启用 WAL 模式
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))  # WAL 下可降级为 NORMAL
        # 补齐模型新增但数据库缺失的列（SQLite 不支持自动迁移）
        await conn.run_sync(_add_missing_columns)
    logger.info("数据库表已初始化，WAL 模式已启用")


def _add_missing_columns(conn) -> None:
    """对比 SQLModel metadata 与实际表结构，用 ALTER TABLE 补齐缺失列。"""
    from sqlalchemy import inspect
    inspector = inspect(conn)
    for table in SQLModel.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name not in existing:
                col_type = col.type.compile(conn.dialect)
                nullable = "NULL" if col.nullable else "NOT NULL"
                default = f" DEFAULT {col.default.arg!r}" if col.default is not None else ""
                conn.execute(text(
                    f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}{default} {nullable}"
                ))
                logger.info("数据库迁移：%s.%s 列已添加", table.name, col.name)


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    异步 Session 上下文管理器。

    FastAPI 依赖注入（deps.get_session）使用此函数。
    自动处理 commit / rollback / close。
    """
    engine = get_engine()
    # 使用 SQLAlchemy 异步 sessionmaker（SQLModel 兼容）
    async_session_factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
