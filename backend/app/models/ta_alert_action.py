import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class TaAlertAction(Base):
    """预警干预记录：一预警可有多条动作（提醒/推荐资源/预约辅导/备注）。"""

    __tablename__ = "ta_alert_actions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ta_alert_records.id"), nullable=False, comment="关联预警")
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, comment="助教用户")
    action_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="notify/recommend_resources/book_tutoring/note")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注/提醒文案")
    target_student_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, comment="目标学生")
    resource_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="推荐资源 UUID 列表")
    tutoring_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="预约辅导时间")
    notification_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, comment="生成的 ta_notifications 记录，可空")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
