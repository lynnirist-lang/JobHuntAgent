"""
MessageAgent — 生成个性化打招呼语。

三阶段流程：
  1. 结构化评分：keyword_scan(JD) → 提取关键词注入 prompt
  2. 模板筛选：用 embedding 余弦相似度对经历/项目排序，按 GreetingConfig 维度筛选
  3. AI 生成：system prompt 由 GreetingConfig 驱动（语气/字数/额外要求）

GreetingConfig 中的每个字段都实际影响生成行为：
  tone              → system prompt "语气风格：{tone}"
  word_count        → prompt 目标字数 + system prompt 字数要求
  include_*         → 控制档案摘要包含哪些维度
  extra_instruction → 追加到 system prompt
  suffix            → 追加到最终生成文字之后
"""

import asyncio
import json
import logging
from typing import Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from tenacity import retry, stop_after_attempt, wait_exponential

from ..core.llm import get_llm
from ..core.profile import UserProfile
from ..core.settings_store import GreetingConfig
from ..resume_parser.skills_vocab import keyword_scan
from ..scoring import embedder as _embedder

logger = logging.getLogger(__name__)

_TOP_N = 2  # 打招呼字数有限，top-2 经历/项目足够


# ─────────────────────────── Phase 2: 语义排序 ───────────────────────

async def _build_excerpt(profile: UserProfile, jd_text: str, config: GreetingConfig) -> str:
    """
    构建按 JD 语义相似度排序的精简档案摘要。
    用 embedding 余弦相似度替代关键词计数，捕获同义表达（如"MLE"↔"机器学习工程师"）。
    include_* 开关控制每个维度是否出现。
    """
    excerpt: dict = {
        "basic": {
            "school":    profile.basic.school,
            "grad_year": profile.basic.grad_year,
        }
    }

    # 需要编码的文本列表：[jd, exp0, exp1, ..., proj0, proj1, ...]
    texts_to_encode: list[str] = [jd_text[:2000]]
    exp_dicts: list[dict] = []
    proj_dicts: list[dict] = []

    if config.include_experience and profile.experiences:
        exp_dicts = [e.model_dump() for e in profile.experiences]
        for e in exp_dicts:
            texts_to_encode.append(
                " ".join([e.get("company", ""), e.get("role", "")] + e.get("bullets", []))
            )

    if config.include_project and profile.projects:
        proj_dicts = [p.model_dump() for p in profile.projects]
        for p in proj_dicts:
            texts_to_encode.append(
                " ".join([p.get("name", ""), p.get("tech", "")] + p.get("highlights", []))
            )

    # 一次批量编码，在线程池中运行避免阻塞事件循环
    if len(texts_to_encode) > 1:
        vecs = await asyncio.to_thread(_embedder.encode, texts_to_encode)
        jd_vec = vecs[0]
        idx = 1

        if exp_dicts:
            exp_sims = [
                _embedder.cosine_similarity(jd_vec, vecs[idx + i])
                for i in range(len(exp_dicts))
            ]
            idx += len(exp_dicts)
            ranked_exp = [e for _, e in sorted(zip(exp_sims, exp_dicts), key=lambda x: x[0], reverse=True)]
            excerpt["top_experiences"] = ranked_exp[:_TOP_N]
            logger.debug("经历语义相似度: %s", [f"{s:.3f}" for s in sorted(exp_sims, reverse=True)])

        if proj_dicts:
            proj_sims = [
                _embedder.cosine_similarity(jd_vec, vecs[idx + i])
                for i in range(len(proj_dicts))
            ]
            ranked_proj = [p for _, p in sorted(zip(proj_sims, proj_dicts), key=lambda x: x[0], reverse=True)]
            excerpt["top_projects"] = ranked_proj[:_TOP_N]
            logger.debug("项目语义相似度: %s", [f"{s:.3f}" for s in sorted(proj_sims, reverse=True)])

    if config.include_skills and profile.skills:
        excerpt["skills"] = profile.skills[:20]

    return json.dumps(excerpt, ensure_ascii=False, indent=2)


