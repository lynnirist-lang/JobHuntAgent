"""
应用全局配置。

所有配置项通过环境变量或 .env 文件注入，Pydantic Settings 自动读取并校验。
敏感字段（API Key、Cookie 路径）均从环境变量加载，不写死在代码里。
"""

from functools import lru_cache
from typing import List

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局设置类，字段名与 .env 中的键名一一对应（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # 忽略 .env 中多余的键
    )

    # ── LLM API（兼容 OpenAI 协议的任意提供商）───────────────
    # 支持新名称 LLM_* 和旧名称 DEEPSEEK_*，优先读新名称
    llm_api_key: str = Field(
        validation_alias=AliasChoices("llm_api_key", "deepseek_api_key")
    )
    llm_model: str = Field(
        default="gemini-2.0-flash",
        validation_alias=AliasChoices("llm_model", "deepseek_model"),
    )
    llm_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
        validation_alias=AliasChoices("llm_base_url", "deepseek_base_url"),
    )

    # ── 数据库 ────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./data/jobs.db"

    # ── BOSS 直聘 Cookie 持久化 ───────────────────────────────
    boss_cookies_path: str = "./data/boss_cookies.json"

    # ── 搜索参数 ──────────────────────────────────────────────
    boss_search_keywords: str = "Agent工程师,AI全栈,Python后端"
    boss_search_city: str = "上海"
    boss_search_salary: str = "15-25k"

    # ── 投递安全限制 ──────────────────────────────────────────
    daily_apply_limit: int = 30       # 单日投递上限
    apply_delay_mean: float = 4.0     # Gaussian 延迟均值（秒）
    apply_delay_std: float = 1.5      # Gaussian 延迟标准差
    apply_delay_min: float = 1.5      # 最小延迟下限，防止抖动为负

    # ── AI 评分阈值 ───────────────────────────────────────────
    # 兼容旧配置，不再主动使用
    low_priority_threshold: int = 40
    # 新评分阈值（由 ScoreJobsSkill 使用）
    score_eligible_threshold: int = 50   # >= 50：生成打招呼
    score_high_threshold: int = 75       # >= 75：高优先级（预留）
    score_skip_threshold: int = 30       # < 30：自动跳过

    # ── Embedding 模型 ────────────────────────────────────────
    scoring_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # ── 服务端口 ──────────────────────────────────────────────
    backend_port: int = 8080
    frontend_port: int = 3001

    @property
    def keywords_list(self) -> List[str]:
        """将逗号分隔的关键词字符串转为列表。"""
        return [k.strip() for k in self.boss_search_keywords.split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    """单例模式获取配置，避免重复读取 .env 文件。"""
    return Settings()
