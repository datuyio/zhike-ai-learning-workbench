"""为本地知识库增加 pgvector 向量列

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-08

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0046_local_pgvector_embedding"
down_revision: Union[str, None] = "0045_ta_portal_base"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """给已有本地切片表增加可选的 512 维向量列，不影响 ChatDoc 旧数据。

    注意：0001_initial_schema 通过 Base.metadata.create_all 建表时，已按模型定义
    （DocumentChunk.embedding = Vector(512)）创建了该列，因此这里必须用
    IF NOT EXISTS 兜底，避免重复加列导致 DuplicateColumn 报错。
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding vector(512)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_local_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    """移除本地向量索引和向量列，保留原有文档与 ChatDoc 元数据。"""
    op.drop_index("ix_document_chunks_local_embedding_hnsw", table_name="document_chunks")
    op.drop_column("document_chunks", "embedding")
