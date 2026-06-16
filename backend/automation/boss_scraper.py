"""
BOSS 直聘岗位爬取模块。

爬取策略：
  1. 按关键词 + 城市 + 薪资 构造搜索 URL
  2. 翻页抓取岗位列表（每页约 20 条）
  3. 进入每个岗位详情页，抓取完整 JD 文本
  4. 返回结构化数据，由调用方写入数据库

反爬降级策略（必须实现）：
  - 验证码弹出 → 暂停并通知用户手动处理
  - 403 / 风控拦截 → 停止爬取，延迟 30 分钟
  - 连续 3 次解析失败 → 停止并上报告警
  - Cookie 过期 → 停止所有操作，通知重新登录
"""

import asyncio
import logging
import random
import re
from dataclasses import dataclass, field
from typing import AsyncGenerator, List, Optional
from urllib.parse import quote, urlencode

from patchright.async_api import Page, TimeoutError as PlaywrightTimeout

from .browser import get_browser_context
from .boss_login import ensure_logged_in

logger = logging.getLogger(__name__)

# ─────────────────────────── 常量 ────────────────────────────────

BOSS_SEARCH_URL = "https://www.zhipin.com/web/geek/jobs"
MAX_PAGES = 5           # 每次搜索最多翻页数（避免过度爬取）
CONSECUTIVE_FAIL_LIMIT = 3  # 连续失败上限，超出后停止


# ─────────────────────────── 数据结构 ────────────────────────────

@dataclass
class ScrapedJob:
    """爬取到的单条岗位原始数据，尚未写库。"""
    boss_job_id: str
    title: str
    company: str
    salary: str
    location: str
    description: str
    requirements: str
    boss_url: str


@dataclass
class ScrapeResult:
    """爬取任务的最终结果报告。"""
    jobs: List[ScrapedJob] = field(default_factory=list)
    total_scraped: int = 0
    errors: List[str] = field(default_factory=list)
    stopped_reason: Optional[str] = None  # 若提前停止，记录原因


# ─────────────────────────── 工具函数 ────────────────────────────

def _clean_text(s: str) -> str:
    """Strip Private Use Area codepoints (icon-font chars) and normalize whitespace."""
    cleaned = "".join(ch for ch in s if not (0xE000 <= ord(ch) <= 0xF8FF))
    return re.sub(r"\s+", " ", cleaned).strip()


# ─────────────────────────── 核心函数 ────────────────────────────

def _build_search_url(keyword: str, city: str, salary_code: str = "", page: int = 1) -> str:
    """
    构造 BOSS 直聘搜索 URL。

    city 传入城市名（如"上海"），函数内映射到城市代码。
    salary_code 对应薪资区间下拉框的 value（空字符串表示不限）。
    """
    city_codes = {
        "上海": "101020100", "北京": "101010100", "深圳": "101280600",
        "广州": "101280100", "杭州": "101210100", "成都": "101270100",
        "武汉": "101200100", "南京": "101190100", "远程": "100010000",
        "西安": "101110100", "苏州": "101190400", "合肥": "101220100",
        "重庆": "101040100", "厦门": "101230200", "天津": "101030100",
        "郑州": "101180100", "长沙": "101250100", "福州": "101230100",
        "济南": "101120100", "青岛": "101120200", "宁波": "101210400",
        "无锡": "101190200", "沈阳": "101070100", "东莞": "101281600",
        "佛山": "101280800", "珠海": "101280700", "南昌": "101240100",
        "昆明": "101290100", "贵阳": "101260100", "哈尔滨": "101050100",
        "长春": "101060100", "大连": "101070200", "南宁": "101300100",
        "海口": "101310100", "石家庄": "101090100", "太原": "101100100",
        "呼和浩特": "101080100", "乌鲁木齐": "101130100", "兰州": "101160100",
    }
    # 精确匹配，再去掉"市"后缀二次查找，最后前缀模糊匹配
    city_clean = city.replace("市", "").strip()
    city_code = (
        city_codes.get(city)
        or city_codes.get(city_clean)
        or next((v for k, v in city_codes.items() if city_clean in k or k in city_clean), None)
        or "101020100"  # 兜底上海
    )
    if city_code == "101020100" and city_clean not in ("上海", ""):
        logger.warning("未找到城市 [%s] 的代码，已回退到上海", city)

    params = {
        "query": keyword,
        "city": city_code,
        "page": page,
    }
    if salary_code:
        params["salary"] = salary_code

    return f"{BOSS_SEARCH_URL}?{urlencode(params)}"


