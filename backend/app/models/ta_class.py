import secrets
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

# 邀请码字符集：去掉易混淆的 0/O/1/I/L
_INVITE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_class_invite_code() -> str:
    """生成 8 位班级邀请码，避开易混淆字符。"""
    return "".join(secrets.choice(_INVITE_CODE_ALPHABET) for _ in range(8))

class TaClass(Base):
    __tablename__ = "ta_classes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="班级名称")
    invite_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, default=generate_class_invite_code, comment="学生入班邀请码")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="班级描述")
    max_students: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="班级容量上限，空表示不限")
    course_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True, comment="关联课程")
    ta_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, comment="助教/教师用户ID")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    students = relationship("TaClassStudent", back_populates="class_ref", lazy="selectin")
