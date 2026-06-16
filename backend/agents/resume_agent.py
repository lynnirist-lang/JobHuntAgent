"""
ResumeAgent — 根据目标 JD 对现有简历内容进行适配改写。

三阶段流程：
  1. 结构化：keyword_scan(JD) → 对每条经历/项目评分排序
  2. 模板：筛选 top-N 最相关条目，原始内容不变
  3. AI 微调：只让 AI 改写 bullets/highlights 文字，其他字段原样返回
"""

import json
import logging
import re
from typing import AsyncIterator, Dict, List, Optional, Tuple

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from tenacity import retry, stop_after_attempt, wait_exponential

from ..core.llm import get_llm
from ..core.profile import UserProfile
from ..core.settings_store import ResumeAdaptConfig
from ..resume_parser.skills_vocab import keyword_scan

logger = logging.getLogger(__name__)


# ─────────────────────────── Phase 1 & 2: 结构化排序 ────────────────

def _score_text(text: str, jd_keywords: set) -> int:
    """统计 jd_keywords 中有多少出现在 text 中（不区分大小写）。"""
    t = text.lower()
    return sum(1 for kw in jd_keywords if kw.lower() in t)


def _rank_experiences(experiences: List[dict], jd_keywords: set) -> List[Tuple[int, dict]]:
    scored = []
    for exp in experiences:
        text = " ".join([exp.get("company", ""), exp.get("role", "")] + exp.get("bullets", []))
        scored.append((_score_text(text, jd_keywords), exp))
    return sorted(scored, key=lambda x: x[0], reverse=True)


def _rank_projects(projects: List[dict], jd_keywords: set) -> List[Tuple[int, dict]]:
    scored = []
    for proj in projects:
        text = " ".join([proj.get("name", ""), proj.get("tech", "")] + proj.get("highlights", []))
        scored.append((_score_text(text, jd_keywords), proj))
    return sorted(scored, key=lambda x: x[0], reverse=True)


def _restore_non_bullet_fields(adapted: dict, template: dict) -> dict:
    """后处理：强制将 AI 输出中的非 bullet 字段替换回原始模板值，防止 AI 篡改。"""
    exp_index = {(e["company"], e["role"]): e for e in template["experiences"]}
    proj_index = {p["name"]: p for p in template["projects"]}

    for exp in adapted.get("experiences", []):
        key = (exp.get("company", ""), exp.get("role", ""))
        # 尝试模糊匹配（AI 可能轻微改动 company/role 文字）
        orig = exp_index.get(key)
        if orig is None:
            for (c, r), o in exp_index.items():
                if c in exp.get("company", "") or exp.get("company", "") in c:
                    orig = o
                    break
        if orig:
            exp["company"] = orig["company"]
            exp["role"] = orig["role"]
            exp["duration"] = orig["duration"]

    for proj in adapted.get("projects", []):
        key = proj.get("name", "")
        orig = proj_index.get(key)
        if orig is None:
            for pname, o in proj_index.items():
                if pname in key or key in pname:
                    orig = o
                    break
        if orig:
            proj["name"] = orig["name"]
            proj["tech"] = orig["tech"]
            proj["github"] = orig["github"]

    return adapted


# ─────────────────────────── Phase 3: AI 微调 Prompt ────────────────

def _build_adapt_system(config: ResumeAdaptConfig) -> str:
    """根据 ResumeAdaptConfig 构建 system prompt。"""
    lines = [
        "你是一名专业的简历顾问。你的任务极为明确且受限：",
        "",
        "只改写 \"bullets\" 和 \"highlights\" 数组中每条文字的措辞，其他所有字段原样返回。",
        "",
        "改写规则：",
        "1. 突出 JD 关键词列表中提及的技术方向和能力，调整侧重点",
        "2. 保持 STAR 格式（情境-任务-行动-结果）",
        "3. 每条 bullet 控制在 30-60 字之间",
        "4. 禁止新增用户没有的技术栈、项目或经历内容",
        "5. \"company\"、\"role\"、\"duration\"、\"name\"、\"tech\"、\"github\" 字段必须原样返回",
    ]
    if config.avoid_words:
        lines.append(f"6. 改写时严禁出现以下词语：{', '.join(config.avoid_words)}")
    if config.extra_instruction:
        lines += ["", f"额外要求：{config.extra_instruction}"]
    lines += ["", "你的输出必须是合法的 JSON，格式与输入完全一致，不要添加任何解释文字。"]
    return "\n".join(lines)


_ADAPT_HUMAN = """\
## 目标岗位 JD
{jd_text}

## JD 核心关键词（改写时重点突出这些方向）
{jd_keywords}

## 需改写的经历/项目（只改 bullets/highlights 字段，其余原样返回）
{template_json}

只输出改写后的 JSON，不要任何前缀、说明或代码块标记。
"""


# ─────────────────────────── 旧版优化 Prompt（保留兼容性）────────

