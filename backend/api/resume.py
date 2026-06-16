"""
用户档案相关 API 路由。

GET  /profile          — 读取用户档案
PUT  /profile          — 更新用户档案
POST /resume/upload    — 上传并解析简历文件（PDF/DOCX）
POST /resume/generate  — （Phase 2）触发简历 AI 优化（非流式）
"""

import logging
import os
import re
import tempfile
from typing import List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File

from ..core.profile import UserProfile, load_profile, save_profile
from ..resume_parser.extractor import extract_pdf
from ..resume_parser.skills_vocab import extract_skills
from ..skills.parse_resume_pdf.skill import ParseResumePdfSkill
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["用户档案"])

# 单例，避免每次请求重建 LLM 链
_parse_skill: Optional[ParseResumePdfSkill] = None

def _get_parse_skill() -> ParseResumePdfSkill:
    global _parse_skill
    if _parse_skill is None:
        _parse_skill = ParseResumePdfSkill()
    return _parse_skill


class ProfileUpdateRequest(BaseModel):
    profile: UserProfile


@router.get("/profile", summary="读取用户档案")
async def get_profile():
    """读取 user_profile.json，若文件不存在返回 404。"""
    try:
        profile = load_profile()
        return profile.model_dump()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/profile", summary="更新用户档案")
async def update_profile(body: ProfileUpdateRequest):
    """将前端传入的档案数据写入 user_profile.json。"""
    save_profile(body.profile)
    return {"message": "用户档案已更新"}



def _extract_text_docx(data: bytes) -> str:
    """用 python-docx 提取 DOCX 文本（若库不存在则报错）。"""
    import io  # noqa: PLC0415
    try:
        from docx import Document  # type: ignore
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    except ImportError:
        raise HTTPException(status_code=422, detail="需要安装 python-docx 才能解析 DOCX 文件")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"DOCX 解析失败: {e}")


def _simple_parse(text: str) -> dict:
    """
    基于正则/关键词从简历文本中提取结构化字段。
    这是轻量级启发式解析，不依赖 LLM。
    返回前端可直接消费的字段字典。
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    def first_match(pattern: str) -> str:
        for line in lines:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                return m.group(0)
        return ""

    # 手机
    phone = first_match(r"1[3-9]\d{9}")
    # 邮箱
    email = first_match(r"[\w.+-]+@[\w-]+\.[a-z]{2,}")
    # 城市（简单枚举）
    city = ""
    for c in ["北京", "上海", "深圳", "广州", "杭州", "成都", "武汉", "南京", "西安", "远程"]:
        if c in text:
            city = c
            break

    # 技能：扩展词库关键词扫描（确定性，不调用 embedding）
    found_skills: List[str] = extract_skills(full_text=text, use_semantic=False)

    return {
        "phone": phone,
        "email": email,
        "city": city,
        "skills": found_skills,
        "raw_text": text[:2000],
    }


@router.post("/resume/upload", summary="上传并解析简历")
async def upload_resume(file: UploadFile = File(...)):
    """
    接收 PDF 或 DOCX 文件，用 LLM 全量解析后返回给前端自动填充。
    PDF：ParseResumePdfSkill（本地规则解析基本信息/经历/项目/技能，无 LLM 调用）
    DOCX：降级到规则解析（仅手机/邮箱/城市/技能）
    """
    filename = (file.filename or "").lower()
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件内容为空")

    if filename.endswith(".pdf"):
        # ── PDF：完整 LLM 解析 ──────────────────────────────────
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(data)
                tmp_path = tmp.name

            result = await _get_parse_skill().execute({"pdf_path": tmp_path})
        except HTTPException:
            raise
        except Exception as e:
            logger.error("PDF 解析失败: %s", e, exc_info=True)
            raise HTTPException(status_code=422, detail=f"PDF 解析失败：{e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        profile: dict = result["profile"]
        raw_text: str  = result.get("raw_text", "")

        # projects: 后端字段 highlights → 前端字段 bullets
        projects = []
        for p in profile.get("projects", []):
            proj = dict(p)
            proj["bullets"] = proj.pop("highlights", [])
            projects.append(proj)

        response = {
            "name":        profile["basic"].get("name", ""),
            "email":       profile["basic"].get("email", ""),
            "phone":       profile["basic"].get("phone", ""),
            "city":        profile["basic"].get("city", ""),
            "school":      profile["basic"].get("school", ""),
            "grad_year":   profile["basic"].get("grad_year"),
            "skills":      profile.get("skills", []),
            "experiences": profile.get("experiences", []),
            "projects":    projects,
            "target":      profile.get("target", {}),
            "raw_text":    raw_text[:2000],
        }
        logger.info(
            "PDF 解析完成：经历 %d 条，项目 %d 条，技能 %d 项",
            len(response["experiences"]),
            len(response["projects"]),
            len(response["skills"]),
        )
        return response

    elif filename.endswith(".docx") or filename.endswith(".doc"):
        # ── DOCX：降级到规则解析 ────────────────────────────────
        text = _extract_text_docx(data)
        if not text.strip():
            raise HTTPException(status_code=422, detail="未能从文件中提取到文本")
        result = _simple_parse(text)
        logger.info("DOCX 简单解析完成，技能 %d 项", len(result.get("skills", [])))
        return result

    else:
        raise HTTPException(status_code=415, detail="仅支持 PDF / DOCX 格式")
