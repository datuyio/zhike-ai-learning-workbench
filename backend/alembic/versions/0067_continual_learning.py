"""持续学习闭环：新增 AI 反馈表与进化日志表。

Revision ID: 0067_continual_learning
Revises: 0066_ta_agent_confirmations
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0067_continual_learning"
down_revision = "0066_ta_agent_confirmations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 全新库中 0001 的 create_all 已按当前模型建出下述两表，
    # 按 0032 迁移的既有模式用表存在性守卫保证幂等。
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    table_names = set(inspector.get_table_names())

    # 教师对 AI 输出的 1-5 星评分与文字反馈，支撑反馈闭环与校准统计。
    if "continual_ai_feedback" not in table_names:
        op.create_table(
            "continual_ai_feedback",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("ta_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="SET NULL"), nullable=True),
            sa.Column("class_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ta_classes.id", ondelete="SET NULL"), nullable=True),
            sa.Column("target_type", sa.String(length=40), nullable=False),
            sa.Column("target_id", sa.String(length=160), nullable=True),
            sa.Column("rating", sa.Integer(), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_continual_ai_feedback_ta_user_id", "continual_ai_feedback", ["ta_user_id"])
        op.create_index("ix_continual_ai_feedback_course_id", "continual_ai_feedback", ["course_id"])
        op.create_index("ix_continual_ai_feedback_class_id", "continual_ai_feedback", ["class_id"])
        op.create_index("ix_continual_ai_feedback_target_type", "continual_ai_feedback", ["target_type"])
        op.create_index("ix_continual_ai_feedback_target_id", "continual_ai_feedback", ["target_id"])

    # 系统进化日志：反馈校准、风险模型重算、易错点更新等演变事件轨迹。
    if "continual_evolution_events" not in table_names:
        op.create_table(
            "continual_evolution_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("event_type", sa.String(length=60), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("metrics_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_continual_evolution_events_event_type", "continual_evolution_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_continual_evolution_events_event_type", table_name="continual_evolution_events")
    op.drop_table("continual_evolution_events")
    op.drop_index("ix_continual_ai_feedback_target_id", table_name="continual_ai_feedback")
    op.drop_index("ix_continual_ai_feedback_target_type", table_name="continual_ai_feedback")
    op.drop_index("ix_continual_ai_feedback_class_id", table_name="continual_ai_feedback")
    op.drop_index("ix_continual_ai_feedback_course_id", table_name="continual_ai_feedback")
    op.drop_index("ix_continual_ai_feedback_ta_user_id", table_name="continual_ai_feedback")
    op.drop_table("continual_ai_feedback")
