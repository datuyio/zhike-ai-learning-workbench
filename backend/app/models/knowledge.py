import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.models.base import Base, TimestampMixin, UUIDMixin


class Document(Base, UUIDMixin, TimestampMixin):
    """课程知识库中的原始文档记录。"""

    __tablename__ = "documents"

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(64), default="course_material")
    parse_status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    vector_status: Mapped[str] = mapped_column(String(32), default="pending_review", index=True)
    text_vector_status: Mapped[str] = mapped_column(String(32), default="pending_review", index=True)
    visual_vector_status: Mapped[str] = mapped_column(String(32), default="pending_review", index=True)
    review_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    publish_readiness: Mapped[str] = mapped_column(String(32), default="blocked", index=True)
    chapter_code: Mapped[str | None] = mapped_column(String(120))
    file_uri: Mapped[str | None] = mapped_column(String(500))
    content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    source_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    ingestion_version: Mapped[int] = mapped_column(Integer, default=1)
    current_parse_task_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    parser_version: Mapped[str | None] = mapped_column(String(120))
    chunker_version: Mapped[str | None] = mapped_column(String(120))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleanup_queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleanup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    pages = relationship("DocumentPage", back_populates="document", cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentPage(Base, UUIDMixin, TimestampMixin):
    """文档页级视觉资产和页摘要记录。"""

    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_no", name="uq_document_page_no"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    page_no: Mapped[int] = mapped_column(Integer)
    image_uri: Mapped[str | None] = mapped_column(String(500))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    dpi: Mapped[int | None] = mapped_column(Integer)
    lifecycle_status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    heading_candidates_json: Mapped[list] = mapped_column(JSONB, default=list)
    page_summary: Mapped[str | None] = mapped_column(Text())
    visual_content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    embedded_visual_content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    embedding_dim: Mapped[int | None] = mapped_column(Integer)
    embedding_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    visual_embedding_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    visual_embedding_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embedding_error: Mapped[str | None] = mapped_column(Text())
    generation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    meta_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    document = relationship("Document", back_populates="pages")


class DocumentChunk(Base, UUIDMixin, TimestampMixin):
    """文档解析后的可检索切片记录。"""

    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    concept_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("course_concepts.id", ondelete="SET NULL"), index=True)
    page_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document_pages.id", ondelete="SET NULL"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_no: Mapped[int | None] = mapped_column(Integer)
    section_path: Mapped[str | None] = mapped_column(String(255))
    asset_type: Mapped[str] = mapped_column(String(32), default="TEXT", index=True)
    heading_path_json: Mapped[list] = mapped_column(JSONB, default=list)
    heading_path_text: Mapped[str | None] = mapped_column(String(500), index=True)
    heading_ltree: Mapped[str | None] = mapped_column(String(500), index=True)
    heading_number: Mapped[str | None] = mapped_column(String(64), index=True)
    bbox_json: Mapped[list | None] = mapped_column(JSONB)
    bbox_norm_json: Mapped[list | None] = mapped_column(JSONB)
    content: Mapped[str] = mapped_column(Text())
    raw_text: Mapped[str | None] = mapped_column(Text())
    language: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    embedding_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    content_version: Mapped[int] = mapped_column(Integer, default=1)
    embedded_content_version: Mapped[int | None] = mapped_column(Integer)
    embedded_content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    embedding_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embedding_error: Mapped[str | None] = mapped_column(Text())
    generation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    reading_order_index: Mapped[int | None] = mapped_column(Integer)
    logical_table_id: Mapped[str | None] = mapped_column(String(120), index=True)
    visual_summary: Mapped[str | None] = mapped_column(Text())
    parser_version: Mapped[str | None] = mapped_column(String(120), index=True)
    chunker_version: Mapped[str | None] = mapped_column(String(120), index=True)
    embedding_model: Mapped[str] = mapped_column(String(120), default="bge-m3")
    embedding_dim: Mapped[int] = mapped_column(Integer, default=1024)
    # 当前本地 BGE 方案固定使用 512 维；云端 ChatDoc 仍使用原有链路。
    embedding: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)
    anchor_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    quality_score: Mapped[float] = mapped_column(default=0.0)
    quality_rule_version: Mapped[str] = mapped_column(String(64), default="quality-v1", index=True)
    quality_reasons_json: Mapped[list] = mapped_column(JSONB, default=list)
    quality_ignored: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    quality_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document = relationship("Document", back_populates="chunks")


