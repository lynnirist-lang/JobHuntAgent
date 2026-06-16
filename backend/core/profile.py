"""
用户档案（UserProfile）数据模型与读写工具。

UserProfile 存储在 user_profile.json（.gitignore），不进数据库。
该文件是 AI Agent 的核心输入，所有匹配评分和打招呼生成都依赖它。
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# user_profile.json 默认路径（相对于项目根目录运行时）
_PROFILE_PATH = Path("user_profile.json")
_EXAMPLE_PATH = Path("user_profile.example.json")


# ─────────────────────────── 数据模型 ────────────────────────────

class BasicInfo(BaseModel):
    """基本个人信息。"""
    name: str = ""
    school: str = ""
    major: str = ""
    grad_year: int = 2026
    phone: str = ""
    email: str = ""
    city: str = ""


class Experience(BaseModel):
    """一段工作/实习经历。"""
    company: str
    role: str
    duration: str                 # 例："2025.09-2026.06"
    bullets: List[str] = Field(default_factory=list)


class Project(BaseModel):
    """一个项目经历。"""
    name: str
    tech: str                     # 技术栈描述
    highlights: List[str] = Field(default_factory=list)
    github: str = ""


class Target(BaseModel):
    """求职目标配置。"""
    roles: List[str] = Field(default_factory=list)
    cities: List[str] = Field(default_factory=list)
    salary: str = ""
    major: str = ""


class UserProfile(BaseModel):
    """
    完整用户档案。

    会被序列化后注入到 LLM Prompt 中，因此字段命名要清晰可读。
    """
    basic: BasicInfo = Field(default_factory=BasicInfo)
    experiences: List[Experience] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    target: Target = Field(default_factory=Target)

    def to_prompt_text(self) -> str:
        """将档案序列化为格式化 JSON 字符串，用于注入 Prompt。"""
        return self.model_dump_json(indent=2, exclude_none=True)


# ─────────────────────────── 读写工具 ────────────────────────────

def load_profile(path: Optional[Path] = None) -> UserProfile:
    """
    从 JSON 文件加载用户档案。

    优先读取 user_profile.json；若不存在则回退到 example 文件（只读演示）。
    """
    target = path or _PROFILE_PATH
    if not target.exists() or target.stat().st_size == 0:
        logger.warning("user_profile.json 不存在或为空，回退到 example 模板（只读）")
        target = _EXAMPLE_PATH
    if not target.exists():
        raise FileNotFoundError(
            "未找到 user_profile.json，请复制 user_profile.example.json 并填写个人信息"
        )
    with target.open(encoding="utf-8") as f:
        data = json.load(f)
    return UserProfile.model_validate(data)


def save_profile(profile: UserProfile, path: Optional[Path] = None) -> None:
    """将用户档案写回 JSON 文件（仅写 user_profile.json，不覆盖 example）。"""
    target = path or _PROFILE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(profile.model_dump(), f, indent=2, ensure_ascii=False)
    logger.info("用户档案已保存至 %s", target)
