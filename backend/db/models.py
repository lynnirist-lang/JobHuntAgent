"""
数据库表定义（SQLModel = SQLAlchemy + Pydantic 合一）。

三张核心表：
  Job             — 从 BOSS 爬取的岗位信息 + AI 评分结果
  Application     — 每次投递记录（一个 Job 可有多次尝试）
  ResumeSnapshot  — 投递时的简历快照，支持历史版本回溯
"""

import json
from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


# ─────────────────────────── 枚举 ────────────────────────────────

class JobStatus(str, Enum):
    """岗位在整个流程中的状态机。"""
    PENDING = "pending"           # 刚爬取，等待 AI 处理
    MATCHED = "matched"           # 打招呼已生成，等待用户审批
    APPROVED = "approved"         # 用户批准，等待启动投递
    PENDING_SEND = "pending_send" # 已入冷却队列，倒计时中（半自动模式）
    SKIPPED = "skipped"           # 用户在 UI 跳过
    SENT = "sent"                 # 打招呼已发送
    READ = "read"                 # HR 已读
    REPLIED = "replied"           # HR 有回复
    LOW_PRIORITY = "low_priority" # 留作兼容，不再主动使用
    FAILED = "failed"             # 投递过程出错


class ApplicationStatus(str, Enum):
    """单次投递记录的状态。"""
    APPROVED = "approved"   # 已批准，尚未发送
    SENT = "sent"           # 已发送
    READ = "read"           # HR 已读
    REPLIED = "replied"     # 有回复
    FAILED = "failed"       # 发送失败


# ─────────────────────────── 表定义 ──────────────────────────────

class Job(SQLModel, table=True):
    """
    BOSS 岗位信息表。

    boss_job_id 设唯一约束，爬取时用 INSERT OR IGNORE 防止重复入库。
    missing_skills / red_flags 存为 JSON 字符串，避免额外关联表。
    """
    id: Optional[int] = Field(default=None, primary_key=True)

    # BOSS 平台唯一岗位 ID（URL 中的 job_id 参数）
    boss_job_id: str = Field(unique=True, index=True)

    # 基本信息
    title: str = Field(index=True)
    company: str = Field(index=True)
    salary: str = ""
    location: str = ""
    description: str = ""         # 完整 JD 文本，供 AI 分析
    requirements: str = ""        # 岗位要求（部分页面独立区块）
    boss_url: str = ""            # 岗位详情页 URL

    # AI 评分结果
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)
    score: Optional[int] = None                    # 匹配分 0-100
    match_reason: Optional[str] = None             # 匹配理由
    missing_skills: Optional[str] = None           # JSON: ["Go语言", "K8s"]
    red_flags: Optional[str] = None                # JSON: ["要求3年以上"]
    greeting_message: Optional[str] = None         # 打招呼草稿，UI 可编辑
    score_breakdown: Optional[str] = None          # JSON: ScoreBreakdown dict
    cooldown_until: Optional[datetime] = None      # 半自动冷却期截止时间

    # 时间戳
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # 反向关系
    applications: List["Application"] = Relationship(back_populates="job")

    # ── 便捷属性 ──────────────────────────────────────────────
    @property
    def missing_skills_list(self) -> List[str]:
        """将 JSON 字符串解析为列表，方便代码使用。"""
        if not self.missing_skills:
            return []
        try:
            return json.loads(self.missing_skills)
        except json.JSONDecodeError:
            return []

    @property
    def red_flags_list(self) -> List[str]:
        if not self.red_flags:
            return []
        try:
            return json.loads(self.red_flags)
        except json.JSONDecodeError:
            return []


class ResumeSnapshot(SQLModel, table=True):
    """
    简历快照表。

    每次批量投递前保存当前 UserProfile，通过外键关联 Application，
    方便日后回溯"当时投递时用的是哪个版本的简历"。
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    content: str                           # JSON 序列化的 UserProfile
    created_at: datetime = Field(default_factory=datetime.utcnow)

    applications: List["Application"] = Relationship(back_populates="resume_snapshot")


class Application(SQLModel, table=True):
    """
    投递记录表。

    一个 Job 可能因重试而有多条 Application 记录。
    resume_snapshot_id 关联投递时使用的简历版本。
    """
    id: Optional[int] = Field(default=None, primary_key=True)

    # 外键
    job_id: int = Field(foreign_key="job.id", index=True)
    resume_snapshot_id: Optional[int] = Field(
        default=None, foreign_key="resumesnapshot.id"
    )

    # 投递详情
    status: ApplicationStatus = Field(default=ApplicationStatus.APPROVED, index=True)
    greeting_message: str = ""            # 实际发送的打招呼语（可能用户编辑过）
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None  # 失败时记录错误信息

    # 时间戳
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # 关系
    job: Optional[Job] = Relationship(back_populates="applications")
    resume_snapshot: Optional[ResumeSnapshot] = Relationship(
        back_populates="applications"
    )
