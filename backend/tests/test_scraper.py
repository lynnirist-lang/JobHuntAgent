"""
爬虫解析逻辑单元测试（Day 4）。

使用 mock HTML 测试解析函数，不需要真实浏览器。
所有测试均使用 pytest-asyncio 的异步模式。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── 测试辅助：构造 mock Page ──────────────────────────────────────

def make_mock_element(text: str = "", href: str = "") -> AsyncMock:
    """创建模拟的 Playwright Element。"""
    el = AsyncMock()
    el.inner_text = AsyncMock(return_value=text)
    el.get_attribute = AsyncMock(return_value=href)
    return el


def make_mock_page(
    cards: list | None = None,
    captcha: bool = False,
    blocked: bool = False,
    body_text: str = "",
) -> AsyncMock:
    """
    创建模拟的 Playwright Page。

    Args:
        cards:    模拟的岗位卡片列表（每个卡片是一组 selector 配置）
        captcha:  是否模拟验证码弹窗
        blocked:  是否模拟风控页面
        body_text: 模拟 body 文字内容
    """
    page = AsyncMock()
    page.url = "https://www.zhipin.com/web/geek/job?query=test"

    if blocked:
        page.url = "https://www.zhipin.com/403"
    page.inner_text = AsyncMock(return_value=body_text or "正常页面内容")

    # 模拟 query_selector：根据 selector 返回不同元素
    async def mock_query_selector(selector):
        if captcha and selector in [".boss-popup__content", "#tcaptcha_iframe", ".slider-verify"]:
            return MagicMock()  # 返回非 None 表示找到了验证码元素
        return None

    page.query_selector = AsyncMock(side_effect=mock_query_selector)
    page.query_selector_all = AsyncMock(return_value=[])
    page.wait_for_selector = AsyncMock(return_value=MagicMock())
    page.goto = AsyncMock()
    return page


# ── 测试用例 ──────────────────────────────────────────────────────

class TestCaptchaDetection:
    """测试验证码检测逻辑。"""

    @pytest.mark.asyncio
    async def test_no_captcha_returns_false(self):
        """正常页面不应触发验证码检测。"""
        from backend.automation.boss_scraper import _check_for_captcha
        page = make_mock_page(captcha=False)
        result = await _check_for_captcha(page)
        assert result is False

    @pytest.mark.asyncio
    async def test_captcha_popup_detected(self):
        """BOSS 弹窗验证码应被检测到。"""
        from backend.automation.boss_scraper import _check_for_captcha
        page = make_mock_page(captcha=True)
        result = await _check_for_captcha(page)
        assert result is True


class TestRiskBlockDetection:
    """测试风控拦截检测。"""

    @pytest.mark.asyncio
    async def test_403_url_detected(self):
        """URL 包含 403 时应标记为被拦截。"""
        from backend.automation.boss_scraper import _check_risk_block
        page = make_mock_page(blocked=True)
        result = await _check_risk_block(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_risk_keywords_detected(self):
        """body 包含风控关键词时应标记为被拦截。"""
        from backend.automation.boss_scraper import _check_risk_block
        page = make_mock_page(body_text="您的访问受限，请稍后再试")
        result = await _check_risk_block(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_normal_page_not_blocked(self):
        """正常页面不应被标记为拦截。"""
        from backend.automation.boss_scraper import _check_risk_block
        page = make_mock_page(body_text="Agent工程师 | 上海 | 15-25k")
        result = await _check_risk_block(page)
        assert result is False


class TestBuildSearchUrl:
    """测试搜索 URL 构造。"""

    def test_shanghai_city_code(self):
        """上海应映射到正确的城市代码。"""
        from backend.automation.boss_scraper import _build_search_url
        url = _build_search_url("Python开发", "上海")
        assert "101020100" in url
        assert "Python" in url

    def test_page_parameter(self):
        """翻页参数应正确编码。"""
        from backend.automation.boss_scraper import _build_search_url
        url = _build_search_url("Agent", "北京", page=3)
        assert "page=3" in url

    def test_unknown_city_defaults_to_shanghai(self):
        """未知城市默认使用上海代码。"""
        from backend.automation.boss_scraper import _build_search_url
        url = _build_search_url("测试", "火星")
        assert "101020100" in url  # 默认上海
