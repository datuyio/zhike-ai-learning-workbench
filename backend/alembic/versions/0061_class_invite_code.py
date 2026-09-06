"""增加班级邀请码字段，支持学生凭码入班。

Revision ID: 0061_class_invite_code
Revises: 0060_ta_quiz
"""
import secrets

import sqlalchemy as sa
from alembic import op

revision = "0061_class_invite_code"
down_revision = "0060_ta_quiz"
branch_labels = None
depends_on = None

# 邀请码字符集：去掉易混淆的 0/O/1/I/L
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _generate_code() -> str:
    """生成 8 位随机邀请码。"""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))


def upgrade() -> None:
    """增加班级邀请码字段（幂等）。

    0001_initial_schema 通过 Base.metadata.create_all 建表时，会按当前模型定义
    （TaClass.invite_code 唯一非空）直接建出该列，因此这里需先探测列是否存在，
    已存在则跳过，避免重复加列报错。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [c["name"] for c in inspector.get_columns("ta_classes")]
    if "invite_code" in existing_columns:
        return
    # 先加可空列，回填存量班级，再收紧为唯一非空。
    op.add_column("ta_classes", sa.Column("invite_code", sa.String(length=16), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, invite_code FROM ta_classes")).fetchall()
    for row in rows:
        if row[1]:
            continue
        conn.execute(
            sa.text("UPDATE ta_classes SET invite_code = :code WHERE id = :id"),
            {"code": _generate_code(), "id": row[0]},
        )
    op.alter_column("ta_classes", "invite_code", existing_type=sa.String(length=16), nullable=False)
    op.create_unique_constraint("uq_ta_classes_invite_code", "ta_classes", ["invite_code"])


def downgrade() -> None:
    op.drop_constraint("uq_ta_classes_invite_code", "ta_classes", type_="unique")
    op.drop_column("ta_classes", "invite_code")
