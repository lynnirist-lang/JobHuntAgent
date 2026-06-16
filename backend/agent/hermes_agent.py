"""
Hermes 控制中枢 — agentic loop。

async generator `run(messages, session, orchestrator)` 产出文本 chunks，
由 FastAPI /agent/hermes 端点包装为 Vercel AI SDK v3 data stream 推送给前端。

流程：
  LLM（带工具）→ 有工具调用？→ 执行工具、流式推送进度 → 继续循环
                          ↓ 无
               流式推送最终文本回复
"""
import logging
from typing import AsyncGenerator, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ..core.llm import get_llm
from .tools import TOOL_DEFS, TOOL_DISPLAY_NAMES, execute_tool

logger = logging.getLogger(__name__)

_MAX_ROUNDS = 8  # 防止工具调用死循环

SYSTEM_PROMPT = """\
你是 Hermes，求职 Agent 系统的智能控制中枢。你通过调用工具直接操控整个求职流水线，\
用户只需用自然语言告诉你目标，你来负责选择和调用正确的工具。

## 岗位状态流转
PENDING（刚爬取）→ MATCHED（打招呼已生成，等用户审批）→ APPROVED（已批准）\
→ PENDING_SEND（冷却队列中）→ SENT（已发送）

## 工具调用规范
1. **查询类**（list_jobs、get_today_stats、get_settings、get_scrape_status）：直接执行，无需确认。
2. **单条操作**（approve_job、skip_job、update_greeting）：直接执行。
3. **批量操作**（batch_approve_jobs）：若用户未明确指定 job_ids，先调用 list_jobs 确认数量，\
   然后告知用户"将批准 N 个岗位"再执行。
4. **加入投递队列**（enqueue_jobs）：高风险，执行前必须先展示将被加入的岗位列表和数量，\
   明确征得用户确认后再调用。
5. **启动爬取**（start_scrape）：确认关键词和城市参数后执行，任务后台运行，立即返回。

## 回复要求
- 中文，简洁
- 工具执行后，用 1-2 句话汇报关键结果，不要重复参数细节
- 若需要多步操作，先说明计划再逐步执行
- 对话中记住用户提到的偏好（城市、薪资范围、岗位类型），后续自动带入
- **提到具体岗位时，必须在文本中注明 job_id**，格式为「职位名（ID=42）」，方便用户后续直接引用
"""


def _to_lc_messages(raw_messages: List[dict]) -> list:
    """将 Vercel AI SDK 格式的 messages 转为 LangChain message 对象列表。"""
    result = [SystemMessage(SYSTEM_PROMPT)]
    for m in raw_messages:
        role = m.get("role", "")
        content = m.get("content", "") or ""
        if role == "user":
            result.append(HumanMessage(content))
        elif role == "assistant":
            # 只保留纯文本回复；工具调用轮历史由本 session 自行管理
            if content:
                result.append(AIMessage(content))
    return result


async def run(
    messages: List[dict],
    session,
    orchestrator,
) -> AsyncGenerator[str, None]:
    """
    Hermes agentic loop，异步生成器。

    每次 yield 一个字符串 chunk，调用方负责包装成 SSE 格式推送。
    工具执行时 yield 进度文本，最后 yield LLM 的最终回复。
    """
    lc_messages = _to_lc_messages(messages)
    llm = get_llm(temperature=0.7)
    llm_with_tools = llm.bind_tools(TOOL_DEFS)

    for round_idx in range(_MAX_ROUNDS):
        logger.debug("[Hermes] round %d, messages=%d", round_idx, len(lc_messages))

        response: AIMessage = await llm_with_tools.ainvoke(lc_messages)
        lc_messages.append(response)

        # ── 无工具调用：最终回复，流式逐 token 输出 ──────────────────
        if not response.tool_calls:
            content = response.content or ""
            if content:
                # 按句子粒度流式推送，模拟打字效果
                for chunk in _split_for_streaming(content):
                    yield chunk
            return

        # ── 有工具调用：执行并推送进度 ────────────────────────────────
        for tc in response.tool_calls:
            tool_name = tc["name"]
            display = TOOL_DISPLAY_NAMES.get(tool_name, tool_name)
            yield f"正在{display}…\n"

            result_str = await execute_tool(
                tool_name,
                tc.get("args", {}),
                session,
                orchestrator,
            )
            logger.debug("[Hermes] tool=%s result=%s", tool_name, result_str[:120])
            lc_messages.append(
                ToolMessage(content=result_str, tool_call_id=tc["id"])
            )

    yield "\n⚠️ 已达到最大操作轮数，请尝试拆分为更简单的指令。"


def _split_for_streaming(text: str, chunk_size: int = 8) -> List[str]:
    """将长文本按固定字符数分块，使前端呈现渐进式打字效果。"""
    return [text[i: i + chunk_size] for i in range(0, len(text), chunk_size)]
