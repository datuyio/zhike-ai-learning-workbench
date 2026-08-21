import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Float, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class TaAssignment(Base):
    __tablename__ = "ta_assignments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ta_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, comment="布置作业的助教")
    class_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ta_classes.id"), nullable=False, comment="目标班级")
    course_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True)
    concept_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("course_concepts.id"), nullable=True, comment="关联知识点")
    title: Mapped[str] = mapped_column(String(300), nullable=False, comment="作业标题")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="作业说明")
    total_score: Mapped[float] = mapped_column(Float, default=100, comment="满分")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="截止时间，空=不限")
    late_policy: Mapped[str] = mapped_column(String(20), default="allow_penalty", comment="迟交策略: reject/allow_penalty/allow")
    late_penalty_ratio: Mapped[float] = mapped_column(Float, default=0.1, comment="迟交扣分比例")
    status: Mapped[str] = mapped_column(String(20), default="draft", comment="状态: draft/published/closed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TaSubmission(Base):
    __tablename__ = "ta_submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "student_id", name="uq_assignment_student"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ta_assignments.id"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False, comment="学生提交内容")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_late: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否逾期提交")
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, comment="提交次数，重交递增")
    grading_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ta_grading_records.id"), nullable=True)
