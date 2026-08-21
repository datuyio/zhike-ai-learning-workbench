"""助教端随堂测验：测验表、题目表与作答表

Revises: 0059_ta_alert_intervention
Create Date: 2026-08-07 00:00:00
"""
from alembic import op

revision = "0060_ta_quiz"
down_revision = "0059_ta_alert_intervention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """幂等建表，沿用 0051 风格。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ta_quizzes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ta_user_id UUID NOT NULL REFERENCES users(id),
            class_id UUID NOT NULL REFERENCES ta_classes(id),
            course_id UUID REFERENCES courses(id),
            title VARCHAR(300) NOT NULL,
            description TEXT,
            status VARCHAR(20) DEFAULT 'draft',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ta_quiz_questions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            quiz_id UUID NOT NULL REFERENCES ta_quizzes(id),
            order_index INTEGER DEFAULT 0,
            question_type VARCHAR(30) DEFAULT 'single_choice',
            prompt TEXT NOT NULL,
            options JSONB,
            answer VARCHAR(20) NOT NULL,
            score DOUBLE PRECISION DEFAULT 10
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ta_quiz_attempts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            quiz_id UUID NOT NULL REFERENCES ta_quizzes(id),
            student_id UUID NOT NULL REFERENCES users(id),
            answers JSONB,
            score DOUBLE PRECISION,
            submitted_at TIMESTAMP WITH TIME ZONE,
            grading_record_id UUID,
            CONSTRAINT uq_quiz_student UNIQUE (quiz_id, student_id)
        )
        """
    )


def downgrade() -> None:
    """回滚：删除三表。"""
    op.execute("DROP TABLE IF EXISTS ta_quiz_attempts")
    op.execute("DROP TABLE IF EXISTS ta_quiz_questions")
    op.execute("DROP TABLE IF EXISTS ta_quizzes")
