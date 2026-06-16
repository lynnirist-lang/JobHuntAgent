"""
LLM 工厂模块。

封装 langchain_openai.ChatOpenAI 的初始化细节。
支持任何兼容 OpenAI 协议的提供商（DeepSeek、Google Gemini、OpenAI 等），
通过 .env 中的 LLM_BASE_URL / LLM_MODEL / LLM_API_KEY 切换。
"""

from langchain_openai import ChatOpenAI

from .config import get_settings


def get_llm(temperature: float = 0.7, streaming: bool = False) -> ChatOpenAI:
    """
    创建并返回 LLM 实例。

    Args:
        temperature: 生成温度。打招呼生成用 0.7（创意性）。
        streaming: 是否开启流式输出（SSE 接口使用）。

    Returns:
        配置好的 ChatOpenAI 实例，指向 .env 配置的 LLM 端点。
    """
    settings = get_settings()
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=temperature,
        streaming=streaming,
        # 内置指数退避重试，覆盖网络抖动和 429 限流
        max_retries=3,
        request_timeout=60,
    )
