"""
解析中文薪资字符串为 (min_k, max_k) 整数元组（单位：K/月）。

支持格式：
  "15-25K·13薪"  → (15, 25)
  "30K以上"       → (30, 60)   # 上限取下限的 2 倍
  "20K"           → (20, 20)
  "面议"          → (None, None)
  "15000-25000"   → (15, 25)   # 整数元/月格式
  "1.5-2.5万"     → (15, 25)
"""

import re
from typing import Optional, Tuple


def parse_salary(salary_str: str) -> Tuple[Optional[int], Optional[int]]:
    """返回 (min_k, max_k)；面议或无法解析返回 (None, None)。"""
    if not salary_str:
        return None, None

    s = salary_str.strip()

    # 面议
    if re.search(r"面议|negotiable|待定|TBD", s, re.IGNORECASE):
        return None, None

    # 去掉薪资倍数后缀（·13薪、·16薪 等）
    s = re.sub(r"[·・]\d+薪", "", s)
    # 去掉"每月"等单位说明
    s = re.sub(r"每月|/月|per\s*month", "", s, flags=re.IGNORECASE)

    s_upper = s.upper()

    # 万元格式："1.5-2.5万" → 先换算成 K
    m = re.search(r"([\d.]+)\s*[-–~]\s*([\d.]+)\s*万", s)
    if m:
        return int(float(m.group(1)) * 10), int(float(m.group(2)) * 10)
    m = re.search(r"([\d.]+)\s*万以上", s)
    if m:
        lo = int(float(m.group(1)) * 10)
        return lo, lo * 2

    # 区间格式（含 K/k）："15-25K" 或 "15K-25K"
    m = re.search(r"([\d.]+)\s*[Kk]?\s*[-–~]\s*([\d.]+)\s*[Kk]", s_upper)
    if m:
        return int(float(m.group(1))), int(float(m.group(2)))

    # "以上" 格式："30K以上"
    m = re.search(r"([\d.]+)\s*[Kk]以上", s_upper)
    if m:
        lo = int(float(m.group(1)))
        return lo, lo * 2

    # 单值 K："20K"
    m = re.search(r"([\d.]+)\s*[Kk]", s_upper)
    if m:
        v = int(float(m.group(1)))
        return v, v

    # 全数字元/月："15000-25000"
    m = re.search(r"(\d{4,6})\s*[-–~]\s*(\d{4,6})", s)
    if m:
        lo = int(m.group(1)) // 1000
        hi = int(m.group(2)) // 1000
        if lo > 0 and hi > 0:
            return lo, hi

    return None, None


def compute_salary_score(
    job_min: Optional[int],
    job_max: Optional[int],
    profile_min: int,
    profile_max: int,
) -> int:
    """
    计算薪资匹配分（0-100）。

    - job_max < profile_min：低于期望，0~40 分
    - job_min > profile_max：高于期望（对候选人有利），90 分
    - 有区间重叠：50~100 分，按重叠比例线性插值
    """
    if job_min is None or job_max is None:
        return 60  # 面议：中性分

    if job_max < profile_min:
        # 薪资上限低于期望下限，按差距给惩罚
        gap_ratio = (profile_min - job_max) / max(profile_min, 1)
        return max(0, int(40 - gap_ratio * 40))

    if job_min > profile_max:
        # 薪资高于期望（对候选人有利）
        return 90

    # 计算区间重叠
    overlap_lo = max(job_min, profile_min)
    overlap_hi = min(job_max, profile_max)
    overlap = max(0, overlap_hi - overlap_lo)
    profile_range = max(1, profile_max - profile_min)
    ratio = overlap / profile_range
    return int(50 + ratio * 50)
