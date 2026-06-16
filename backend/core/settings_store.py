"""
策略配置持久化（agent_settings.json）。

AgentSettings 是运行时可热更新的策略控制层：
  score        → ScoreJobsSkill 评分阈值
  apply        → boss_apply 投递延迟与安全限制
  greeting     → MessageAgent 打招呼生成行为
  resume_adapt → ResumeAgent JD 适配行为
  顶层字段      → 编排器冷却时间、爬取页数、定时模式等
"""

import json
import logging
from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_SETTINGS_PATH = Path("agent_settings.json")


# ─────────────────────────── 子策略模型 ──────────────────────────────

class ScoreConfig(BaseModel):
    """岗位评分分段阈值。"""
    skip_threshold: int = 30       # < 此分：自动跳过
    eligible_threshold: int = 50   # >= 此分：生成打招呼
    high_threshold: int = 75       # >= 此分：高优先（预留）
    skill_gate: int = 40           # 技能分低于此值强制 LOW_PRIORITY，防止城市/经验撑分


class ApplyConfig(BaseModel):
    """投递行为安全参数。"""
    daily_limit: int = 30
    delay_mean: float = 4.0        # Gaussian 延迟均值（秒）
    delay_std: float = 1.5
    delay_min: float = 1.5         # 最小延迟下限
    consecutive_fail_limit: int = 3  # fail_strategy=retry 时的连续失败上限


class GreetingConfig(BaseModel):
    """打招呼语生成行为。"""
    tone: str = "专业"               # 语气风格，注入 system prompt
    word_count: int = 120            # 目标字数
    suffix: str = ""                 # 固定结尾追加文字（留空则不追加）
    extra_instruction: str = ""      # 追加到 system prompt 的额外要求
    include_skills: bool = True      # 档案摘要是否包含技能列表
    include_experience: bool = True  # 档案摘要是否包含工作经历
    include_project: bool = False    # 档案摘要是否包含项目经历
    concurrency: int = 8             # 批量并发上限
    timeout: int = 45                # 单任务超时秒数


class ResumeAdaptConfig(BaseModel):
    """JD 简历适配行为。"""
    top_n: int = 3
    avoid_words: List[str] = Field(default_factory=list)
    extra_instruction: str = ""
    highlight_keywords: bool = True   # 改写时突出 JD 关键词
    adapt_tone: bool = True           # 调整措辞风格贴合岗位


class SearchConfig(BaseModel):
    """搜索参数持久化（dashboard 搜索设置）。"""
    keywords: List[str] = Field(default_factory=lambda: ["Agent工程师", "AI全栈", "Python后端"])
    city: str = "上海"
    salary_code: str = ""


# ─────────────────────────── 顶层策略模型 ────────────────────────────

class AgentSettings(BaseModel):
    # 运行模式
    mode: Literal["scheduled", "manual"] = "scheduled"
    start_time: str = "09:00"
    end_time: str = "22:00"
    auto_interval_minutes: int = 60

    # 流水线参数
    max_pages: int = 3              # 单次爬取最大页数
    cooldown_minutes: int = 30      # 审批通过 → 实际投递的冷却时间

    # 异常处理策略
    captcha_strategy: Literal["pause", "skip", "notify"] = "pause"
    # pause: 遇验证码立即停止整批；skip: 跳过该条继续；notify: 同 pause（预留通知扩展）
    fail_strategy: Literal["retry", "skip", "stop"] = "retry"
    # retry: 连续失败达上限后停止；skip: 失败直接跳过不计数；stop: 任意失败立即停止

    # 子策略
    score: ScoreConfig = Field(default_factory=ScoreConfig)
    apply: ApplyConfig = Field(default_factory=ApplyConfig)
    greeting: GreetingConfig = Field(default_factory=GreetingConfig)
    resume_adapt: ResumeAdaptConfig = Field(default_factory=ResumeAdaptConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)


# ─────────────────────────── 读写工具 ────────────────────────────────

def load_settings() -> AgentSettings:
    """从 agent_settings.json 加载策略配置，文件不存在时返回全默认值。"""
    if not _SETTINGS_PATH.exists():
        return AgentSettings()
    with _SETTINGS_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return AgentSettings.model_validate(data)


def save_settings(settings: AgentSettings) -> None:
    """将策略配置写回 agent_settings.json。"""
    with _SETTINGS_PATH.open("w", encoding="utf-8") as f:
        json.dump(settings.model_dump(), f, indent=2, ensure_ascii=False)
    logger.info("策略配置已保存至 %s", _SETTINGS_PATH)