# ─────────────────────────── Phase 3: 动态 Prompt 构建 ───────────────

def _build_system_prompt(config: GreetingConfig) -> str:
    low  = max(80,  config.word_count - 15)
    high = min(200, config.word_count + 15)
    lines = [
        "你是一名求职者，正在 BOSS 直聘上向 HR 发送打招呼消息。",
        "",
        "要求：",
        f"1. 字数严格控制在 {low}-{high} 字之间",
        f"2. 语气风格：{config.tone}，措辞要礼貌、真诚，给 HR 良好的第一印象",
        "3. 开头可以简短问候（如「您好」），紧接着说明应聘岗位和自己的核心优势，避免千篇一律的自我介绍套话",
        "4. 正文从已提供的经历中提炼 1-2 个与岗位最相关的具体点，优先体现 JD 关键词中的技术方向",
        "5. 结尾表达期待进一步沟通的意愿，语气真诚自然（例如「期待有机会与您交流」），不要机械重复",
        "6. 不提薪资期望，不提学校背景",
        "7. 整体读起来像真人写的，不像模板，不像 AI",
    ]
    if config.extra_instruction:
        lines += ["", f"额外要求：{config.extra_instruction}"]
    lines += ["", "只输出打招呼正文，不要任何前缀、解释或引号。"]
    return "\n".join(lines)


_MESSAGE_HUMAN = """\
## 目标岗位（JD 摘要）
{jd_summary}

## JD 核心关键词（生成时重点体现）
{jd_keywords}

## 候选人最相关经历（已按匹配度预筛选）
{profile_excerpt}

请生成一条约 {word_count} 字的打招呼消息。
"""


# ─────────────────────────── Agent 类 ────────────────────────────────

class MessageAgent:
    """策略驱动的个性化打招呼语生成器。所有行为由 GreetingConfig 控制。"""

    def __init__(self) -> None:
        self._llm = get_llm(temperature=0.75)
        # system prompt 是动态的，使用占位变量；chain 在 __init__ 中构建一次
        self._chain = (
            ChatPromptTemplate.from_messages([
                ("system", "{system_msg}"),
                ("human",  _MESSAGE_HUMAN),
            ])
            | self._llm
            | StrOutputParser()
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def generate(
        self,
        jd_text: str,
        profile: UserProfile,
        match_reason: str = "",
        config: Optional[GreetingConfig] = None,
    ) -> str:
        """
        三阶段生成打招呼语，行为完全由 config 驱动。

        Args:
            jd_text:      JD 全文
            profile:      用户档案
            match_reason: 评分阶段产出的匹配理由（可选引导方向）
            config:       打招呼策略配置；None 时使用全默认值

        Returns:
            打招呼正文字符串（已应用 suffix）
        """
        config = config or GreetingConfig()

        # Phase 1: 从 JD 提取技能关键词（注入 prompt，不再用于排序）
        jd_keywords = keyword_scan(jd_text)
        jd_keywords_str = (
            "、".join(sorted(jd_keywords)) if jd_keywords else "（无特定技术关键词）"
        )
        logger.debug("JD 关键词 %d 个", len(jd_keywords))

        # Phase 2: 用 embedding 相似度排序，构建精简档案摘要
        profile_excerpt = await _build_excerpt(profile, jd_text, config)

        # JD 摘要（可附加 match_reason 引导方向）
        jd_summary = jd_text[:1500]
        if match_reason:
            jd_summary += f"\n\n[关键契合点参考：{match_reason}]"

        # Phase 3: AI 生成（system prompt 由 config 动态构建）
        message = await self._chain.ainvoke({
            "system_msg":      _build_system_prompt(config),
            "jd_summary":      jd_summary,
            "jd_keywords":     jd_keywords_str,
            "profile_excerpt": profile_excerpt,
            "word_count":      str(config.word_count),
        })
        message = message.strip().strip('"').strip("'")

        if config.suffix:
            message = message + config.suffix

        logger.debug("打招呼语生成完成，字数：%d", len(message))
        return message
