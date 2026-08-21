"""助教端基础表与扩展字段

本迁移对存量库采用 IF NOT EXISTS 补丁式建表：若预存表缺失其他列（结构早于模型），本迁移不会自动补齐，后续模型变更需继续按『迁移补列』惯例处理。

Revision ID: 0045_ta_portal_base
Revises: 0044_fix_admin_password_hash
Create Date: 2026-08-05 00:00:00
"""
from alembic import op

revision = "0045_ta_portal_base"
down_revision = "0044_fix_admin_password_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """幂等创建助教端基础表与公告表，并为批改记录补充学生提交内容列。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ta_classes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(200) NOT NULL,
            description TEXT,
            course_id UUID REFERENCES courses(id),
            ta_user_id UUID NOT NULL REFERENCES users(id),
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ta_class_students (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            class_id UUID NOT NULL REFERENCES ta_classes(id),
            student_id UUID NOT NULL REFERENCES users(id),
            joined_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ta_lesson_plans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title VARCHAR(300) NOT NULL,
            course_id UUID REFERENCES courses(id),
            chapter VARCHAR(200),
            content JSONB,
            outline TEXT,
            created_by UUID NOT NULL REFERENCES users(id),
            version INTEGER NOT NULL DEFAULT 1,
            is_published BOOLEAN DEFAULT false,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ta_grading_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title VARCHAR(300) NOT NULL,
            student_id UUID NOT NULL REFERENCES users(id),
            course_id UUID REFERENCES courses(id),
            class_id UUID REFERENCES ta_classes(id),
            grader_type VARCHAR(20) NOT NULL DEFAULT 'ai_assisted',
            question_type VARCHAR(30),
            score DOUBLE PRECISION,
            total_score DOUBLE PRECISION,
            feedback JSONB,
            ai_comment TEXT,
            ta_comment TEXT,
            student_answer TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ta_alert_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id UUID NOT NULL REFERENCES users(id),
            class_id UUID REFERENCES ta_classes(id),
            course_id UUID REFERENCES courses(id),
            alert_type VARCHAR(50) NOT NULL,
            severity VARCHAR(10) NOT NULL DEFAULT 'medium',
            title VARCHAR(200) NOT NULL,
            description TEXT,
            ai_analysis TEXT,
            resolved BOOLEAN NOT NULL DEFAULT false,
            resolved_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS student_learning_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id UUID NOT NULL REFERENCES users(id),
            course_id UUID REFERENCES courses(id),
            event_type VARCHAR(50) NOT NULL,
            event_metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_student_learning_events_created_at ON student_learning_events (created_at)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ta_announcements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title VARCHAR(300) NOT NULL,
            body TEXT NOT NULL,
            announcement_type VARCHAR(30) NOT NULL DEFAULT 'general',
            class_id UUID REFERENCES ta_classes(id),
            created_by UUID NOT NULL REFERENCES users(id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    # 存量库中 ta_grading_records 可能已存在且无该列，用 IF NOT EXISTS 幂等补充
    op.execute("ALTER TABLE ta_grading_records ADD COLUMN IF NOT EXISTS student_answer TEXT")


def downgrade() -> None:
    """回滚：删除公告表与新增列。

    注：ta_classes 等 6 张基础表对存量库是预存表（0001 脚手架或手工创建），
    并非本迁移真正新增，downgrade 不删除它们，避免误删预存数据。
    全新库场景下回滚会遗留这 6 张空表，属可接受的取舍。
    """
    op.execute("DROP TABLE IF EXISTS ta_announcements")
    op.execute("ALTER TABLE ta_grading_records DROP COLUMN IF EXISTS student_answer")
