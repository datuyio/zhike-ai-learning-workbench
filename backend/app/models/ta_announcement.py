import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class TaAnnouncement(Base):
    __tablename__ = "ta_announcements"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False, comment="公告标题")
    body: Mapped[str] = mapped_column(Text, nullable=False, comment="公告内容")
    announcement_type: Mapped[str] = mapped_column(String(30), default="general", comment="类型: general/homework/notice")
    class_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ta_classes.id"), nullable=True, comment="目标班级, None=全体")
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, comment="发布人")
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否置顶")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否生效，False=已撤回")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
