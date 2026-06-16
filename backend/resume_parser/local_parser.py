"""
基于规则的简历解析器 — 不依赖任何 LLM。

输入：ResumeChunks（已由 extractor.py 按章节分块）
输出：与 ParseResumePdfSkill 相同的 profile dict

解析逻辑：
  basic_info → 姓名/手机/邮箱/城市（正则 + 启发式）
  education  → 学校/毕业年份/专业
  experience → 公司/职位/时间段/描述（日期行作为块分隔符）
  projects   → 项目名/技术栈/亮点（空行或非子弹头行作为块分隔符）
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .extractor import ResumeChunks

# ─────────────────────────── Patterns ────────────────────────────────────────

_PHONE_RE = re.compile(r"1[3-9]\d{9}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.IGNORECASE)

# 日期区间：2024.03-2025.06 / 2024年3月-至今 / 2024/03~present
_DATE_RANGE_RE = re.compile(
    r"(\d{4}[./年]\s*\d{1,2}[月]?)\s*[-–—至~到]\s*"
    r"(\d{4}[./年]\s*\d{1,2}[月]?|至今|present|now)",
    re.IGNORECASE,
)

_BULLET_CHARS = frozenset("•·-*→▪◆▸►✓√")
_SCHOOL_RE = re.compile(r"[一-鿿\w]+(大学|学院|University|College|Institute)\w*")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")

_CITIES = [
    "北京", "上海", "深圳", "广州", "杭州", "成都", "武汉", "南京",
    "西安", "重庆", "苏州", "天津", "长沙", "郑州", "青岛", "厦门", "远程",
]

# 公司/机构关键词，用于判断是否是公司名而非职位名
_COMPANY_KEYWORDS_RE = re.compile(r"公司|集团|有限|科技|互联|网络|软件|银行|保险|Ltd|Inc|Corp")


# ─────────────────────────── Helpers ─────────────────────────────────────────

def _is_bullet(line: str) -> bool:
    return bool(line) and line[0] in _BULLET_CHARS


def _strip_bullet(line: str) -> str:
    return re.sub(r'^[•·\-\*→▪◆▸►✓√]\s*', '', line).strip()


# ─────────────────────────── Basic info ──────────────────────────────────────

def _extract_name(lines: List[str]) -> str:
    """从前 10 行中找符合姓名格式的行。"""
    zh_name = re.compile(r'^[一-鿿]{2,6}$')
    en_name = re.compile(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$')
    for line in lines[:10]:
        s = line.strip()
        if not s:
            continue
        if _PHONE_RE.search(s) or _EMAIL_RE.search(s):
            continue
        if any(c in s for c in _CITIES):
            continue
        if _SCHOOL_RE.search(s):
            continue
        if zh_name.match(s) or en_name.match(s):
            return s
    return ""


def parse_basic_info(basic_info: str, raw_text: str) -> Dict[str, str]:
    info_lines = [l.strip() for l in basic_info.splitlines() if l.strip()]
    raw_lines  = [l.strip() for l in raw_text.splitlines()   if l.strip()]

    phone = (m := _PHONE_RE.search(raw_text)) and m.group(0) or ""
    email = (m := _EMAIL_RE.search(raw_text)) and m.group(0) or ""

    city = ""
    for c in _CITIES:
        if c in raw_text:
            city = c
            break

    name = _extract_name(info_lines) or _extract_name(raw_lines)
    return {"name": name, "phone": phone, "email": email, "city": city}


# ─────────────────────────── Education ───────────────────────────────────────

def parse_education(education: str) -> Tuple[str, Optional[int], str]:
    """返回 (学校, 毕业年份, 专业)。"""
    school = (m := _SCHOOL_RE.search(education)) and m.group(0) or ""

    years = [int(y) for y in _YEAR_RE.findall(education)]
    grad_year: Optional[int] = max(years) if years else None

    major = ""
    for line in education.splitlines():
        line = line.strip()
        if "专业" in line or re.search(r"(计算机|软件工程|信息工程|电子|通信|数学|物理|经济|管理).*?(专业|系)", line):
            m2 = re.search(r"([一-鿿]+(?:专业|系))", line)
            if m2:
                major = m2.group(1)
                break

    return school, grad_year, major


# ─────────────────────────── Experiences ─────────────────────────────────────

def parse_experiences(experience: str) -> List[Dict]:
    if not experience.strip():
        return []

    stripped = [l.strip() for l in experience.splitlines()]

    # 找含日期区间的行的索引
    date_indices = [i for i, l in enumerate(stripped) if _DATE_RANGE_RE.search(l)]
    if not date_indices:
        return []

    # 先计算每条目的标题起始行（日期行往前 0-2 个非子弹头行）
    header_starts: List[int] = []
    for k, di in enumerate(date_indices):
        hs = di
        look_back = 0
        prev_di = date_indices[k - 1] if k > 0 else -1
        while hs > 0 and look_back < 2:
            prev = stripped[hs - 1]
            if not prev or _is_bullet(prev):
                break
            if hs - 1 <= prev_di:
                break
            hs -= 1
            look_back += 1
        header_starts.append(hs)

    results = []
    for k, di in enumerate(date_indices):
        header_text = " ".join(s for s in stripped[header_starts[k]:di + 1] if s)

        # 提取时间段
        dm = _DATE_RANGE_RE.search(header_text)
        duration = dm.group(0) if dm else ""
        if dm:
            header_text = (header_text[:dm.start()] + " " + header_text[dm.end():]).strip()

        # 分离公司/职位
        parts = re.split(r"\s*[|｜·]\s*|\s{2,}", header_text)
        parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 1]

        company, role = "", ""
        if len(parts) >= 2:
            company, role = parts[0], parts[1]
        elif len(parts) == 1:
            val = parts[0]
            if _COMPANY_KEYWORDS_RE.search(val):
                company = val
            else:
                role = val

        # 内容区结束 = 下一条目的标题起始行（精确，不留补偿量）
        body_end = header_starts[k + 1] if k + 1 < len(date_indices) else len(stripped)

        bullets = []
        for bl in stripped[di + 1:body_end]:
            if not bl:
                continue
            cleaned = _strip_bullet(bl)
            if cleaned and not _DATE_RANGE_RE.search(cleaned):
                bullets.append(cleaned)

        if company or role or duration:
            results.append({
                "company":  company,
                "role":     role,
                "duration": duration,
                "bullets":  bullets,
            })

    return results


# ─────────────────────────── Projects ────────────────────────────────────────

def _split_project_blocks(lines: List[str]) -> List[List[str]]:
    """将项目章节拆成独立的项目块。以空行或"非子弹头行跟在子弹头行之后"为分隔。"""
    blocks: List[List[str]] = []
    current: List[str] = []
    seen_bullet = False

    for raw in lines:
        line = raw.strip()
        if not line:
            if seen_bullet and current:
                blocks.append(current)
                current = []
                seen_bullet = False
            continue

        if _is_bullet(line):
            seen_bullet = True
            current.append(line)
        else:
            # 非子弹头行：若已有内容则开新块
            if seen_bullet:
                blocks.append(current)
                current = [line]
                seen_bullet = False
            else:
                current.append(line)

    if current:
        blocks.append(current)

    return [b for b in blocks if any(l for l in b)]


def parse_projects(projects: str) -> List[Dict]:
    if not projects.strip():
        return []

    blocks = _split_project_blocks(projects.splitlines())
    results = []

    for block in blocks:
        non_empty = [l for l in block if l]
        if not non_empty:
            continue

        # 标题行：第一个（或几个）非子弹头行
        header_lines: List[str] = []
        bullet_lines: List[str] = []
        past_header = False

        for line in non_empty:
            if _is_bullet(line):
                past_header = True
                bullet_lines.append(line)
            elif not past_header:
                header_lines.append(line)
            else:
                bullet_lines.append(line)

        if not header_lines:
            continue

        header_text = " ".join(header_lines)

        # 提取技术栈：括号内 或 分隔符后
        tech = ""
        tm = re.search(r"[（(]([^）)]+)[）)]", header_text)
        if tm:
            tech = tm.group(1)
            header_text = (header_text[:tm.start()] + header_text[tm.end():]).strip()
        else:
            parts = re.split(r"\s*[|｜·]\s*", header_text, maxsplit=1)
            if len(parts) > 1:
                header_text, tech = parts[0].strip(), parts[1].strip()

        name = re.sub(r'^[\d\.\s]+', '', header_text).strip()

        highlights = [_strip_bullet(bl) for bl in bullet_lines if _strip_bullet(bl)]

        if name:
            results.append({
                "name":       name,
                "tech":       tech,
                "highlights": highlights,
                "github":     "",
            })

    return results


# ─────────────────────────── Public API ──────────────────────────────────────

def parse_resume(chunks: ResumeChunks, skills: List[str]) -> Dict:
    """
    规则解析完整简历，返回与 ParseResumePdfSkill 相同格式的 profile dict。

    Args:
        chunks: extractor.py 产出的章节块
        skills: 已由 extract_skills() 提取的技能列表（确定性，不在此重新提取）
    """
    basic                   = parse_basic_info(chunks.basic_info, chunks.raw_text)
    school, grad_year, major = parse_education(chunks.education)

    return {
        "basic": {
            "name":      basic["name"],
            "email":     basic["email"],
            "phone":     basic["phone"],
            "city":      basic["city"],
            "school":    school,
            "major":     major,
            "grad_year": grad_year,
        },
        "experiences": parse_experiences(chunks.experience),
        "projects":    parse_projects(chunks.projects),
        "skills":      skills,
        "target":      {},
    }
