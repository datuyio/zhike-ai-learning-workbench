from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import fitz
import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy import func, or_, select
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
    heading_path: list[str]
    heading_number: str | None = None


def _split_sentences(text: str) -> list[str]:
    """按中英文句末标点切分为完整句子，保留标点。"""
    # 中文句末标点：。！？； 英文句末标点：.!? 以及换行符
    parts = re.split(r"(?<=[。！？；.!?\n])\s*", text)
    return [p.strip() for p in parts if p.strip()]


def _take_tail_sentences(sentences: list[str], min_chars: int) -> list[str]:
    """从句子列表末尾取出足够覆盖 min_chars 的完整句子，不截断句子。"""
    tail: list[str] = []
    chars = 0
    for s in reversed(sentences):
        tail.insert(0, s)
        chars += len(s)
        if chars >= min_chars:
            break
    return tail


def _split_page(text: str, page_no: int, start_index: int) -> list[ParsedChunk]:
    # 清理 PDF 提取出的 NUL 空字符；PostgreSQL 不接受 0x00，否则入库会报 DataError
    text = text.replace("\x00", "")
    sentences = _split_sentences(text)
    chunks: list[ParsedChunk] = []
    buffer: list[str] = []
    length = 0
    index = start_index
    for sentence in sentences:
        if buffer and length + len(sentence) + 1 > settings.LOCAL_KNOWLEDGE_CHUNK_SIZE:
            # 当前 buffer 累积达到 chunk_size，写入一个 chunk
            content = "".join(buffer).strip()
            chunks.append(ParsedChunk(page_no, index, content, None, []))
            index += 1
            # 取尾部完整句子作为 overlap，不截断句子
            tail = _take_tail_sentences(buffer, settings.LOCAL_KNOWLEDGE_CHUNK_OVERLAP)
            buffer = tail + [sentence]
            length = sum(len(s) for s in tail) + len(sentence) + 1
        else:
            buffer.append(sentence)
            length += len(sentence) + 1
    if buffer:
        chunks.append(ParsedChunk(page_no, index, "".join(buffer).strip(), None, []))
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


_MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_HEADING_NUMBER_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s*")


