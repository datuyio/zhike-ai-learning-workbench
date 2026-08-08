from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass

import fitz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Course, Document, DocumentChunk
from app.schemas.common import Citation
from app.services.knowledge.local_embedding import LocalEmbeddingError, local_embedding_service


class LocalKnowledgeError(RuntimeError):
    """本地知识库解析、入库或检索失败。"""


@dataclass(frozen=True)
class ParsedChunk:
    """保留页码和章节线索的文本切片。"""

    page_no: int
    chunk_index: int
    content: str
    section_path: str | None


def _split_page(text: str, page_no: int, start_index: int) -> list[ParsedChunk]:
    # 清理 PDF 提取出的 NUL 空字符；PostgreSQL 不接受 0x00，否则入库会报 DataError
    text = text.replace("\x00", "")
    paragraphs = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"\n{2,}", text)]
    paragraphs = [part for part in paragraphs if part]
    chunks: list[ParsedChunk] = []
    buffer: list[str] = []
    length = 0
    index = start_index
    for paragraph in paragraphs:
        if buffer and length + len(paragraph) + 1 > settings.LOCAL_KNOWLEDGE_CHUNK_SIZE:
            content = " ".join(buffer).strip()
            chunks.append(ParsedChunk(page_no, index, content, None))
            index += 1
            overlap = content[-settings.LOCAL_KNOWLEDGE_CHUNK_OVERLAP :]
            buffer = [overlap, paragraph]
            length = len(overlap) + len(paragraph)
        else:
            buffer.append(paragraph)
            length += len(paragraph) + 1
    if buffer:
        chunks.append(ParsedChunk(page_no, index, " ".join(buffer).strip(), None))
    return chunks


def parse_pdf(content: bytes) -> list[ParsedChunk]:
    """使用 PyMuPDF 按页解析 PDF，并保留页码元数据。"""
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise LocalKnowledgeError(f"无法解析 PDF：{exc}") from exc
    chunks: list[ParsedChunk] = []
    try:
        for page_no, page in enumerate(document, start=1):
            chunks.extend(_split_page(page.get_text("text"), page_no, len(chunks)))
    finally:
        document.close()
    if not chunks:
        raise LocalKnowledgeError("PDF 未提取到可检索文本；扫描版 PDF 需要先进行 OCR。")
    return chunks


class LocalKnowledgeService:
    """基于本地 PDF、BGE Embedding 和 PostgreSQL pgvector 的知识库服务。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _course(self, course_slug: str) -> Course:
        course = self.db.scalar(select(Course).where(Course.slug == course_slug))
        if course is None:
            raise LocalKnowledgeError(f"课程不存在：{course_slug}")
        return course

    def ingest(self, course_slug: str, filename: str, mime_type: str | None, content: bytes, user_id: str) -> dict:
        """解析并写入本地知识库；不会调用或删除现有 ChatDoc 数据。"""
        if not filename.lower().endswith(".pdf"):
            raise LocalKnowledgeError("本地知识库当前只接受 PDF 文件。")
        if len(content) > settings.MAX_DOCUMENT_UPLOAD_BYTES:
            raise LocalKnowledgeError("文件超过上传大小限制。")
        course = self._course(course_slug)
        content_hash = hashlib.sha256(content).hexdigest()
        duplicate = self.db.scalar(select(Document).where(Document.course_id == course.id, Document.content_hash == content_hash, Document.deleted_at.is_(None), Document.source_type == "local_pgvector"))
        if duplicate is not None and settings.BLOCK_DUPLICATE_DOCUMENT_UPLOAD:
            raise LocalKnowledgeError(f"文档已存在：{duplicate.id}")
        parsed = parse_pdf(content)
        try:
            vectors = local_embedding_service.encode([chunk.content for chunk in parsed])
        except LocalEmbeddingError as exc:
            raise LocalKnowledgeError(str(exc)) from exc
        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        document = Document(
            course_id=course.id, uploaded_by_user_id=user_uuid, title=filename, filename=filename,
            mime_type=mime_type or "application/pdf", source_type="local_pgvector", parse_status="parsed",
            vector_status="ready", text_vector_status="ready", visual_vector_status="not_applicable",
            review_status="approved", publish_readiness="ready", content_hash=content_hash, source_hash=content_hash,
            parser_version="pymupdf-1.25", chunker_version="page-paragraph-v1",
            meta_json={"embedding_provider": "local", "embedding_model": settings.LOCAL_EMBEDDING_MODEL},
        )
        self.db.add(document)
        self.db.flush()
        for chunk, vector in zip(parsed, vectors, strict=True):
            chunk_hash = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
            self.db.add(DocumentChunk(
                document_id=document.id, course_id=course.id, chunk_index=chunk.chunk_index, page_no=chunk.page_no,
                section_path=chunk.section_path, content=chunk.content, raw_text=chunk.content, language="zh",
                content_hash=chunk_hash, lifecycle_status="active", embedding_status="ready", embedded_content_version=1,
                embedded_content_hash=chunk_hash, generation_id=uuid.uuid4().hex, token_count=len(chunk.content),
                parser_version="pymupdf-1.25", chunker_version="page-paragraph-v1",
                embedding_model=settings.LOCAL_EMBEDDING_MODEL, embedding_dim=settings.LOCAL_EMBEDDING_DIMENSION,
                embedding=vector,
            ))
        self.db.commit()
        return {"document_id": str(document.id), "course_id": course_slug, "course_title": course.title, "filename": filename,
                "parse_status": "parsed", "vector_status": "ready", "review_status": "approved", "publish_readiness": "ready",
                "message": f"本地知识库已完成解析、向量化和入库，共 {len(parsed)} 个切片。", "rag_backend": "local_pgvector"}

    def search(self, course_slug: str, query: str, limit: int, document_id: str | None = None) -> list[Citation]:
        """在课程范围内执行余弦相似度检索，并返回统一 Citation。"""
        course = self._course(course_slug)
        try:
            query_vector = local_embedding_service.encode([query])[0]
        except LocalEmbeddingError as exc:
            raise LocalKnowledgeError(str(exc)) from exc
        distance = DocumentChunk.embedding.cosine_distance(query_vector)
        statement = (select(DocumentChunk, Document, distance.label("distance")).join(Document, Document.id == DocumentChunk.document_id)
                     .where(DocumentChunk.course_id == course.id, DocumentChunk.lifecycle_status == "active", DocumentChunk.embedding_status == "ready", Document.deleted_at.is_(None))
                     .order_by(distance).limit(limit))
        if document_id:
            statement = statement.where(Document.id == uuid.UUID(document_id))
        rows = self.db.execute(statement).all()
        return [Citation(source_id=str(document.id), source_title=document.title, page_no=chunk.page_no, chunk_index=chunk.chunk_index,
                         local_chunk_id=str(chunk.id), chunk_id=str(chunk.id), provenance_source="local_pgvector", retrieval_mode="local_pgvector",
                         similarity=max(0.0, min(1.0, 1.0 - float(distance_value))), snippet=chunk.content[:settings.LOCAL_KNOWLEDGE_SNIPPET_SIZE],
                         content=chunk.content, section_path=chunk.section_path) for chunk, document, distance_value in rows]
