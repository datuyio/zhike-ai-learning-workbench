"""助教端预警干预闭环：干预记录表与学生通知表

Revises: 0058_ta_assignments
Create Date: 2026-08-07 00:00:00
"""
from alembic import op

revision = "0059_ta_alert_intervention"
down_revision = "0058_ta_assignments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """幂等建表，沿用 0050 风格。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ta_notifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id UUID NOT NULL REFERENCES users(id),
            class_id UUID REFERENCES ta_classes(id),
            title VARCHAR(300) NOT NULL,
            body TEXT NOT NULL,
            notification_type VARCHAR(30) NOT NULL,
            source_type VARCHAR(30) NOT NULL,
            source_id VARCHAR(100),
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ta_alert_actions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            alert_id UUID NOT NULL REFERENCES ta_alert_records(id),
            created_by UUID NOT NULL REFERENCES users(id),
            action_type VARCHAR(30) NOT NULL,
            content TEXT,
            target_student_id UUID REFERENCES users(id),
            resource_ids JSONB,
            tutoring_time TIMESTAMP WITH TIME ZONE,
            notification_id UUID,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    """回滚：删除两表。"""
    op.execute("DROP TABLE IF EXISTS ta_alert_actions")
    op.execute("DROP TABLE IF EXISTS ta_notifications")