def _strip_frontmatter(text: str) -> str:
    """移除 Markdown 开头的 YAML frontmatter，保留正文。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        return normalized
    body = normalized[4:]
    match = re.search(r"(?m)^---\s*$", body)
    return body[match.end() :] if match else body


def _clean_markdown_content(text: str) -> str:
    """移除 Markdown 中的导航噪音，并尽量保留代码与解释内容。"""
    text = text.replace("\x00", "")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(?m)^[-*_]{3,}\s*$", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _heading_number(title: str) -> str | None:
    """提取标题开头的章节编号，例如 3.2。"""
    match = _HEADING_NUMBER_PATTERN.match(title)
    return match.group(1) if match else None


def _markdown_blocks(text: str) -> list[dict]:
    """把 Markdown 按标题层级拆成带层级路径的正文块。"""
    blocks: list[dict] = []
    heading_stack: list[str] = []
    current: dict | None = None

    for raw_line in text.splitlines():
        heading_match = _MARKDOWN_HEADING_PATTERN.match(raw_line.strip())
        if not heading_match:
            if current is not None:
                current["lines"].append(raw_line)
            else:
                current = {
                    "heading_level": 0,
                    "title": None,
                    "heading_path": [],
                    "heading_number": None,
                    "lines": [raw_line],
                }
            continue

        if current is not None:
            blocks.append(current)
        level = len(heading_match.group(1))
        title = heading_match.group(2).strip()
        if level <= len(heading_stack):
            heading_stack = heading_stack[: level - 1]
        heading_stack.append(title)
        current = {
            "heading_level": level,
            "title": title,
            "heading_path": list(heading_stack),
            "heading_number": _heading_number(title),
            "lines": [],
        }

    if current is not None:
        blocks.append(current)
    return blocks


def _chunks_for_markdown_block(block: dict, start_index: int) -> list[ParsedChunk]:
    """把单个 Markdown 标题块切分为带章节路径的可检索切片。"""
    body = _clean_markdown_content("\n".join(block["lines"]))
    if not body:
        return []

    title = block.get("title")
    heading_path = list(block.get("heading_path") or [])
    heading_number = block.get("heading_number")
    section_path = " / ".join(heading_path) if heading_path else None
    level = int(block.get("heading_level") or 0)
    prefix = f"{'#' * level} {title}\n" if title else ""

    body_chunks = _split_page(body, 1, start_index)
    chunks: list[ParsedChunk] = []
    for index, body_chunk in enumerate(body_chunks):
        content = prefix + body_chunk.content if index == 0 else body_chunk.content
        content = content.strip()
        if len(content) < 24:
            continue
        chunks.append(
            ParsedChunk(
                page_no=1,
                chunk_index=body_chunk.chunk_index,
                content=content,
                section_path=section_path,
                heading_path=heading_path,
                heading_number=heading_number,
            )
        )
    return chunks


def parse_markdown(content: bytes) -> list[ParsedChunk]:
    """解析 Markdown/MDX 正文，按标题层级保留章节路径。"""
    try:
        text = _strip_frontmatter(content.decode("utf-8-sig", errors="replace"))
    except Exception as exc:
        raise LocalKnowledgeError(f"无法解码 Markdown 文件：{exc}") from exc

    chunks: list[ParsedChunk] = []
    block_start = 0
    for block in _markdown_blocks(text):
        block_chunks = _chunks_for_markdown_block(block, block_start)
        chunks.extend(block_chunks)
        block_start += len(block_chunks)

    if not chunks:
        fallback = _split_page(_clean_markdown_content(text), 1, 0)
        chunks = [
            ParsedChunk(
                page_no=1,
                chunk_index=item.chunk_index,
                content=item.content,
                section_path=None,
                heading_path=[],
            )
            for item in fallback
            if len(item.content.strip()) >= 24
        ]
    if not chunks:
        raise LocalKnowledgeError("Markdown 未提取到可检索文本。")
    return chunks


@dataclass
class _Bm25Index:
    """某课程的 BM25 索引及其对应的切片内容，用于混合检索。"""

    bm25: BM25Okapi
    chunk_ids: list[str]                        # 与 BM25 词表顺序一致的 chunk_id 列表
    chunk_map: dict[str, DocumentChunk]          # chunk_id -> DocumentChunk 快速查找
    doc_map: dict[str, Document]                 # document_id -> Document 快速查找


# 课程级 BM25 索引缓存；文档发生变更时按课程失效，避免每次检索都重建
_bm25_cache: dict[str, _Bm25Index] = {}


def _tokenize(text: str) -> list[str]:
    """使用 jieba 对文本分词，兼顾中英文关键词。"""
    return [token for token in jieba.cut(text) if token.strip()]


def _fit_column_text(value: str | None, max_length: int) -> str | None:
    """按数据库列宽截断路径文本，同时完整保留 JSON 中的原始标题路径。"""
    if not value:
        return value
    return value[:max_length]


def _build_bm25_index(db: Session, course_id) -> _Bm25Index:
    """从数据库加载课程的活跃切片并构建 BM25 索引。"""
    rows = db.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.course_id == course_id,
            DocumentChunk.lifecycle_status == "active",
            DocumentChunk.embedding_status == "ready",
            Document.deleted_at.is_(None),
        )
        .order_by(DocumentChunk.id)
    ).all()
    chunk_ids: list[str] = []
    chunk_map: dict[str, DocumentChunk] = {}
    doc_map: dict[str, Document] = {}
    corpus: list[list[str]] = []
    for chunk, doc in rows:
        cid = str(chunk.id)
        did = str(doc.id)
        chunk_ids.append(cid)
        chunk_map[cid] = chunk
        doc_map[did] = doc
        corpus.append(_tokenize(chunk.content))
    return _Bm25Index(bm25=BM25Okapi(corpus), chunk_ids=chunk_ids, chunk_map=chunk_map, doc_map=doc_map)


def _invalidate_bm25_cache(course_id) -> None:
    """文档入库后按课程失效 BM25 索引缓存。"""
    _bm25_cache.pop(str(course_id), None)


class LocalKnowledgeService:
    """基于本地 PDF、BGE Embedding 和 PostgreSQL pgvector 的知识库服务。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _course(self, course_id_or_slug: str) -> Course:
        clauses = [Course.slug == course_id_or_slug]
        try:
            clauses.append(Course.id == uuid.UUID(str(course_id_or_slug)))
        except (TypeError, ValueError):
            pass
        course = self.db.scalar(select(Course).where(or_(*clauses)))
        if course is None:
            raise LocalKnowledgeError(f"课程不存在：{course_id_or_slug}")
        return course

    def readiness(self, course_id_or_slug: str) -> dict:
        """返回本地 pgvector 后端是否已有可直接检索的文档和向量切片。"""
        course = self._course(course_id_or_slug)
        document_count = self.db.scalar(
            select(func.count(Document.id)).where(
                Document.course_id == course.id,
                Document.source_type == "local_pgvector",
                Document.parse_status.in_({"parsed", "completed"}),
                Document.vector_status == "ready",
                Document.deleted_at.is_(None),
            )
        ) or 0
        chunk_count = self.db.scalar(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.course_id == course.id,
                DocumentChunk.lifecycle_status == "active",
                DocumentChunk.embedding_status == "ready",
                DocumentChunk.embedding.is_not(None),
            )
        ) or 0
        return {
            "course_id": course.slug,
            "course_title": course.title,
            "ready": int(document_count) > 0 and int(chunk_count) > 0,
            "document_count": int(document_count),
            "chunk_count": int(chunk_count),
        }

    def ingest(
        self,
        course_slug: str,
        filename: str,
        mime_type: str | None,
        content: bytes,
        user_id: str,
        *,
        source_meta_json: dict | None = None,
        source_path: str | None = None,
    ) -> dict:
        """解析 PDF/Markdown 并写入本地知识库，不调用或删除 ChatDoc 数据。"""
        if len(content) > settings.MAX_DOCUMENT_UPLOAD_BYTES:
            raise LocalKnowledgeError("文件超过上传大小限制。")
        suffix = Path(filename).suffix.lower()
        if suffix == ".pdf":
            parsed = parse_pdf(content)
            parser_version = "pymupdf-1.25"
            fallback_mime = "application/pdf"
        elif suffix in {".md", ".markdown", ".mdx", ".txt", ".text"}:
            parsed = parse_markdown(content)
            parser_version = "markdown-heading-v1"
            fallback_mime = "text/markdown"
        else:
            raise LocalKnowledgeError("本地知识库仅支持 PDF、Markdown、MDX 和纯文本文件。")

        course = self._course(course_slug)
        content_hash = hashlib.sha256(content).hexdigest()
        source_meta = dict(source_meta_json or {})
        source_hash = str(source_meta.get("sha256") or content_hash)
        duplicate = self.db.scalar(
            select(Document).where(
                Document.course_id == course.id,
                Document.content_hash == content_hash,
                Document.deleted_at.is_(None),
                Document.source_type == "local_pgvector",
            )
        )
        if duplicate is not None and settings.BLOCK_DUPLICATE_DOCUMENT_UPLOAD:
            raise LocalKnowledgeError(f"文档已存在：{duplicate.id}")

        try:
            vectors = local_embedding_service.encode([chunk.content for chunk in parsed])
        except LocalEmbeddingError as exc:
            raise LocalKnowledgeError(str(exc)) from exc

        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        source_title = str(source_meta.get("relative_path") or source_meta.get("path") or filename)
        meta_json = {
            "embedding_provider": "local",
            "embedding_model": settings.LOCAL_EMBEDDING_MODEL,
            "source_meta": source_meta,
            "local_chunk_total": len(parsed),
            "rag_backend": "local_pgvector",
        }
        document = Document(
            course_id=course.id,
            uploaded_by_user_id=user_uuid,
            title=source_title[:255],
            filename=Path(filename).name[:255],
            mime_type=mime_type or fallback_mime,
            source_type="local_pgvector",
            parse_status="parsed",
            vector_status="ready",
            text_vector_status="ready",
            visual_vector_status="not_applicable",
            review_status="approved",
            publish_readiness="ready",
            content_hash=content_hash,
            source_hash=source_hash,
            parser_version=parser_version,
            chunker_version=settings.LOCAL_KNOWLEDGE_CHUNKER_VERSION,
            meta_json=meta_json,
        )
        if source_path:
            document.file_uri = str(Path(source_path).resolve())[:500]
        self.db.add(document)
        self.db.flush()

        for chunk, vector in zip(parsed, vectors, strict=True):
            chunk_hash = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
            heading_path = list(chunk.heading_path or [])
            heading_path_text = " / ".join(heading_path) if heading_path else None
            heading_ltree = ".".join(heading_path) if heading_path else None
            self.db.add(
                DocumentChunk(
                    document_id=document.id,
                    course_id=course.id,
                    chunk_index=chunk.chunk_index,
                    page_no=chunk.page_no,
                    section_path=_fit_column_text(chunk.section_path, 255),
                    heading_path_json=heading_path,
                    heading_path_text=_fit_column_text(heading_path_text, 500),
                    heading_ltree=_fit_column_text(heading_ltree, 500),
                    heading_number=chunk.heading_number,
                    asset_type="TEXT",
                    content=chunk.content,
                    raw_text=chunk.content,
                    language="zh" if re.search(r"[\u4e00-\u9fff]", chunk.content) else "en",
                    content_hash=chunk_hash,
                    lifecycle_status="active",
                    embedding_status="ready",
                    embedded_content_version=1,
                    embedded_content_hash=chunk_hash,
                    generation_id=uuid.uuid4().hex,
                    token_count=len(chunk.content),
                    parser_version=parser_version,
                    chunker_version=settings.LOCAL_KNOWLEDGE_CHUNKER_VERSION,
                    embedding_model=settings.LOCAL_EMBEDDING_MODEL,
                    embedding_dim=settings.LOCAL_EMBEDDING_DIMENSION,
                    embedding=vector,
                )
            )
        self.db.commit()
        _invalidate_bm25_cache(course.id)
        return {
            "document_id": str(document.id),
            "course_id": course_slug,
            "course_title": course.title,
            "filename": Path(filename).name,
            "parse_status": "parsed",
            "vector_status": "ready",
            "review_status": "approved",
            "publish_readiness": "ready",
            "chunk_count": len(parsed),
            "message": f"本地知识库已完成解析、向量化和入库，共 {len(parsed)} 个切片。",
            "rag_backend": "local_pgvector",
        }

    def search(self, course_slug: str, query: str, limit: int, document_id: str | None = None) -> list[Citation]:
        """在课程范围内执行 BM25 + 向量混合检索，返回加权融合排序后的统一 Citation。"""
        course = self._course(course_slug)
        try:
            query_vector = local_embedding_service.encode([query])[0]
        except LocalEmbeddingError as exc:
            raise LocalKnowledgeError(str(exc)) from exc

        # ── 1. 向量检索：取 top-(limit*4) 候选 ──
        vector_limit = max(limit * 4, 20)
        distance = DocumentChunk.embedding.cosine_distance(query_vector)
        vector_stmt = (
            select(DocumentChunk, Document, distance.label("distance"))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.course_id == course.id,
                DocumentChunk.lifecycle_status == "active",
                DocumentChunk.embedding_status == "ready",
                Document.deleted_at.is_(None),
            )
            .order_by(distance)
            .limit(vector_limit)
        )
        if document_id:
            vector_stmt = vector_stmt.where(Document.id == uuid.UUID(document_id))
        vector_rows = self.db.execute(vector_stmt).all()
        # 按 chunk_id 组织向量结果
        vector_results: dict[str, tuple[float, DocumentChunk, Document]] = {}
        for chunk, document, distance_value in vector_rows:
            similarity = max(0.0, min(1.0, 1.0 - float(distance_value)))
            vector_results[str(chunk.id)] = (similarity, chunk, document)

        # ── 2. BM25 检索 ──
        course_id_str = str(course.id)
        if course_id_str not in _bm25_cache:
            _bm25_cache[course_id_str] = _build_bm25_index(self.db, course.id)
        bm25_index = _bm25_cache[course_id_str]
        query_tokens = _tokenize(query)
        bm25_scores = bm25_index.bm25.get_scores(query_tokens)
        # 生成 (chunk_id, score) 列表，过滤零分结果
        scored_pairs = [
            (bm25_index.chunk_ids[i], bm25_scores[i])
            for i in range(len(bm25_scores))
            if bm25_scores[i] > 0
        ]
        scored_pairs.sort(key=lambda x: x[1], reverse=True)
        bm25_top = scored_pairs[:vector_limit]
        # BM25 分数归一化
        bm25_max = max(s for _, s in bm25_top) if bm25_top else 1.0

        # ── 3. 加权融合 ──
        bm25_weight = settings.LOCAL_KNOWLEDGE_BM25_WEIGHT
        vector_weight = settings.LOCAL_KNOWLEDGE_VECTOR_WEIGHT
        fused: dict[str, dict] = {}

        # 先加入向量结果
        for chunk_id, (sim, chunk, doc) in vector_results.items():
            fused[chunk_id] = {"vector_sim": sim, "bm25_score": 0.0, "chunk": chunk, "document": doc}

        # 再加入 BM25 结果（含 document_id 过滤）
        uuid_doc_id = uuid.UUID(document_id) if document_id else None
        for chunk_id, score in bm25_top:
            if uuid_doc_id is not None:
                chunk_obj = bm25_index.chunk_map.get(chunk_id)
                if chunk_obj is None or chunk_obj.document_id != uuid_doc_id:
                    continue
            norm_bm25 = score / bm25_max
            if chunk_id in fused:
                fused[chunk_id]["bm25_score"] = norm_bm25
            else:
                chunk_obj = bm25_index.chunk_map.get(chunk_id)
                if chunk_obj is None:
                    continue
                doc_obj = bm25_index.doc_map.get(str(chunk_obj.document_id))
                if doc_obj is None or doc_obj.deleted_at is not None:
                    continue
                fused[chunk_id] = {
                    "vector_sim": 0.0, "bm25_score": norm_bm25,
                    "chunk": chunk_obj, "document": doc_obj,
                }

        # 计算融合分并排序
        for chunk_id, data in fused.items():
            data["fused"] = bm25_weight * data["bm25_score"] + vector_weight * data["vector_sim"]

        sorted_items = sorted(fused.items(), key=lambda x: x[1]["fused"], reverse=True)

        # ── 4. 组装结果 ──
        results: list[Citation] = []
        for chunk_id, data in sorted_items[:limit]:
            chunk = data["chunk"]
            document = data["document"]
            results.append(Citation(
                source_id=str(document.id), source_title=document.title,
                page_no=chunk.page_no, chunk_index=chunk.chunk_index,
                local_chunk_id=str(chunk.id), chunk_id=str(chunk.id),
                provenance_source="local_pgvector", retrieval_mode="local_pgvector",
                similarity=round(data["fused"], 4),
                snippet=chunk.content[:settings.LOCAL_KNOWLEDGE_SNIPPET_SIZE],
                content=chunk.content, section_path=chunk.section_path,
            ))

        return results
