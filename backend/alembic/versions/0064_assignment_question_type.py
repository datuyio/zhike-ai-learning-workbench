"""作业支持题型（主观/客观）与批改参考标准。

Revision ID: 0064_assignment_question_type
Revises: 0063_student_seed_passwords
"""
import sqlalchemy as sa
from alembic import op

revision = "0064_assignment_question_type"
down_revision = "0063_student_seed_passwords"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为作业补充题型/选项/标准答案字段，为批改记录补充参考答案字段（幂等）。"""
    op.add_column(
        "ta_assignments",
        sa.Column("question_type", sa.String(30), nullable=False, server_default="short_answer", comment="题型: short_answer/code/single_choice/true_false 等"),
    )
    op.add_column("ta_assignments", sa.Column("options", sa.JSON(), nullable=True, comment="客观题选项数组，主观题为空"))
    op.add_column("ta_assignments", sa.Column("correct_answer", sa.String(20), nullable=True, comment="客观题标准答案，主观题为空"))
    op.add_column("ta_grading_records", sa.Column("reference_answer", sa.Text(), nullable=True, comment="AI 批改参考/标准答案"))


def downgrade() -> None:
    """回滚删除新增列。"""
    op.drop_column("ta_assignments", "correct_answer")
    op.drop_column("ta_assignments", "options")
    op.drop_column("ta_assignments", "question_type")
    op.drop_column("ta_grading_records", "reference_answer")
