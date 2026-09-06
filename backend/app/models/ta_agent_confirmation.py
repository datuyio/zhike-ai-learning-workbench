"""教师端 AI 助手的待确认写操作记录。

写操作（布置作业、创建测验、发布公告等）由 Agent 提出参数、系统先落一条待确认
记录并暂停，教师确认后由确认端点真正执行；确认/取消都会更新状态，避免重复执行。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TaAgentConfirmation(Base):
    """教师端 Agent 写操作待确认记录。"""

    __tablename__ = "ta_agent_confirmations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # 归属会话与教师：仅创建者本人可确认/取消
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    ta_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    tool: Mapped[str] = mapped_column(String(120), nullable=False, comment="待执行的工具名")
    args_json: Mapped[dict] = mapped_column(JSONB, nullable=False, comment="工具参数（确认后执行）")
    summary: Mapped[str] = mapped_column(Text, nullable=False, comment="待确认操作的一句话说明，展示给教师")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="pending/confirmed/cancelled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
