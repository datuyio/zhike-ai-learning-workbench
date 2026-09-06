"""助教端整合迁移：存量 varchar(36) 主外键转原生 UUID，补齐公告表与批改补充列

Revision ID: 0053_ta_portal_integration
Revises: 0046_local_pgvector_embedding
Create Date: 2026-08-16 00:00:00
"""
from alembic import op

revision = "0053_ta_portal_integration"
down_revision = "0046_local_pgvector_embedding"
branch_labels = None
depends_on = None

# 存量 varchar(36) 主外键列清单：表名 -> 需转 UUID 的列
_VARCHAR_UUID_COLUMNS = {
    "ta_classes": ["id"],
    "ta_class_students": ["id", "class_id"],
    "ta_lesson_plans": ["id"],
    "ta_grading_records": ["id", "class_id"],
    "ta_alert_records": ["id", "class_id"],
    "student_learning_events": ["id"],
}

# 引用 ta_classes(id) 的外键约束清单
_CLASS_ID_FKS = {
    "ta_class_students": "ta_class_students_class_id_fkey",
    "ta_grading_records": "ta_grading_records_class_id_fkey",
    "ta_alert_records": "ta_alert_records_class_id_fkey",
}


def upgrade() -> None:
    """把存量 varchar(36) 主外键转换为原生 UUID，并补齐缺失的公告表与批改列。

    转换前先删除依赖外键，转换后重建；新库场景下列已是 UUID，本迁移自动变成幂等空操作。
    """
    # 1) 删除引用 varchar 主键的外键约束
    for constraint in _CLASS_ID_FKS.values():
        op.execute(f"ALTER TABLE {constraint.rsplit('_class_id_fkey', 1)[0]} DROP CONSTRAINT IF EXISTS {constraint}")
    # 2) varchar -> uuid（列已是 uuid 时 USING 强转仍可安全执行，天然幂等）
    for table, columns in _VARCHAR_UUID_COLUMNS.items():
        for column in columns:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE UUID USING {column}::uuid")
    # 3) 重建外键
    for table, constraint in _CLASS_ID_FKS.items():
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
            "FOREIGN KEY (class_id) REFERENCES ta_classes(id)"
        )
    # 4) 补齐公告表（feature 0045 已含，本地 0045 缺失）
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
    # 5) 批改记录补学生提交内容列（feature 0045 已含，本地 0045 缺失）
    op.execute("ALTER TABLE ta_grading_records ADD COLUMN IF NOT EXISTS student_answer TEXT")


def downgrade() -> None:
    """回滚：移除公告表与补充列，并把 UUID 列退回 varchar(36)。"""
    op.execute("DROP TABLE IF EXISTS ta_announcements")
    op.execute("ALTER TABLE ta_grading_records DROP COLUMN IF EXISTS student_answer")
    for constraint in _CLASS_ID_FKS.values():
        op.execute(f"ALTER TABLE {constraint.rsplit('_class_id_fkey', 1)[0]} DROP CONSTRAINT IF EXISTS {constraint}")
    for table, columns in _VARCHAR_UUID_COLUMNS.items():
        for column in columns:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE VARCHAR(36) USING {column}::text")
    for table, constraint in _CLASS_ID_FKS.items():
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
            "FOREIGN KEY (class_id) REFERENCES ta_classes(id)"
        )
