from typing import List
from pydantic import BaseModel


class ScoreBreakdown(BaseModel):
    skill_score: int        # 0-100，权重 40%
    experience_score: int   # 0-100，权重 25%
    salary_score: int       # 0-100，权重 20%
    location_score: int     # 0-100，权重 15%


class ScoreResult(BaseModel):
    total_score: int               # 0-100 综合得分
    breakdown: ScoreBreakdown
    match_reason: str              # 可读摘要，≤120字
    missing_skills: List[str]      # 简历中有但 JD 未命中的技能
    red_flags: List[str]           # 明显不匹配项（如经验差距过大）
    is_eligible: bool              # total_score >= 50 时为 True