async def _check_for_captcha(page: Page) -> bool:
    """检测页面是否出现验证码弹窗（滑块或图形验证码）。"""
    captcha_selectors = [
        ".boss-popup__content",   # BOSS 弹窗
        "#tcaptcha_iframe",        # 腾讯验证码 iframe
        ".slider-verify",          # 滑块验证
    ]
    for selector in captcha_selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                logger.warning("检测到验证码弹窗：%s", selector)
                return True
        except Exception:
            pass
    return False


async def _check_risk_block(page: Page) -> bool:
    """检测是否被风控拦截（403 页面或风控提示文字）。"""
    url = page.url
    if "403" in url or "blocked" in url.lower():
        return True
    try:
        body_text = await page.inner_text("body")
        risk_keywords = ["访问受限", "请求频繁", "验证您的身份", "系统繁忙"]
        return any(kw in body_text for kw in risk_keywords)
    except Exception:
        return False


async def _parse_job_list_page(page: Page) -> List[dict]:
    """
    解析搜索结果列表页，提取岗位的基本信息。

    Returns:
        list of dict with keys: boss_job_id, title, company, salary, location, url
    """
    jobs = []
    try:
        # BOSS 使用懒加载，稍等后再检测卡片
        await asyncio.sleep(2)
        await page.wait_for_selector(".job-card-wrap", timeout=15_000)
        cards = await page.query_selector_all(".job-card-wrap")

        for card in cards:
            try:
                # 用 JS 一次性提取所有字段，避免多次 Python async await 开销
                data = await card.evaluate("""card => {
                    // ── 链接 & 标题 ──────────────────────────────
                    const nameEl = card.querySelector('a.job-name') ||
                                   card.querySelector('.job-name a') ||
                                   card.querySelector('.job-name');
                    const href = nameEl ? (nameEl.getAttribute('href') || '') : '';

                    // 标题：取直接文本节点，排除薪资子元素
                    let title = '';
                    if (nameEl) {
                        const direct = [...nameEl.childNodes]
                            .filter(n => n.nodeType === 3)
                            .map(n => n.textContent.trim())
                            .filter(Boolean)
                            .join('');
                        title = direct || nameEl.innerText.replace(/\\d+[-–]\\d+[Kk].*/, '').trim();
                    }

                    // ── 薪资（多层兜底）────────────────────────
                    const salaryEl =
                        card.querySelector('span.salary') ||
                        card.querySelector('.job-salary') ||
                        card.querySelector('.salary') ||
                        card.querySelector('[class*="salary"]') ||
                        card.querySelector('.job-name span') ||
                        card.querySelector('.job-name em');
                    const salary = salaryEl ? salaryEl.innerText.trim() : '';

                    // ── 公司 & 城市 ──────────────────────────────
                    const footerEl = card.querySelector('.job-card-footer') ||
                                     card.querySelector('.company-info') ||
                                     card.querySelector('.info-company');
                    const companyEl = card.querySelector('.company-name') ||
                                      card.querySelector('[class*="company"]');
                    const locationEl = card.querySelector('.job-area') ||
                                       card.querySelector('.location') ||
                                       card.querySelector('[class*="location"]') ||
                                       card.querySelector('[class*="area"]');

                    let company = '', location = '';
                    if (companyEl) {
                        company = companyEl.innerText.trim();
                    } else if (footerEl) {
                        const lines = footerEl.innerText.trim().split('\\n').map(s => s.trim()).filter(Boolean);
                        company = lines[0] || '';
                    }
                    if (locationEl) {
                        location = locationEl.innerText.trim();
                    } else if (footerEl && !company) {
                        const lines = footerEl.innerText.trim().split('\\n').map(s => s.trim()).filter(Boolean);
                        location = lines[1] || '';
                    }

                    return { title, salary, href, company, location };
                }""")

                href = data.get("href", "")
                if not href:
                    continue

                # boss_job_id 在 URL path 中，格式：/job_detail/xxxxx.html
                boss_job_id = href.split("/")[-1].replace(".html", "").split("?")[0]
                if not boss_job_id:
                    continue

                full_url = f"https://www.zhipin.com{href}" if href.startswith("/") else href

                jobs.append({
                    "boss_job_id": boss_job_id,
                    "title":    _clean_text(data.get("title",    "")),
                    "company":  _clean_text(data.get("company",  "")),
                    "salary":   _clean_text(data.get("salary",   "")),
                    "location": _clean_text(data.get("location", "")),
                    "url": full_url,
                })
            except Exception as e:
                logger.debug("解析单个岗位卡片失败：%s", e)
                continue

    except PlaywrightTimeout:
        logger.warning("岗位列表加载超时（页面可能为空或网络异常）")

    return jobs


