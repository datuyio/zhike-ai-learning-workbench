"""教师端 AI 助手待确认写操作表。

教师端 Agent 的写操作（布置作业、创建测验、发布公告等）先落一条待确认记录，
教师确认后由确认端点真正执行；避免 Agent 未经确认直接产生副作用。

Revision ID: 0066_ta_agent_confirmations
Revises: 0065_assignment_multi_questions
"""
import sqlalchemy as sa
from alembic import op

revision = "0066_ta_agent_confirmations"
down_revision = "0065_assignment_multi_questions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """建待确认写操作表。"""
    op.create_table(
        "ta_agent_confirmations",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", sa.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=True),
        sa.Column("ta_user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tool", sa.String(120), nullable=False, comment="待执行的工具名"),
        sa.Column("args_json", sa.JSON(), nullable=False, comment="工具参数（确认后执行）"),
        sa.Column("summary", sa.Text(), nullable=False, comment="待确认操作的一句话说明"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", comment="pending/confirmed/cancelled"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    """回滚删除待确认表。"""
    op.drop_table("ta_agent_confirmations")