class ChunkRegion(Base, UUIDMixin, TimestampMixin):
    """切片在原文页面中的区域定位记录。"""

    __tablename__ = "chunk_regions"
    __table_args__ = (
        UniqueConstraint("chunk_id", "region_index", name="uq_chunk_region_index"),
    )

    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    page_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document_pages.id", ondelete="SET NULL"))
    page_no: Mapped[int] = mapped_column(nullable=False, index=True)
    bbox_norm: Mapped[list[float]] = mapped_column(JSONB, nullable=False)
    bbox: Mapped[list[float] | None] = mapped_column(JSONB)
    region_index: Mapped[int] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="parser")
    asset_type: Mapped[str | None] = mapped_column(String(32))
    meta_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class ChunkDuplicateCandidate(Base, UUIDMixin, TimestampMixin):
    """切片重复候选关系及人工审核状态。"""

    __tablename__ = "chunk_duplicate_candidates"
    __table_args__ = (UniqueConstraint("chunk_id", "candidate_chunk_id", "method", name="uq_chunk_duplicate_candidate_method"),)

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True)
    candidate_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    candidate_chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    reason_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChunkQualityFeedback(Base, UUIDMixin, TimestampMixin):
    """切片质量评分和人工反馈记录。"""

    __tablename__ = "chunk_quality_feedback"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document_chunks.id", ondelete="SET NULL"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    rule_code: Mapped[str | None] = mapped_column(String(120), index=True)
    quality_rule_version: Mapped[str | None] = mapped_column(String(64), index=True)
    note: Mapped[str | None] = mapped_column(Text())
    before_score: Mapped[float | None] = mapped_column(Float)
    after_score: Mapped[float | None] = mapped_column(Float)
    meta_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class DocumentParseTask(Base, UUIDMixin, TimestampMixin):
    """文档解析入库后台任务状态。"""

    __tablename__ = "document_parse_tasks"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(64), default="queued", index=True)
    error_message: Mapped[str | None] = mapped_column(Text())
    progress: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=900)
    worker_id: Mapped[str | None] = mapped_column(String(120), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(120), index=True)
    result_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class VectorIndex(Base, UUIDMixin, TimestampMixin):
    """课程向量索引元数据记录。"""

    __tablename__ = "vector_indexes"

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    embedding_model: Mapped[str] = mapped_column(String(120))
    embedding_dim: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="ready")
    meta_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class VectorizationTask(Base, UUIDMixin, TimestampMixin):
    """文档或课程范围的向量化后台任务状态。"""

    __tablename__ = "vectorization_tasks"

    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vectorization_tasks.id", ondelete="SET NULL"), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), index=True)
    scope_id: Mapped[str] = mapped_column(String(120), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(64), default="queued", index=True)
    mode: Mapped[str] = mapped_column(String(32), default="stale_only")
    include_pages: Mapped[bool] = mapped_column(Boolean, default=True)
    clear_old: Mapped[bool] = mapped_column(Boolean, default=False)
    generation_id: Mapped[str] = mapped_column(String(64), index=True)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=1800)
    worker_id: Mapped[str | None] = mapped_column(String(120), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(120), index=True)
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    succeeded_items: Mapped[int] = mapped_column(Integer, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, default=0)
    stale_skipped_items: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text())
    result_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class TaskEvent(Base, UUIDMixin, TimestampMixin):
    """后台任务阶段事件和可观测性指标。"""

    __tablename__ = "task_events"

    task_id: Mapped[str] = mapped_column(String(120), index=True)
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    stage: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    message: Mapped[str | None] = mapped_column(Text())
    worker_id: Mapped[str | None] = mapped_column(String(120), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(120), index=True)
    metrics_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class RetrievalVerificationQuestion(Base, UUIDMixin, TimestampMixin):
    """检索验证题目及期望命中条件。"""

    __tablename__ = "retrieval_verification_questions"

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text())
    expected_concept_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("course_concepts.id", ondelete="SET NULL"), index=True)
    expected_heading_text: Mapped[str | None] = mapped_column(String(500), index=True)
    min_similarity: Mapped[float] = mapped_column(Float, default=0.55)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    meta_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class RetrievalVerificationRun(Base, UUIDMixin, TimestampMixin):
    """检索验证批次运行状态和聚合指标。"""

    __tablename__ = "retrieval_verification_runs"

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    vectorization_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vectorization_tasks.id", ondelete="SET NULL"), index=True)
    generation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(64), default="queued", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(120), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(120), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=900)
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    passed_questions: Mapped[int] = mapped_column(Integer, default=0)
    top_k_hit_rate: Mapped[float] = mapped_column(Float, default=0.0)
    citation_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    low_confidence_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_top_score: Mapped[float] = mapped_column(Float, default=0.0)
    error_summary: Mapped[str | None] = mapped_column(Text())
    result_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class KnowledgePublishGeneration(Base, UUIDMixin, TimestampMixin):
    """知识库发布代际和回滚关联记录。"""

    __tablename__ = "knowledge_publish_generations"
    __table_args__ = (UniqueConstraint("course_id", "generation_id", name="uq_course_publish_generation"),)

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    generation_id: Mapped[str] = mapped_column(String(64), index=True)
    previous_generation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="candidate", index=True)
    vectorization_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vectorization_tasks.id", ondelete="SET NULL"), index=True)
    verification_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("retrieval_verification_runs.id", ondelete="SET NULL"), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metrics_json: Mapped[dict] = mapped_column(JSONB, default=dict)
