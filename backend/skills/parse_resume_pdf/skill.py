"""
Skill: parse_resume_pdf

分层解析流程（纯本地，无 LLM）：
  1. unstructured / pdfplumber 提取文本并分块
  2. 混合技能提取（关键词 + embedding，确定性）
  3. 规则解析基本信息/经历/项目（local_parser.py）
"""
import logging
from pathlib import Path
from typing import Any, Dict

from ...resume_parser.extractor import extract_pdf_from_path
from ...resume_parser.local_parser import parse_resume
from ...resume_parser.skills_vocab import extract_skills

logger = logging.getLogger(__name__)


class ParseResumePdfSkill:
    NAME = "parse_resume_pdf"

    async def execute(self, inputs: Dict[str, Any], **_) -> Dict[str, Any]:
        pdf_path = Path(inputs["pdf_path"])
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Step 1: 结构化提取（unstructured → pdfplumber 降级）
        chunks = extract_pdf_from_path(str(pdf_path))

        if not chunks.raw_text.strip():
            raise ValueError("PDF 无法提取文本，可能是扫描件")

        # Step 2: 混合技能提取（确定性，不依赖 LLM）
        extracted_skills = extract_skills(
            full_text=chunks.raw_text,
            skills_section_text=chunks.skills,
            use_semantic=True,
        )

        # Step 3: 规则解析结构化字段
        profile_data = parse_resume(chunks, extracted_skills)

        logger.info(
            "本地解析完成：经历 %d 条，项目 %d 条，技能 %d 项",
            len(profile_data["experiences"]),
            len(profile_data["projects"]),
            len(extracted_skills),
        )
        return {"profile": profile_data, "raw_text": chunks.raw_text}
