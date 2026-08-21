import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

class TaLessonPlan(Base):
    __tablename__ = "ta_lesson_plans"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False, comment="教案标题")
    course_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True, comment="关联课程")
    chapter: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="章节名称")
    content: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="教案结构化内容")
    outline: Mapped[str | None] = mapped_column(Text, nullable=True, comment="教案大纲Markdown")
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, comment="创建者ID")
    version: Mapped[int] = mapped_column(Integer, default=1, comment="版本号")
    is_published: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False, comment="是否发布")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
