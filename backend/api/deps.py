"""
FastAPI 依赖注入工具。

get_session：提供异步 SQLModel Session，请求结束后自动提交/回滚。
"""

from typing import AsyncGenerator

from sqlmodel.ext.asyncio.session import AsyncSession

from ..db.engine import get_async_session


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：为每个请求提供独立的数据库 Session。"""
    async with get_async_session() as session:
        yield session
