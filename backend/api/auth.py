"""
BOSS 直聘登录 API。

POST /auth/login   — 触发浏览器扫码登录（后台异步，轮询 status 查进度）
GET  /auth/status  — 查询登录状态
POST /auth/logout  — 清除 Cookie，强制下次重新登录
"""

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter

from ..automation.boss_login import check_login_status, login
from ..automation.browser import clear_cookies, get_browser_context, run_in_browser_loop

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["登录"])

_login_status: Dict[str, Any] = {
    "logged_in": False,
    "waiting_qr": False,
    "message": "未检测",
}


async def _run_login() -> None:
    global _login_status
    _login_status["waiting_qr"] = True
    _login_status["message"] = "请在弹出的浏览器中扫码登录…"
    _login_status["logged_in"] = False

    success, msg = await run_in_browser_loop(login())

    _login_status["waiting_qr"] = False
    _login_status["logged_in"] = success
    _login_status["message"] = msg


@router.post("/login", summary="触发扫码登录")
async def trigger_login():
    """
    在后台启动浏览器并打开 BOSS 直聘登录页。
    浏览器会弹出，用手机扫码后 Cookie 自动保存。
    通过 GET /auth/status 轮询结果。
    """
    if _login_status["waiting_qr"]:
        return {"message": "登录流程已在进行中，请扫码后等待"}

    asyncio.create_task(_run_login())
    return {"message": "浏览器已启动，请在弹出窗口中扫码登录"}


@router.get("/status", summary="查询登录状态")
async def get_login_status():
    """返回缓存的登录状态，不重复打开浏览器页面。"""
    return _login_status


async def _check_login_impl() -> bool:
    """在浏览器上下文中验证 Cookie 有效性（必须在 ProactorEventLoop 中运行）。"""
    context = await get_browser_context()
    page = await context.new_page()
    try:
        return await check_login_status(page)
    finally:
        await page.close()


@router.post("/check", summary="主动检测 Cookie 是否有效")
async def check_login():
    """打开浏览器页面实际验证 Cookie；若缓存已是登录态则直接返回。"""
    if _login_status.get("logged_in") and not _login_status.get("waiting_qr"):
        return _login_status   # 已知登录，无需再开浏览器

    try:
        logged_in = await run_in_browser_loop(_check_login_impl())
        _login_status["logged_in"] = logged_in
        _login_status["waiting_qr"] = False
        _login_status["message"] = "已登录" if logged_in else "未登录，请点击登录"
    except Exception as e:
        logger.warning("检测登录状态失败：%s", e)
        _login_status["logged_in"] = False
        _login_status["message"] = f"检测失败：{e}"
    return _login_status


@router.post("/logout", summary="清除登录 Cookie")
async def logout():
    """清除本地 Cookie，下次爬取前需重新扫码。"""
    await run_in_browser_loop(clear_cookies())
    _login_status["logged_in"] = False
    _login_status["waiting_qr"] = False
    _login_status["message"] = "已退出，请重新登录"
    return {"message": "Cookie 已清除"}
