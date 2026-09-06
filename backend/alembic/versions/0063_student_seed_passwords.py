"""为学生演示账号设置登录密码。

Revision ID: 0063_student_seed_passwords
Revises: 0062_ta_question_bank
"""
import os

import sqlalchemy as sa
from alembic import op
from argon2 import PasswordHasher

_password_hasher = PasswordHasher()

revision = "0063_student_seed_passwords"
down_revision = "0062_ta_question_bank"
branch_labels = None
depends_on = None

# 0054 种入的 6 个演示学生账号；密码默认 student123，可用 SEED_STUDENT_PASSWORD 覆盖
STUDENT_EMAILS = [f"student{i}@example.edu.cn" for i in range(1, 7)]


def upgrade() -> None:
    """为尚无密码的学生演示账号写入 Argon2id 密码哈希（幂等，仅补空密码账号）。"""
    password = os.getenv("SEED_STUDENT_PASSWORD") or "student123"
    bind = op.get_bind()
    for email in STUDENT_EMAILS:
        bind.execute(
            sa.text(
                """
                UPDATE users
                SET password_hash = :hash
                WHERE email = :email AND (password_hash IS NULL OR password_hash = '')
                """
            ),
            {"hash": _password_hasher.hash(password), "email": email},
        )


def downgrade() -> None:
    """回滚：将学生账号密码清空（恢复迁移前状态，仅供本地开发回滚）。"""
    bind = op.get_bind()
    for email in STUDENT_EMAILS:
        bind.execute(
            sa.text("UPDATE users SET password_hash = NULL WHERE email = :email"),
            {"email": email},
        )