async def _parse_job_detail(page: Page, url: str) -> tuple[str, str]:
    """
    进入岗位详情页，抓取完整 JD 文本。

    Returns:
        (description, requirements) — 职位描述和要求
    """
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20_000)

        # 等待正文内容渲染完成（任一 selector 出现即止）
        try:
            await page.wait_for_selector(
                ".job-sec-text, .job-detail-body, .job-detail, [class*='job-sec']",
                timeout=8_000,
            )
        except PlaywrightTimeout:
            pass

        await asyncio.sleep(random.uniform(0.8, 1.5))

        # 用 JS 一次性提取，避免多次 async 往返
        result = await page.evaluate("""() => {
            // 尝试找到所有 .job-sec-text（BOSS 当前主流结构）
            const secTexts = [...document.querySelectorAll('.job-sec-text')];
            if (secTexts.length) {
                const combined = secTexts.map(e => e.innerText.trim()).filter(Boolean).join('\\n\\n');
                if (combined.length > 20) return { desc: combined, reqs: '' };
            }

            // 常见备用 selector 列表
            const candidates = [
                '.job-detail-body',
                '.job-description__text',
                '.job-description',
                '.text-desc',
                '.desc',
                '[class*="detail-body"]',
                '[class*="job-desc"]',
            ];
            for (const sel of candidates) {
                const el = document.querySelector(sel);
                if (el) {
                    const t = el.innerText.trim();
                    if (t.length > 20) return { desc: t, reqs: '' };
                }
            }

            // 兜底：把所有包含 job-sec 字样的元素文本合并
            const fallback = [...document.querySelectorAll('[class*="job-sec"]')]
                .map(e => e.innerText.trim()).filter(t => t.length > 10).join('\\n\\n');
            if (fallback.length > 20) return { desc: fallback, reqs: '' };

            // 最后：记录页面实际存在的 class，便于调试
            const classes = [...document.querySelectorAll('[class]')]
                .map(e => e.className).filter(c => c && /job|desc|detail/.test(c)).slice(0, 30);
            return { desc: '', reqs: '', debug_classes: classes };
        }""")

        description  = _clean_text(result.get("desc",  ""))
        requirements = _clean_text(result.get("reqs",  ""))

        if not description:
            debug = result.get("debug_classes", [])
            logger.warning("详情页未找到描述，页面相关 class：%s | url=%s", debug, url)

        # 若 requirements 为空，把描述后半段拆出来
        if not requirements and description:
            lines = [l for l in description.split("\n") if l.strip()]
            mid = len(lines) // 2
            if mid > 0:
                requirements = "\n".join(lines[mid:]).strip()
                description  = "\n".join(lines[:mid]).strip()

        return description, requirements

    except PlaywrightTimeout:
        logger.warning("岗位详情页加载超时：%s", url)
        return "", ""
    except Exception as e:
        logger.error("解析详情页失败 (%s): %s", url, e)
        return "", ""


