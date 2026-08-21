"""助教端 P1 增强：班级容量上限与批改重交/逾期字段

Revises: 0054_seed_ta_demo_data
Create Date: 2026-08-06 00:00:00
"""
from alembic import op

revision = "0055_ta_portal_p1"
down_revision = "0054_seed_ta_demo_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为班级补容量字段，为批改记录补重交/逾期字段（幂等补列，兼容存量库）。"""
    op.execute("ALTER TABLE ta_classes ADD COLUMN IF NOT EXISTS max_students INTEGER")
    op.execute("ALTER TABLE ta_grading_records ADD COLUMN IF NOT EXISTS attempt_number INTEGER DEFAULT 0")
    op.execute("ALTER TABLE ta_grading_records ADD COLUMN IF NOT EXISTS is_late BOOLEAN DEFAULT false")
    op.execute("ALTER TABLE ta_grading_records ADD COLUMN IF NOT EXISTS late_penalty DOUBLE PRECISION")


def downgrade() -> None:
    """回滚：删除新增列。"""
    op.execute("ALTER TABLE ta_classes DROP COLUMN IF EXISTS max_students")
    op.execute("ALTER TABLE ta_grading_records DROP COLUMN IF EXISTS attempt_number")
    op.execute("ALTER TABLE ta_grading_records DROP COLUMN IF EXISTS is_late")
    op.execute("ALTER TABLE ta_grading_records DROP COLUMN IF EXISTS late_penalty")
