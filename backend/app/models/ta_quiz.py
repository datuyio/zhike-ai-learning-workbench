import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class TaQuiz(Base):
    """随堂测验（客观题，draft→published→closed）。"""

    __tablename__ = "ta_quizzes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ta_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    class_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ta_classes.id"), nullable=False)
    course_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", comment="draft/published/closed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TaQuizQuestion(Base):
    """测验题目（单选/判断）。"""

    __tablename__ = "ta_quiz_questions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ta_quizzes.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    question_type: Mapped[str] = mapped_column(String(30), default="single_choice", comment="single_choice/true_false")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, comment="题干")
    options: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="单选选项数组，判断题为['正确','错误']")
    answer: Mapped[str] = mapped_column(String(20), nullable=False, comment="标准答案: A/T/F")
    score: Mapped[float] = mapped_column(Float, default=10)


class TaQuizAttempt(Base):
    """学生作答记录（每生每测验一条）。"""

    __tablename__ = "ta_quiz_attempts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ta_quizzes.id"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    answers: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="{question_id: 作答}")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grading_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, comment="生成的批改记录，可空")
    __table_args__ = (UniqueConstraint("quiz_id", "student_id", name="uq_quiz_student"),)
