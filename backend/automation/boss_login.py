"""
BOSS 直聘扫码登录模块。

检测策略：以 session Cookie 存在为主要判断依据（最可靠）；
         二次用页面导航验证 Cookie 是否过期。
"""

import asyncio
import logging
from typing import Tuple

from patchright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeout

from .browser import get_browser_context, save_cookies

logger = logging.getLogger(__name__)

BOSS_HOME  = "https://www.zhipin.com"
BOSS_LOGIN = "https://www.zhipin.com/web/user/?ka=header-login"
_LOGIN_PATH = "/web/user"
LOGIN_TIMEOUT_SECONDS = 120

# 登录后 BOSS 会写入的 session Cookie 名称（至少一个存在即为已登录）
_SESSION_COOKIES = {"geek_zp_token", "wt2", "bst", "tc"}


def _sync_auth_state(logged_in: bool, message: str) -> None:
    """同步登录结果到 api.auth 缓存（延迟导入，避免循环依赖）。"""
    try:
        from ..api.auth import _login_status  # noqa: PLC0415
        if not _login_status.get("waiting_qr"):
            _login_status["logged_in"] = logged_in
            _login_status["message"] = message
    except Exception:
        pass


async def _has_session_cookie(context: BrowserContext) -> bool:
    """直接查 Cookie 是否含 session token，无需打开任何页面。"""
    cookies = await context.cookies()
    names = {c["name"] for c in cookies}
    found = names & _SESSION_COOKIES
    logger.debug("session cookies found: %s", found)
    return len(found) >= 1


async def check_login_status(page: Page) -> bool:
    """
    检测登录状态：
    1. 先查 session Cookie（无需导航，最快）
    2. 有 Cookie 时再导航验证是否过期
    """
    context = page.context

    if not await _has_session_cookie(context):
        logger.info("无 session Cookie，未登录")
        _sync_auth_state(False, "未登录，请点击登录")
        return False

    # Cookie 存在，验证是否仍然有效
    CHECK_URL = "https://www.zhipin.com/web/geek/jobs?query=Python&city=101280100"
    try:
        await page.goto(CHECK_URL, wait_until="domcontentloaded", timeout=15_000)
        await asyncio.sleep(1.0)

        if _LOGIN_PATH in page.url:
            logger.info("Cookie 已过期（被重定向到登录页）")
            _sync_auth_state(False, "Cookie 已过期，请重新登录")
            return False

        logger.info("登录有效（职位页可访问）")
        _sync_auth_state(True, "已登录")
        return True

    except PlaywrightTimeout:
        logger.warning("验证登录超时，Cookie 存在暂视为有效")
        _sync_auth_state(True, "已登录（网络超时，未完全验证）")
        return True


async def login() -> Tuple[bool, str]:
    """
    扫码登录流程：
    - 先检查是否已有 session Cookie（不打开页面，无闪烁）
    - 未登录则开新页跳到登录页，轮询等待 Cookie 写入
    """
    context = await get_browser_context()

    # ── 快速 Cookie 检查（不打开任何页面）─────────────────────
    if await _has_session_cookie(context):
        check_page = await context.new_page()
        try:
            already = await check_login_status(check_page)
        finally:
            await check_page.close()
        if already:
            return True, "已登录（Cookie 有效）"

    # ── 打开登录页等待扫码 ───────────────────────────────────
    page = await context.new_page()
    try:
        logger.info("打开 BOSS 直聘登录页，等待扫码…")
        await page.goto(BOSS_LOGIN, wait_until="domcontentloaded", timeout=15_000)
        await asyncio.sleep(1.0)
        logger.info("当前 URL: %s  标题: %s", page.url, await page.title())

        logger.info("请扫码登录，最多等待 %d 秒", LOGIN_TIMEOUT_SECONDS)

        # 每 3 秒检查一次 Cookie，直到 session token 出现
        for i in range(LOGIN_TIMEOUT_SECONDS // 3):
            await asyncio.sleep(3)
            if await _has_session_cookie(context):
                logger.info("检测到 session Cookie（第 %d 次轮询）", i + 1)
                break
        else:
            await page.close()
            return False, f"扫码超时（{LOGIN_TIMEOUT_SECONDS}s），请重试"

        await asyncio.sleep(1.5)
        await save_cookies()
        logger.info("Cookie 已保存，当前 URL: %s", page.url)
        await page.close()
        return True, "登录成功"

    except Exception as e:
        logger.error("登录出错：%s", e, exc_info=True)
        try:
            await page.close()
        except Exception:
            pass
        return False, f"登录出错：{e}"


async def ensure_logged_in(check_im: bool = False) -> bool:
    """
    爬虫和投递模块调用前确认 Session 有效。

    check_im=True 时额外验证 IM 消息权限（投递前调用）。
    """
    context = await get_browser_context()
    if not await _has_session_cookie(context):
        logger.warning("无 session Cookie，需要重新登录")
        _sync_auth_state(False, "未登录，请点击登录")
        return False

    page = await context.new_page()
    try:
        ok = await check_login_status(page)
        if not ok or not check_im:
            return ok

        # 额外验证消息权限：访问 IM 页，若被重定向到登录则认为 Cookie 失效
        try:
            await page.goto("https://www.zhipin.com/web/im/", wait_until="domcontentloaded", timeout=15_000)
            await asyncio.sleep(1.5)
            if "/user" in page.url or "login" in page.url.lower():
                logger.warning("IM 页被重定向，Cookie 无消息权限")
                _sync_auth_state(False, "会话已过期，请重新登录")
                return False
            logger.info("IM 页可访问，消息权限正常")
        except PlaywrightTimeout:
            logger.warning("IM 页访问超时，暂视为有权限")
        return True
    finally:
        await page.close()
