"""
JobScorer — 多维度岗位匹配评分器。

评分维度及权重：
  技能匹配   40%  (embedding 相似度 60% + 关键词命中率 40%)
  经验匹配   25%  (正则提取 JD 要求年限 vs 用户总工作年限)
  薪资匹配   20%  (解析薪资区间，计算与用户期望的重叠)
  地点匹配   15%  (城市名字符串包含匹配)

评分均为 0-100，最终取加权和后取整。
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple

from ..core.profile import UserProfile
from ..db.models import Job
from . import embedder as _embedder
from .models import ScoreBreakdown, ScoreResult
from .salary_parser import compute_salary_score, parse_salary

logger = logging.getLogger(__name__)

# ── 权重 ──────────────────────────────────────────────────────────
_W_SKILL = 0.40
_W_EXP   = 0.25
_W_SAL   = 0.20
_W_LOC   = 0.15

# ── 经验年限正则（按优先级排列）────────────────────────────────────
_EXP_PATTERNS: List[re.Pattern] = [
    re.compile(r"(\d+)\s*年以上.*?经验"),           # "3年以上工作经验"
    re.compile(r"经验.*?(\d+)\s*年以上"),            # "工作经验3年以上"
    re.compile(r"(\d+)\s*[-–~]\s*\d+\s*年.*?经验"), # "3-5年工作经验" 取下限
    re.compile(r"经验.*?(\d+)\s*[-–~]\s*\d+\s*年"), # "经验3-5年" 取下限
    re.compile(r"(\d+)\s*年.*?经验"),                # 兜底："1年以上经验"
]

# ── 经验友好型关键词（无门槛）────────────────────────────────────────
_FRESH_PATTERNS: List[re.Pattern] = [
    re.compile(r"应届"),
    re.compile(r"应届生"),
    re.compile(r"校招"),
    re.compile(r"经验不限"),
    re.compile(r"不限经验"),
    re.compile(r"无需.*?经验"),
    re.compile(r"经验.*?不限"),
]


class JobScorer:
    """对单个 Job 与 UserProfile 进行评分，无内部状态，可安全复用。"""

    async def score(self, job: Job, profile: UserProfile) -> ScoreResult:
        jd_text = f"{job.title} {job.description} {job.requirements}"

        skill_score, missing_skills = await self._score_skills(jd_text, job, profile)
        exp_score, exp_flag         = self._score_experience(jd_text, profile)
        sal_score, sal_flag         = self._score_salary(job.salary, profile)
        loc_score                   = self._score_location(job.location, profile)

        breakdown = ScoreBreakdown(
            skill_score=skill_score,
            experience_score=exp_score,
            salary_score=sal_score,
            location_score=loc_score,
        )

        total = int(
            skill_score * _W_SKILL
            + exp_score  * _W_EXP
            + sal_score  * _W_SAL
            + loc_score  * _W_LOC
        )

        red_flags = [f for f in [exp_flag, sal_flag] if f]
        match_reason = self._build_match_reason(breakdown, missing_skills)

        return ScoreResult(
            total_score=total,
            breakdown=breakdown,
            match_reason=match_reason,
            missing_skills=missing_skills,
            red_flags=red_flags,
            is_eligible=(total >= 50),
        )

    # ── 技能评分 ──────────────────────────────────────────────────

    async def _score_skills(
        self, jd_text: str, job: Job, profile: UserProfile
    ) -> Tuple[int, List[str]]:
        skills = profile.skills
        if not skills:
            return 50, []

        # 构建更丰富的候选人画像文本供 embedding 比较：
        # 目标岗位 + 历史角色 + 项目技术栈 + 技能列表
        profile_parts: List[str] = []
        if profile.target.roles:
            profile_parts.append(" ".join(profile.target.roles))
        for exp in profile.experiences[:2]:        # 最近两段经历的角色名
            profile_parts.append(exp.role)
        for proj in profile.projects[:3]:          # 最多3个项目的技术栈
            profile_parts.append(proj.tech)
        profile_parts.append(" ".join(skills))
        profile_text = " ".join(filter(None, profile_parts))

        # embedding 在线程池中运行，避免阻塞事件循环
        vecs = await asyncio.to_thread(
            _embedder.encode, [jd_text[:2000], profile_text[:1000]]
        )
        semantic_sim = _embedder.cosine_similarity(vecs[0], vecs[1])
        # cosine 值域 0~1，映射到 0~100
        # 多语言模型在中文上语义相似度普遍偏低（0.3~0.6 已算较好），乘以系数放大
        semantic_score = min(100, int(semantic_sim * 140))

        # 关键词命中：分母取 min(技能数, 5)——匹配到 5 个技能就算满分
        # 避免技能多的候选人因 JD 未全部列举而被不公平惩罚
        jd_lower = jd_text.lower()
        matched  = [s for s in skills if s.lower() in jd_lower]
        missing  = [s for s in skills if s.lower() not in jd_lower]
        denominator   = min(len(skills), 5)
        keyword_score = int(min(len(matched), denominator) / denominator * 100)

        # 岗位名称与目标职位直接匹配给予加成（10分上限）
        title_bonus = 0
        if profile.target.roles:
            job_title_lower = job.title.lower()
            if any(r.lower() in job_title_lower for r in profile.target.roles):
                title_bonus = 10

        blended = min(100, int(semantic_score * 0.6 + keyword_score * 0.4) + title_bonus)
        return blended, missing

    # ── 经验评分 ──────────────────────────────────────────────────

    def _score_experience(
        self, jd_text: str, profile: UserProfile
    ) -> Tuple[int, Optional[str]]:
        # 应届 / 经验不限 → 无门槛，直接高分
        for pat in _FRESH_PATTERNS:
            if pat.search(jd_text):
                return 85, None

        required = self._extract_required_years(jd_text)
        if required is None:
            return 60, None  # JD 未注明年限，给偏中性分

        user_years = self._compute_user_years(profile)

        if user_years >= required:
            return 100, None
        elif user_years >= required - 1:
            # 差 1 年以内：轻微不足
            return 70, None
        elif user_years >= required - 2:
            # 差 1~2 年：明显不足
            flag = f"要求{required}年经验，候选人约{user_years:.1f}年"
            return 30, flag
        else:
            # 差 2 年以上：严重不足
            flag = f"要求{required}年经验，候选人约{user_years:.1f}年，差距较大"
            return 5, flag

    def _extract_required_years(self, jd_text: str) -> Optional[int]:
        for pattern in _EXP_PATTERNS:
            m = pattern.search(jd_text)
            if m:
                return int(m.group(1))
        return None

    def _compute_user_years(self, profile: UserProfile) -> float:
        """累加所有 experience.duration 区间，换算为年。"""
        now = datetime.now()
        total_months = 0.0
        for exp in profile.experiences:
            parts = re.split(r"[-–]", exp.duration)
            if len(parts) != 2:
                continue
            start_str, end_str = parts[0].strip(), parts[1].strip()
            try:
                start = self._parse_ym(start_str)
                if any(k in end_str for k in ("至今", "现在", "now", "present")):
                    end = now
                else:
                    end = self._parse_ym(end_str)
                delta = (end.year - start.year) * 12 + (end.month - start.month)
                total_months += max(0, delta)
            except (ValueError, AttributeError):
                continue
        return round(total_months / 12, 1)

    @staticmethod
    def _parse_ym(s: str) -> datetime:
        """解析 "2025.09"、"2025/09"、"2025-09" 等格式为 datetime。"""
        s = s.strip().replace("/", ".").replace("-", ".")
        parts = s.split(".")
        year  = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        return datetime(year, month, 1)

    # ── 薪资评分 ──────────────────────────────────────────────────

    def _score_salary(
        self, salary_str: str, profile: UserProfile
    ) -> Tuple[int, Optional[str]]:
        job_min, job_max = parse_salary(salary_str)
        target_min, target_max = parse_salary(profile.target.salary)

        if target_min is None:
            # 用户未设定薪资期望，给中性分
            return 60, None

        score = compute_salary_score(job_min, job_max, target_min, target_max)
        flag  = None
        if score < 30 and job_max is not None:
            flag = f"薪资 {salary_str} 低于期望 {profile.target.salary}"
        return score, flag

    # ── 地点评分 ──────────────────────────────────────────────────

    def _score_location(self, job_location: str, profile: UserProfile) -> int:
        if not job_location:
            return 50
        target_cities = profile.target.cities
        if not target_cities:
            return 50
        job_loc_lower = job_location.lower()
        for city in target_cities:
            city_lower = city.lower()
            # 远程/居家岗位特殊处理
            if city_lower in ("远程", "remote") and any(
                kw in job_loc_lower for kw in ("远程", "remote", "居家", "在家")
            ):
                return 100
            # 城市名字符串包含匹配（"上海·浦东" 包含 "上海"）
            if city_lower in job_loc_lower:
                return 100
        return 0

    # ── 可读摘要 ──────────────────────────────────────────────────

    def _build_match_reason(
        self, breakdown: ScoreBreakdown, missing_skills: List[str]
    ) -> str:
        parts: List[str] = []

        if breakdown.skill_score >= 70:
            parts.append("技能匹配良好")
        elif missing_skills:
            sample = "、".join(missing_skills[:3])
            parts.append(f"缺少技能：{sample}")

        if breakdown.experience_score >= 80:
            parts.append("经验符合要求")
        elif breakdown.experience_score < 40:
            parts.append("经验不足")

        if breakdown.salary_score >= 80:
            parts.append("薪资匹配")
        elif breakdown.salary_score < 30:
            parts.append("薪资偏低")

        if breakdown.location_score == 100:
            parts.append("城市匹配")
        elif breakdown.location_score == 0:
            parts.append("城市不符")

        return "；".join(parts) if parts else "基础匹配"