async def scrape_jobs(
    keyword: str,
    city: str,
    salary_code: str = "",
    max_pages: int = MAX_PAGES,
) -> ScrapeResult:
    """
    执行单个关键词的完整爬取任务。

    Args:
        keyword:    搜索关键词（如"Agent工程师"）
        city:       城市名称（如"上海"）
        salary_code: 薪资区间代码（空表示不限）
        max_pages:  最多翻页数

    Returns:
        ScrapeResult 包含所有爬取到的岗位和错误信息
    """
    result = ScrapeResult()

    # 检查登录状态
    if not await ensure_logged_in():
        result.stopped_reason = "Cookie 已失效，请重新扫码登录"
        logger.error(result.stopped_reason)
        return result

    context = await get_browser_context()
    page = await context.new_page()
    consecutive_fails = 0

    try:
        for page_num in range(1, max_pages + 1):
            url = _build_search_url(keyword, city, salary_code, page_num)
            logger.info("[%s] 正在爬取第 %d 页: %s", keyword, page_num, url)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            except PlaywrightTimeout:
                logger.warning("列表页加载超时，跳过第 %d 页", page_num)
                result.errors.append(f"第{page_num}页列表加载超时")
                consecutive_fails += 1
                if consecutive_fails >= CONSECUTIVE_FAIL_LIMIT:
                    result.stopped_reason = f"连续 {CONSECUTIVE_FAIL_LIMIT} 次操作失败，已暂停"
                    break
                continue

            # 反爬检测
            if await _check_for_captcha(page):
                result.stopped_reason = "出现验证码，请在浏览器手动处理后重试"
                break
            if await _check_risk_block(page):
                result.stopped_reason = "被风控拦截，请等待 30 分钟后重试"
                break

            # 解析列表页
            job_basics = await _parse_job_list_page(page)
            if not job_basics:
                logger.info("第 %d 页无更多岗位，停止翻页", page_num)
                break

            consecutive_fails = 0  # 列表页成功则重置失败计数

            # 逐条进入详情页
            for job_basic in job_basics:
                try:
                    desc, reqs = await _parse_job_detail(page, job_basic["url"])
                    result.jobs.append(ScrapedJob(
                        boss_job_id=job_basic["boss_job_id"],
                        title=job_basic["title"],
                        company=job_basic["company"],
                        salary=job_basic["salary"],
                        location=job_basic["location"],
                        description=desc,
                        requirements=reqs,
                        boss_url=job_basic["url"],
                    ))
                    result.total_scraped += 1

                    # 随机延迟，模拟正常浏览节奏
                    delay = max(1.0, random.uniform(1.5, 3.5))
                    await asyncio.sleep(delay)

                    # 每次详情页也检查一次验证码
                    if await _check_for_captcha(page):
                        result.stopped_reason = "详情页出现验证码，请手动处理后重试"
                        return result

                except Exception as e:
                    logger.warning("处理岗位 %s 失败：%s，已跳过", job_basic.get("boss_job_id"), e)
                    result.errors.append(f"岗位 {job_basic.get('title')} 解析失败：{e}")
                    consecutive_fails += 1
                    if consecutive_fails >= CONSECUTIVE_FAIL_LIMIT:
                        result.stopped_reason = f"连续 {CONSECUTIVE_FAIL_LIMIT} 次岗位解析失败，已暂停"
                        return result

            # 列表页成功处理后，翻页前加延迟
            await asyncio.sleep(random.uniform(2.0, 4.0))

    finally:
        await page.close()

    logger.info(
        "[%s] 爬取完成：共 %d 条，错误 %d 条，%s",
        keyword,
        result.total_scraped,
        len(result.errors),
        f"停止原因：{result.stopped_reason}" if result.stopped_reason else "正常结束",
    )
    return result