_RESUME_SYSTEM = """\
你是一名专业的简历优化顾问，擅长针对特定岗位方向重写简历内容。

优化原则：
1. 使用 STAR 法则重写每条 bullet
2. 加入该方向的核心关键词
3. 量化成果（百分比、时间、规模等）
4. 技术栈名称精确
5. 每条 bullet 控制在 30-60 字之间

只输出优化后的 Markdown 格式内容，不要解释。
"""

_RESUME_HUMAN = """\
## 目标方向
{target_role}

## 当前档案
{profile}

请按以下 Markdown 格式输出：

### 工作经历优化

**[公司名] | [职位]**
- [优化后的 bullet 1]

### 项目亮点优化

**[项目名]**
- [优化后的亮点 1]

### 推荐补充技能关键词
[针对{target_role}方向，建议补充的关键词列表]
"""


# ─────────────────────────── Agent 类 ────────────────────────────

class ResumeAgent:
    """根据 JD 对现有简历内容进行适配改写，或针对方向优化。"""

    def __init__(self) -> None:
        self._llm_streaming = get_llm(temperature=0.6, streaming=True)
        self._llm = get_llm(temperature=0.4, streaming=False)
        # adapt chain: system prompt 动态生成，使用占位变量
        self._adapt_chain = (
            ChatPromptTemplate.from_messages([
                ("system", "{system_msg}"),
                ("human",  _ADAPT_HUMAN),
            ])
            | self._llm
            | StrOutputParser()
        )
        self._optimize_prompt = ChatPromptTemplate.from_messages([
            ("system", _RESUME_SYSTEM),
            ("human", _RESUME_HUMAN),
        ])

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def adapt_to_jd(
        self,
        jd_text: str,
        profile: UserProfile,
        config: Optional[ResumeAdaptConfig] = None,
    ) -> dict:
        """
        三阶段 JD 适配：结构化评分 → 模板筛选 → AI 仅改写 bullet 文字。
        行为由 ResumeAdaptConfig 驱动（top_n / avoid_words / extra_instruction）。

        Returns:
            {"experiences": [...], "projects": [...], "jd_keywords": [...]}
        """
        config = config or ResumeAdaptConfig()

        # ── Phase 1: 结构化 — 从 JD 提取技能关键词，对经历/项目评分 ──────
        jd_keywords: set = set(keyword_scan(jd_text))

        all_exp  = [e.model_dump() for e in profile.experiences]
        all_proj = [p.model_dump() for p in profile.projects]

        ranked_exp  = _rank_experiences(all_exp,  jd_keywords)
        ranked_proj = _rank_projects(all_proj, jd_keywords)

        logger.info(
            "JD 关键词 %d 个；top_n=%d；经历得分：%s；项目得分：%s",
            len(jd_keywords), config.top_n,
            [s for s, _ in ranked_exp],
            [s for s, _ in ranked_proj],
        )

        # ── Phase 2: 模板 — 取 top-N（由 config.top_n 控制），原始内容不变 ──
        top_exp  = [exp  for _, exp  in ranked_exp[:config.top_n]]
        top_proj = [proj for _, proj in ranked_proj[:config.top_n]]

        template = {"experiences": top_exp, "projects": top_proj}

        # ── Phase 3: AI 微调 — system prompt 由 config 驱动 ──────────────
        jd_keywords_str = (
            "、".join(sorted(jd_keywords)) if jd_keywords else "（无特定技术关键词）"
        )

        raw = await self._adapt_chain.ainvoke({
            "system_msg":    _build_adapt_system(config),
            "jd_text":       jd_text[:1500],
            "jd_keywords":   jd_keywords_str,
            "template_json": json.dumps(template, ensure_ascii=False, indent=2),
        })

        result = _parse_json_response(raw)
        result = _restore_non_bullet_fields(result, template)
        result["jd_keywords"] = sorted(jd_keywords)
        return result

    async def optimize_stream(
        self, profile: UserProfile, target_role: str
    ) -> AsyncIterator[str]:
        """流式生成简历优化内容（用于 SSE 接口）。"""
        chain = self._optimize_prompt | self._llm_streaming
        async for chunk in chain.astream({
            "target_role": target_role,
            "profile": profile.to_prompt_text(),
        }):
            if hasattr(chunk, "content"):
                yield chunk.content
            elif isinstance(chunk, str):
                yield chunk

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def optimize(self, profile: UserProfile, target_role: str) -> str:
        """非流式版本，用于批处理或测试场景。"""
        chain = self._optimize_prompt | self._llm | StrOutputParser()
        result = await chain.ainvoke({
            "target_role": target_role,
            "profile": profile.to_prompt_text(),
        })
        return result.strip()


def _parse_json_response(text: str) -> dict:
    """从模型响应中提取 JSON，兼容带 ```json 代码块的情况。"""
    text = text.strip()
    # 去掉 Markdown 代码块标记
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())
