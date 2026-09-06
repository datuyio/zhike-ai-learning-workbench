"""初始化课程级个性化学习平台基础表结构

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-25 17:00:00
"""
from alembic import op

from app.models import Base

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # op.execute("# CREATE EXTENSION IF NOT EXISTS vector -- disabled, no pgvector")  # disabled, no pgvector
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)