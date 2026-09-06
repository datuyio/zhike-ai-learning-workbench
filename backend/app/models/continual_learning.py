import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ContinualAiFeedback(Base, UUIDMixin, TimestampMixin):
    """教师对 AI 输出的评分与文字反馈，构成持续学习的反馈闭环数据源。

    target_type 取值：lesson_plan（教案）/ grading（AI 批改）/
    advice（诊断建议）/ resource（资源生成），target_id 为对应业务对象标识。
    """

    __tablename__ = "continual_ai_feedback"

    ta_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True,
        comment="提交反馈的助教用户",
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    class_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ta_classes.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    target_type: Mapped[str] = mapped_column(String(40), index=True, comment="AI 输出类型")
    target_id: Mapped[str | None] = mapped_column(String(160), index=True, comment="被评价对象标识")
    rating: Mapped[int] = mapped_column(Integer, comment="1-5 星评分")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True, comment="文字反馈")


class ContinualEvolutionEvent(Base, UUIDMixin, TimestampMixin):
    """系统持续学习的进化日志：记录反馈校准、风险模型重算、错误模式更新等演变事件。

    event_type 取值：feedback_calibration（反馈驱动校准）/ risk_recalibrated
    （遗忘风险模型重算）/ error_patterns_updated（易错点更新）/ negative_feedback
    （低分反馈警示），metrics_json 保存可供可视化轨迹的量化指标。
    """

    __tablename__ = "continual_evolution_events"

    event_type: Mapped[str] = mapped_column(String(60), index=True, comment="进化事件类型")
    title: Mapped[str] = mapped_column(String(200), comment="事件标题")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True, comment="事件说明")
    metrics_json: Mapped[dict] = mapped_column(JSONB, default=dict, comment="量化指标载荷")
