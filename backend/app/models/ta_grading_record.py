import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Float, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

class TaGradingRecord(Base):
    __tablename__ = "ta_grading_records"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False, comment="作业/题目标题")
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    course_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True)
    class_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ta_classes.id"), nullable=True)
    grader_type: Mapped[str] = mapped_column(String(20), default="ai_assisted", comment="批改方式: auto/ai_assisted/manual")
    question_type: Mapped[str | None] = mapped_column(String(30), nullable=True, comment="题目类型")
    concept_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("course_concepts.id"), nullable=True, comment="关联知识点")
    score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="得分")
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="满分")
    feedback: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="批改反馈")
    ai_comment: Mapped[str | None] = mapped_column(Text, nullable=True, comment="AI评语")
    ta_comment: Mapped[str | None] = mapped_column(Text, nullable=True, comment="助教补充")
    student_answer: Mapped[str | None] = mapped_column(Text, nullable=True, comment="学生提交内容（原题+作答）")
    attempt_number: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0, comment="批改/提交次数，支持重交重批")
    is_late: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False, comment="是否逾期提交")
    late_penalty: Mapped[float | None] = mapped_column(Float, nullable=True, comment="逾期扣分")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="状态: pending/graded/returned")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
