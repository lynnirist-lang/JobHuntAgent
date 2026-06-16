"""
PDF 文本提取 + 章节分块。

提取链（优雅降级）：
  unstructured partition_pdf(strategy="fast")
    → ImportError / 解析失败 → pdfplumber
    → 两者均失败 → raise ValueError / HTTPException(422)
"""
from __future__ import annotations

import io
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# 数据类
# --------------------------------------------------------------------------
@dataclass
class ResumeChunks:
    """简历各章节文本。"""
    basic_info: str = ""
    education: str = ""
    experience: str = ""
    projects: str = ""
    skills: str = ""
    other: str = ""
    raw_text: str = ""


# --------------------------------------------------------------------------
# 章节头模式（中英文，按优先级有序）
# --------------------------------------------------------------------------
_SECTION_PATTERNS: List[tuple] = [
    ("education", [
        r"教育背景", r"教育经历", r"学历", r"学习经历",
        r"education", r"academic", r"schooling",
    ]),
    ("experience", [
        r"工作经历", r"实习经历", r"工作经验", r"工作履历", r"职业经历",
        r"experience", r"employment", r"internship", r"work history",
    ]),
    ("projects", [
        r"项目经历", r"项目经验", r"项目", r"个人项目",
        r"projects?", r"side\s*projects?",
    ]),
    ("skills", [
        r"技能", r"技术栈", r"专业技能", r"核心技能", r"技能特长",
        r"skills?", r"tech(?:nical)?\s*skills?", r"expertise", r"competencies",
    ]),
    ("basic_info", [
        r"个人信息", r"基本信息", r"个人简介",
        r"profile", r"personal\s*info(?:rmation)?", r"about\s*me",
    ]),
]

_HEADING_SENTINEL = "__HEADING__"


def _detect_section(line: str) -> Optional[str]:
    """
    若该行是章节标题则返回对应 key，否则返回 None。
    unstructured 已标记为 Title 的行带 __HEADING__ 前缀，直接走快速路径。
    """
    stripped = line.strip()
    if not stripped:
        return None

    is_labeled_heading = stripped.startswith(_HEADING_SENTINEL)
    heading_text = stripped[len(_HEADING_SENTINEL):] if is_labeled_heading else stripped

    # 带标记的 heading 不受长度限制；普通行限制 <= 40 字符
    if not is_labeled_heading and len(heading_text) > 40:
        return None

    for section_key, patterns in _SECTION_PATTERNS:
        for pat in patterns:
            if re.search(pat, heading_text, re.IGNORECASE):
                return section_key

    # 带标记但未匹配已知章节 → 归入 other 并切换章节
    if is_labeled_heading:
        return "other"

    return None


def _chunk_lines(lines: List[str]) -> ResumeChunks:
    """将行列表按章节标题分块，返回 ResumeChunks。"""
    buffers: Dict[str, List[str]] = {
        "basic_info": [], "education": [], "experience": [],
        "projects": [], "skills": [], "other": [],
    }
    current = "basic_info"
    all_lines: List[str] = []

    for line in lines:
        if not line.strip():
            continue
        all_lines.append(line)
        detected = _detect_section(line)
        if detected is not None:
            current = detected
        else:
            buffers[current].append(line)

    chunks = ResumeChunks(
        basic_info="\n".join(buffers["basic_info"]),
        education="\n".join(buffers["education"]),
        experience="\n".join(buffers["experience"]),
        projects="\n".join(buffers["projects"]),
        skills="\n".join(buffers["skills"]),
        other="\n".join(buffers["other"]),
        raw_text="\n".join(all_lines),
    )
    return chunks


# --------------------------------------------------------------------------
# 提取后端：unstructured
# --------------------------------------------------------------------------
def _extract_with_unstructured(data: bytes) -> Optional[List[str]]:
    """
    用 unstructured 提取 PDF 元素列表。
    Title 类型元素加 __HEADING__ 前缀，供 _detect_section 快速识别。
    strategy="fast" 避免下载 detectron2 布局模型。
    返回 None 表示不可用或失败，调用方负责降级。
    """
    try:
        from unstructured.partition.pdf import partition_pdf  # noqa: PLC0415
        from unstructured.documents.elements import Title    # noqa: PLC0415
    except Exception:
        # ImportError: library not installed; OSError/RuntimeError: dependency missing on Windows
        return None

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        elements = partition_pdf(tmp_path, strategy="fast")
        lines: List[str] = []
        for el in elements:
            text = str(el).strip()
            if not text:
                continue
            if isinstance(el, Title):
                lines.append(_HEADING_SENTINEL + text)
            else:
                lines.append(text)
        return lines
    except Exception as exc:
        logger.warning("unstructured 解析失败，降级到 pdfplumber: %s", exc)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                # Windows: partition_pdf may hold the handle briefly after returning;
                # the file will be cleaned up on process exit.
                pass


# --------------------------------------------------------------------------
# 提取后端：pdfplumber（fallback）
# --------------------------------------------------------------------------
def _extract_with_pdfplumber(data: bytes) -> Optional[List[str]]:
    """用 pdfplumber 提取文本行（最多 20 页）。失败返回 None。"""
    try:
        import pdfplumber  # noqa: PLC0415

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            lines: List[str] = []
            for page in pdf.pages[:20]:
                page_text = page.extract_text() or ""
                lines.extend(page_text.splitlines())
        return lines
    except Exception as exc:
        logger.warning("pdfplumber 解析失败: %s", exc)
        return None


# --------------------------------------------------------------------------
# 公开 API
# --------------------------------------------------------------------------
def extract_pdf(data: bytes) -> ResumeChunks:
    """
    从 PDF bytes 提取结构化章节。
    优先使用 unstructured，失败降级到 pdfplumber。
    两者均失败时 raise HTTPException(422)。
    """
    lines = _extract_with_unstructured(data)
    if not lines:  # None（库不可用）或 []（解析成功但无文本）均降级
        lines = _extract_with_pdfplumber(data)
    if not lines:
        from fastapi import HTTPException  # noqa: PLC0415
        raise HTTPException(
            status_code=422,
            detail="PDF 解析失败：unstructured 和 pdfplumber 均无法提取文本，请检查文件格式",
        )
    return _chunk_lines(lines)


def extract_pdf_from_path(pdf_path: str) -> ResumeChunks:
    """
    从 PDF 文件路径提取结构化章节（供 Skill 调用）。
    两者均失败时 raise ValueError。
    """
    with open(pdf_path, "rb") as f:
        data = f.read()

    lines = _extract_with_unstructured(data)
    if not lines:
        lines = _extract_with_pdfplumber(data)
    if not lines:
        raise ValueError("PDF 无法提取文本，可能是扫描件或加密文件")
    return _chunk_lines(lines)
