import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class TaQuestionBank(Base):
    """本地测试题库：独立于测验存在的题目库，布置作业/测验时按题选取。

    布置时从题库选择题目，后端会把选中题目快照复制到 ta_quiz_questions，
    保证学生作答与判分链路不变；题库本身不直接暴露给学生端。
    """

    __tablename__ = "ta_question_bank"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True, comment="所属课程，可空表示通用题")
    question_type: Mapped[str] = mapped_column(String(30), default="single_choice", comment="题型: single_choice/true_false")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, comment="题干")
    options: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="单选选项数组，判断题为['正确','错误']")
    answer: Mapped[str] = mapped_column(String(20), nullable=False, comment="标准答案: A/B/C/D 或 T/F")
    score: Mapped[float] = mapped_column(Float, default=10, comment="默认分值")
    source: Mapped[str] = mapped_column(String(30), default="local_test", comment="题库来源: local_test 本地测试题库")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
