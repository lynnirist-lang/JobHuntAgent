"""
Patchright 浏览器上下文管理。

Patchright 是 Playwright 的 undetected 版本，在底层修补了多处 CDP 指纹特征，
可以规避 BOSS 直聘等平台的 bot 检测。

Cookie 持久化方案：
  - 登录后将 Cookie 写入本地 JSON 文件（路径在 .env 配置）
  - 每次启动时自动加载已有 Cookie，无需每次重新扫码
  - Cookie 文件加入 .gitignore，不上传到代码仓库

Windows 事件循环说明：
  Patchright 在 Windows 上需要 ProactorEventLoop 才能创建浏览器子进程。
  本模块维护一个独立的 ProactorEventLoop 线程（_proactor_loop），所有浏览器
  操作都在该线程中运行，与 uvicorn 使用的主事件循环类型无关。
"""

import asyncio
import json
import logging
import sys
import threading
from pathlib import Path
from typing import Optional

from patchright.async_api import (
    Browser,
    BrowserContext,
    Playwright,
    async_playwright,
)

from ..core.config import get_settings

logger = logging.getLogger(__name__)

# 模块级单例，避免重复启动浏览器进程
_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_context: Optional[BrowserContext] = None

# 专用于浏览器自动化的 ProactorEventLoop（仅 Windows）
_proactor_loop: Optional[asyncio.AbstractEventLoop] = None
_proactor_thread: Optional[threading.Thread] = None
_proactor_lock = threading.Lock()


def get_proactor_loop() -> asyncio.AbstractEventLoop:
    """
    获取（或创建）运行在后台线程中的持久化 ProactorEventLoop。

    Windows 上 Patchright 需要 ProactorEventLoop 才能创建浏览器子进程。
    此函数确保无论 uvicorn 主循环类型如何，浏览器操作始终在 ProactorEventLoop 中执行。
    """
    global _proactor_loop, _proactor_thread
    with _proactor_lock:
        if _proactor_thread is None or not _proactor_thread.is_alive():
            _proactor_loop = asyncio.ProactorEventLoop()
            _proactor_thread = threading.Thread(
                target=_proactor_loop.run_forever,
                daemon=True,
                name="patchright-proactor-loop",
            )
            _proactor_thread.start()
            logger.info("已启动 Patchright 专用 ProactorEventLoop 线程")
        return _proactor_loop  # type: ignore[return-value]


async def run_in_browser_loop(coro):
    """
    将浏览器协程路由到 _proactor_loop 线程执行（仅 Windows）。

    Patchright 在 Windows 上要求 ProactorEventLoop 才能 create_subprocess_exec。
    uvicorn 的主循环不保证是 ProactorEventLoop，因此所有涉及浏览器的操作
    （启动、建页、导航、投递）都必须经此函数派发到专用 ProactorEventLoop 线程。
    """
    if sys.platform != "win32":
        return await coro
    loop = get_proactor_loop()
    fut = asyncio.run_coroutine_threadsafe(coro, loop)
    return await asyncio.get_running_loop().run_in_executor(None, fut.result)


async def get_browser_context() -> BrowserContext:
    """
    获取（或复用）持久化的 Patchright BrowserContext。

    首次调用会：
      1. 启动 Patchright Playwright
      2. 启动 Chromium（非 headless，方便扫码登录）
      3. 若 Cookie 文件存在，加载到上下文
    后续调用直接返回已有 context。

    此函数必须在 ProactorEventLoop 中调用（通过 get_proactor_loop() 路由）。
    """
    global _playwright, _browser, _context

    if _context is not None:
        return _context

    settings = get_settings()
    logger.info("启动 Patchright Chromium 浏览器…")

    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(
        headless=False,  # 需要可视化界面以便用户扫码
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",  # 关键：隐藏自动化标志
        ],
    )
    _context = await _browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )

    # 加载已有 Cookie（若存在）
    cookies_path = Path(settings.boss_cookies_path)
    if cookies_path.exists():
        try:
            cookies = json.loads(cookies_path.read_text(encoding="utf-8"))
            await _context.add_cookies(cookies)
            logger.info("已从 %s 加载 %d 条 Cookie", cookies_path, len(cookies))
        except Exception as e:
            logger.warning("Cookie 加载失败（%s），将需要重新登录", e)

    return _context


async def save_cookies() -> None:
    """将当前 context 的 Cookie 持久化到本地文件。登录成功后调用。"""
    if _context is None:
        return
    settings = get_settings()
    cookies_path = Path(settings.boss_cookies_path)
    cookies_path.parent.mkdir(parents=True, exist_ok=True)
    cookies = await _context.cookies()
    cookies_path.write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Cookie 已保存至 %s（%d 条）", cookies_path, len(cookies))


async def clear_cookies() -> None:
    """清除浏览器 Cookie 并删除本地文件（用于强制重新登录）。"""
    settings = get_settings()
    cookies_path = Path(settings.boss_cookies_path)
    if _context:
        await _context.clear_cookies()
    if cookies_path.exists():
        cookies_path.unlink()
    logger.info("Cookie 已清除，请重新扫码登录")


async def close_browser() -> None:
    """关闭浏览器，释放资源。FastAPI shutdown 事件时调用。"""
    global _playwright, _browser, _context
    if not any([_context, _browser, _playwright]):
        return

    async def _impl() -> None:
        global _playwright, _browser, _context
        if _context:
            await _context.close()
            _context = None
        if _browser:
            await _browser.close()
            _browser = None
        if _playwright:
            await _playwright.stop()
            _playwright = None

    # 浏览器对象在 ProactorEventLoop 中创建，必须在同一个 loop 中关闭
    if sys.platform == "win32" and _proactor_loop is not None and not _proactor_loop.is_closed():
        fut = asyncio.run_coroutine_threadsafe(_impl(), _proactor_loop)
        await asyncio.get_running_loop().run_in_executor(None, lambda: fut.result(timeout=30))
    else:
        await _impl()

    logger.info("Patchright 浏览器已关闭")
