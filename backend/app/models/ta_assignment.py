import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Float, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="作业说明/题目要求")
    question_type: Mapped[str] = mapped_column(String(30), default="short_answer", comment="题型: short_answer/code/single_choice/true_false 等")
    options: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="客观题选项数组，主观题为空")
    correct_answer: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="客观题标准答案，主观题为空")
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
    answer: Mapped[str] = mapped_column(Text, nullable=False, comment="学生提交内容（单题文本，或与 answers 并存）")
    answers: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="多题作答 {question_id: 作答}，单题提交为空")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_late: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否逾期提交")
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, comment="提交次数，重交递增")
    grading_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ta_grading_records.id"), nullable=True)


class TaAssignmentQuestion(Base):
    """作业题目快照：布置作业时从题库复制或手动输入，保证发布后题目内容稳定。

    客观题（单选/多选/判断/填空）记录 options 与 answer，提交后自动判分；
    主观题（简答/代码）answer 为空，走 AI 批改。
    """

    __tablename__ = "ta_assignment_questions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ta_assignments.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    question_type: Mapped[str] = mapped_column(String(30), default="single_choice", comment="题型: single_choice/multiple_choice/true_false/blank/short_answer/code")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, comment="题干")
    options: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="客观题选项数组，主观题为空")
    answer: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="客观题标准答案（多选用逗号分隔），主观题为空")
    score: Mapped[float] = mapped_column(Float, default=10)
