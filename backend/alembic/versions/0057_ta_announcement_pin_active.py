"""助教端公告增强：置顶与撤回字段

Revises: 0056_seed_ta_homework_scores
Create Date: 2026-08-06 00:00:00
"""
from alembic import op

revision = "0057_ta_announcement_pin_active"
down_revision = "0056_seed_ta_homework_scores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为公告补置顶/撤回字段（幂等补列，兼容存量库）。"""
    op.execute("ALTER TABLE ta_announcements ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN DEFAULT false")
    op.execute("ALTER TABLE ta_announcements ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true")


def downgrade() -> None:
    """回滚：删除新增列。"""
    op.execute("ALTER TABLE ta_announcements DROP COLUMN IF EXISTS is_pinned")
    op.execute("ALTER TABLE ta_announcements DROP COLUMN IF EXISTS is_active")
