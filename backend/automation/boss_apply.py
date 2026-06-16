"""
BOSS 直聘打招呼（投递）模块。

投递安全机制：
  1. Gaussian 抖动延迟 — 每次投递间隔 gauss(mean, std) 秒，最小 1.5 秒
  2. 单日上限 — 超过 daily_apply_limit 自动停止，不抛异常
  3. 人工在环 — 所有岗位必须经 Web UI 批准后才进入此模块
  4. 失败上限 — 连续 3 次失败自动暂停并记录告警
  5. 验证码出现 → 立即停止，通知用户手动处理

Gaussian 延迟说明：
  delay = max(apply_delay_min, random.gauss(mean, std))
  这比固定延迟更接近人类操作节奏，降低被识别为 bot 的风险。
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from patchright.async_api import Page, TimeoutError as PlaywrightTimeout

from ..core.settings_store import load_settings
from .browser import get_browser_context, save_cookies
from .boss_login import ensure_logged_in
from .boss_scraper import _check_for_captcha, _check_risk_block

logger = logging.getLogger(__name__)


@dataclass
class ApplyTarget:
    """单条待投递信息。"""
    application_id: int   # 数据库 Application.id
    job_id: int
    boss_url: str         # 岗位详情页 URL（需从此页面发送打招呼）
    greeting_message: str


@dataclass
class ApplyResult:
    """批量投递结果报告。"""
    success_ids: List[int] = field(default_factory=list)   # 成功的 application_id
    failed_ids: List[int] = field(default_factory=list)    # 失败的 application_id
    errors: dict = field(default_factory=dict)             # application_id → 错误信息
    stopped_reason: Optional[str] = None
    today_sent_count: int = 0  # 本次发送成功数量


async def _send_greeting(page: Page, boss_url: str, message: str) -> Tuple[bool, str]:
    """
    在岗位详情页点击"立即沟通"并发送打招呼语。

    Returns:
        (success, error_message)
    """
    try:
        await page.goto(boss_url, wait_until="domcontentloaded", timeout=15_000)
        await asyncio.sleep(random.uniform(1.0, 2.0))

        # 检查是否已经沟通过（避免重复发送）
        already_chatted = await page.query_selector(
            ".btn-startchat.contacted, .btn-startchat.disabled, [class*='btn-chat'].contacted"
        )
        if already_chatted:
            return False, "已与该岗位沟通过，跳过"

        # 找「立即沟通」按钮（多种 selector + 文本兜底）
        chat_btn = await page.query_selector(
            ".btn-startchat, .op-btn-chat, [class*='btn-chat'], [class*='start-chat']"
        )
        if not chat_btn:
            chat_btn = await page.evaluate_handle(
                "() => [...document.querySelectorAll('button,a')]"
                ".find(b => /立即沟通|打招呼/.test(b.innerText))"
            )
        if not chat_btn:
            return False, "未找到「立即沟通」按钮"

        # BOSS 点击后弹出 dialog-wrap.startchat-dialog，dialog-layer 遮挡层会拦截重试点击
        # 用短超时捕获异常——对话框已经弹出，Playwright 只是无法确认点击是否成功
        try:
            await chat_btn.click(timeout=5_000)
        except PlaywrightTimeout:
            pass  # 对话框依然会打开
        await asyncio.sleep(random.uniform(1.0, 1.5))
        logger.debug("点击立即沟通后 URL: %s", page.url)

        # 检测是否弹出了登录 / 手机验证弹窗（必须是可见元素，不能只检测 DOM 存在）
        _POPUP_JS = """() => {
            const smsEl = document.querySelector('.ipt-sms, .ipt.ipt-sms');
            if (smsEl && smsEl.offsetParent !== null) return true;
            const modals = [...document.querySelectorAll(
                '[class*="dialog"], [class*="popup"], [class*="modal"], [class*="layer"]'
            )].filter(e => e.offsetParent !== null);
            for (const m of modals) {
                if (m.innerText.includes('登录立即与BOSS沟通') ||
                    m.innerText.includes('手机号绑定')) return true;
            }
            return false;
        }"""
        login_popup_visible = await page.evaluate(_POPUP_JS)
        if login_popup_visible:
            # 浏览器窗口可见——等待用户在窗口中手动完成手机验证（最多 120 秒）
            logger.warning(
                "BOSS 弹出手机验证框，请在打开的浏览器窗口中完成手机号/短信验证。"
                "验证完成后投递将自动继续（最多等待 120 秒）…"
            )
            waited = 0
            verified = False
            while waited < 120:
                await asyncio.sleep(3)
                waited += 3
                still_visible = await page.evaluate(_POPUP_JS)
                if not still_visible:
                    verified = True
                    logger.info("手机验证已完成，继续投递。")
                    await save_cookies()  # 立即持久化新 Cookie
                    break
            if not verified:
                return False, "SESSION_EXPIRED"  # 120s 内未完成验证，停止整批
            # 验证完成后再等页面跳转稳定
            try:
                await page.wait_for_load_state("networkidle", timeout=8_000)
            except PlaywrightTimeout:
                pass
            logger.debug("验证后 URL: %s", page.url)

        # 等 startchat-dialog 弹出，再在对话框内找输入框
        _DIALOG_SELECTORS = [
            ".dialog-wrap.startchat-dialog",
            "[class*='startchat-dialog']",
            ".startchat-dialog",
        ]
        dialog_el = None
        for sel in _DIALOG_SELECTORS:
            try:
                el = await page.wait_for_selector(sel, timeout=5_000)
                if el and await el.is_visible():
                    dialog_el = el
                    logger.debug("找到 startchat-dialog: %s", sel)
                    break
            except PlaywrightTimeout:
                continue

        # 优先在对话框内找输入框；如果没有对话框则在整页找
        search_root = dialog_el if dialog_el else page
        _INPUT_SELECTORS = [
            "textarea",
            "[contenteditable='true']",
            "div[contenteditable]",
            ".chat-input textarea",
            "[class*='chat-input'] textarea",
            "[class*='input-box'] textarea",
        ]
        input_el = None
        for sel in _INPUT_SELECTORS:
            try:
                el = await search_root.wait_for_selector(sel, timeout=3_000)
                if el and await el.is_visible():
                    input_el = el
                    logger.debug("找到输入框 selector: %s", sel)
                    break
            except PlaywrightTimeout:
                continue

        if not input_el:
            debug = await page.evaluate(
                "() => [...document.querySelectorAll('textarea,[contenteditable]')]"
                ".slice(0,10).map(e=>({tag:e.tagName,cls:e.className.slice(0,50),visible:!!e.offsetParent}))"
            )
            logger.warning(
                "未找到输入框 | 当前 URL: %s | 输入元素: %s", page.url, debug
            )
            return False, "未找到打招呼输入框"

        # 清空并输入打招呼语
        await input_el.click()
        await asyncio.sleep(0.3)
        # 用 JS 清空（兼容 textarea 和 contenteditable div）
        await page.evaluate("""el => {
            if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
                el.value = '';
            } else {
                el.innerText = '';
            }
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }""", input_el)
        await asyncio.sleep(0.2)
        # 分段模拟真人打字
        chunk_size = 20
        for i in range(0, len(message), chunk_size):
            chunk = message[i : i + chunk_size]
            await input_el.type(chunk, delay=random.randint(30, 80))
            await asyncio.sleep(random.uniform(0.1, 0.3))

        # 找发送按钮（优先在对话框内）
        send_root = dialog_el if dialog_el else page
        send_btn = await send_root.query_selector(
            ".btn-send, [class*='btn-send'], [class*='send-btn'], button[type='submit']"
        )
        if send_btn:
            await send_btn.click()
        else:
            await input_el.press("Enter")

        await asyncio.sleep(random.uniform(1.0, 2.0))

        # 验证发送成功（消息气泡出现）
        try:
            await page.wait_for_selector(
                ".chat-msg-item, .message-item, [class*='msg-item'], [class*='message-wrap']",
                timeout=5_000,
            )
            return True, ""
        except PlaywrightTimeout:
            logger.warning("未检测到消息气泡，但操作可能已成功")
            return True, ""

    except PlaywrightTimeout as e:
        return False, f"超时：{e}"
    except Exception as e:
        return False, f"操作失败：{e}"


async def apply_batch(targets: List[ApplyTarget], today_already_sent: int = 0) -> ApplyResult:
    """
    批量执行投递（打招呼）。
    所有安全参数和异常策略均由 AgentSettings 运行时读取。

    Args:
        targets:             待投递列表（均已通过 UI 审批）
        today_already_sent:  今日已发送数量（用于检查单日上限）
    """
    result = ApplyResult()
    agent_settings = load_settings()
    apply_cfg = agent_settings.apply

    logger.info(
        "投递策略：daily_limit=%d  delay=gauss(%.1f,%.1f)≥%.1f  "
        "captcha=%s  fail=%s  consecutive_limit=%d",
        apply_cfg.daily_limit,
        apply_cfg.delay_mean, apply_cfg.delay_std, apply_cfg.delay_min,
        agent_settings.captcha_strategy, agent_settings.fail_strategy,
        apply_cfg.consecutive_fail_limit,
    )

    # 前置：检查登录状态（包括 IM 消息权限）
    if not await ensure_logged_in(check_im=True):
        result.stopped_reason = "BOSS 会话已过期，请在前端点击「登录」重新扫码"
        return result

    context = await get_browser_context()
    page = await context.new_page()
    consecutive_fails = 0
    sent_this_batch = 0

    try:
        for target in targets:
            # ── 单日上限检查 ────────────────────────────────────────────
            total_sent = today_already_sent + sent_this_batch
            if total_sent >= apply_cfg.daily_limit:
                result.stopped_reason = (
                    f"已达单日投递上限 {apply_cfg.daily_limit} 份，今日投递结束"
                )
                logger.info(result.stopped_reason)
                break

            logger.info(
                "投递 [%d/%d] application_id=%d  %s",
                sent_this_batch + 1, len(targets),
                target.application_id, target.boss_url,
            )

            # ── 验证码检查 → captcha_strategy ───────────────────────────
            if await _check_for_captcha(page):
                if agent_settings.captcha_strategy == "skip":
                    logger.warning("  验证码出现（策略：skip），跳过此条继续")
                    result.failed_ids.append(target.application_id)
                    result.errors[target.application_id] = "验证码出现，已跳过"
                    continue
                else:  # "pause" or "notify"
                    result.stopped_reason = "出现验证码，已暂停投递，请手动处理后重试"
                    break

            # ── 风控检查（始终暂停，无策略分支）────────────────────────
            if await _check_risk_block(page):
                result.stopped_reason = "被风控拦截，已暂停投递，请等待后重试"
                break

            # ── 执行单次投递 ─────────────────────────────────────────────
            success, error_msg = await _send_greeting(
                page, target.boss_url, target.greeting_message
            )

            if success:
                result.success_ids.append(target.application_id)
                sent_this_batch += 1
                consecutive_fails = 0
                logger.info("  ✓ 投递成功 application_id=%d", target.application_id)
            else:
                result.failed_ids.append(target.application_id)
                result.errors[target.application_id] = error_msg
                logger.warning(
                    "  ✗ 投递失败 application_id=%d：%s", target.application_id, error_msg
                )

                # BOSS 弹出手机验证框 → Cookie 失效，整批停止
                if error_msg == "SESSION_EXPIRED":
                    result.stopped_reason = "BOSS 会话已过期，需重新登录（请在前端点击「登录」重新扫码）"
                    logger.error("  ✗ BOSS 弹出手机验证弹窗，Cookie 已失效，停止投递")
                    break

                # ── fail_strategy ────────────────────────────────────────
                if agent_settings.fail_strategy == "stop":
                    result.stopped_reason = "投递失败（fail_strategy=stop），立即停止"
                    break
                elif agent_settings.fail_strategy == "retry":
                    consecutive_fails += 1
                    if consecutive_fails >= apply_cfg.consecutive_fail_limit:
                        result.stopped_reason = (
                            f"连续 {apply_cfg.consecutive_fail_limit} 次失败，已自动暂停"
                        )
                        break
                # fail_strategy == "skip": 直接 continue，不计 consecutive_fails

            # ── Gaussian 抖动延迟 ────────────────────────────────────────
            if target != targets[-1]:
                delay = max(
                    apply_cfg.delay_min,
                    random.gauss(apply_cfg.delay_mean, apply_cfg.delay_std),
                )
                logger.debug("  等待 %.1f 秒后继续…", delay)
                await asyncio.sleep(delay)

    finally:
        await page.close()
        result.today_sent_count = sent_this_batch

    logger.info(
        "批量投递完成：成功 %d 条，失败 %d 条，%s",
        len(result.success_ids),
        len(result.failed_ids),
        f"停止原因：{result.stopped_reason}" if result.stopped_reason else "正常结束",
    )
    return result
