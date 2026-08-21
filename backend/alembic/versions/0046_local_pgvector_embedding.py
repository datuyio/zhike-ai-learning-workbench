"""为本地知识库增加 pgvector 向量列

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "0046_local_pgvector_embedding"
down_revision: Union[str, None] = "0045_ta_portal_base"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """给已有本地切片表增加可选的 512 维向量列，不影响 ChatDoc 旧数据。"""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("document_chunks", sa.Column("embedding", Vector(512), nullable=True))
    op.create_index(
        "ix_document_chunks_local_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """移除本地向量索引和向量列，保留原有文档与 ChatDoc 元数据。"""
    op.drop_index("ix_document_chunks_local_embedding_hnsw", table_name="document_chunks")
    op.drop_column("document_chunks", "embedding")
