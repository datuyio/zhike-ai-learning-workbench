import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class TaNotification(Base):
    """学生通知（统一收件箱）：作业/公告/测验发布 + 预警提醒四源汇入。"""

    __tablename__ = "ta_notifications"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, comment="接收学生")
    class_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ta_classes.id"), nullable=True, comment="关联班级，可空")
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="alert_reminder/announcement/assignment/quiz")
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="溯源类型")
    source_id: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="溯源主键字符串")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
