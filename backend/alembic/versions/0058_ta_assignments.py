"""助教端作业发布：作业表、提交表与批改记录知识点列

Revises: 0057_ta_announcement_pin_active
Create Date: 2026-08-06 00:00:00
"""
from alembic import op

revision = "0058_ta_assignments"
down_revision = "0057_ta_announcement_pin_active"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """幂等建表 + 补列，沿用 0045 风格。"""
    op.execute("ALTER TABLE ta_grading_records ADD COLUMN IF NOT EXISTS concept_id UUID")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ta_assignments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ta_user_id UUID NOT NULL REFERENCES users(id),
            class_id UUID NOT NULL REFERENCES ta_classes(id),
            course_id UUID REFERENCES courses(id),
            concept_id UUID REFERENCES course_concepts(id),
            title VARCHAR(300) NOT NULL,
            description TEXT,
            total_score DOUBLE PRECISION DEFAULT 100,
            due_at TIMESTAMP WITH TIME ZONE,
            late_policy VARCHAR(20) DEFAULT 'allow_penalty',
            late_penalty_ratio DOUBLE PRECISION DEFAULT 0.1,
            status VARCHAR(20) DEFAULT 'draft',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ta_submissions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            assignment_id UUID NOT NULL REFERENCES ta_assignments(id),
            student_id UUID NOT NULL REFERENCES users(id),
            answer TEXT NOT NULL,
            submitted_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            is_late BOOLEAN DEFAULT false,
            attempt_number INTEGER DEFAULT 1,
            grading_record_id UUID REFERENCES ta_grading_records(id),
            CONSTRAINT uq_assignment_student UNIQUE (assignment_id, student_id)
        )
        """
    )


def downgrade() -> None:
    """回滚：删除新表与新增列。"""
    op.execute("DROP TABLE IF EXISTS ta_submissions")
    op.execute("DROP TABLE IF EXISTS ta_assignments")
    op.execute("ALTER TABLE ta_grading_records DROP COLUMN IF EXISTS concept_id")
