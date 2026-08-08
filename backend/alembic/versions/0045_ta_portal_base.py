"""创建助教端口基础表

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-04

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0045_ta_portal_base"
down_revision: Union[str, None] = "0044_fix_admin_password_hash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 班级表
    op.create_table(
        "ta_classes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, comment="班级名称"),
        sa.Column("description", sa.Text, nullable=True, comment="班级描述"),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=True, comment="关联课程"),
        sa.Column("ta_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, comment="助教用户ID"),
        sa.Column("is_active", sa.Boolean, default=True, comment="是否启用"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    # 班级学生关联表
    op.create_table(
        "ta_class_students",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("class_id", sa.String(36), sa.ForeignKey("ta_classes.id"), nullable=False),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # 教案表
    op.create_table(
        "ta_lesson_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False, comment="教案标题"),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=True),
        sa.Column("chapter", sa.String(200), nullable=True, comment="章节"),
        sa.Column("content", JSONB, nullable=True, comment="教案结构化内容"),
        sa.Column("outline", sa.Text, nullable=True, comment="大纲"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer, default=1),
        sa.Column("is_published", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    # 批改记录表
    op.create_table(
        "ta_grading_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=True),
        sa.Column("class_id", sa.String(36), sa.ForeignKey("ta_classes.id"), nullable=True),
        sa.Column("grader_type", sa.String(20), default="ai_assisted"),
        sa.Column("question_type", sa.String(30), nullable=True),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("total_score", sa.Float, nullable=True),
        sa.Column("feedback", JSONB, nullable=True),
        sa.Column("ai_comment", sa.Text, nullable=True),
        sa.Column("ta_comment", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    # 学习行为事件表
    op.create_table(
        "student_learning_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("event_metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )
    # 预警记录表
    op.create_table(
        "ta_alert_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("class_id", sa.String(36), sa.ForeignKey("ta_classes.id"), nullable=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=True),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(10), default="medium"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("ai_analysis", sa.Text, nullable=True),
        sa.Column("resolved", sa.Boolean, default=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ta_alert_records")
    op.drop_table("student_learning_events")
    op.drop_table("ta_grading_records")
    op.drop_table("ta_lesson_plans")
    op.drop_table("ta_class_students")
    op.drop_table("ta_classes")
