from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import CurrentUser, ensure_course_access, get_current_user
from app.models import Document
from app.schemas.course import (
    CourseAiContextResponse,
    CourseDocumentListResponse,
    CourseExtractedQaResponse,
    ExtractedQaItemResponse,
)
from app.services.course.repository import CourseRepository
from app.services.knowledge.extracted_qa_repository import ExtractedQaRepository
from app.services.knowledge.iflytek.course_chat_binding import course_ai_context_payload, resolve_course_chatdoc_binding
from app.services.knowledge.local_knowledge import LocalKnowledgeService
from app.services.knowledge.repository import KnowledgeRepository

router = APIRouter()


def _document_storage_root() -> Path:
    """返回课程资料本地备份目录。"""
    return (Path(settings.OBJECT_STORAGE_ROOT).expanduser().resolve() / "documents").resolve()


def _resolve_course_document(db: Session, course_id: str, document_id: str) -> Document:
    """解析当前课程下的有效知识库文档。

    参数:
        db: 数据库会话。
        course_id: 课程 slug 或 UUID。
        document_id: 文档 UUID。

    返回:
        当前课程关联的有效文档。

    异常:
        HTTPException: 当课程或文档不存在、文档已删除、文档不属于课程时抛出。
    """
    document = KnowledgeRepository(db).get_active_course_document(course_id, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在或不属于当前课程")
    return document


@router.get("/courses/{course_id}/ai-context", response_model=CourseAiContextResponse)
async def course_ai_context(
    course_id: str,
    concept_id: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CourseAiContextResponse | dict[str, object]:
    """课程 AI 对话上下文：讯飞 fileId、问答模式、知识库就绪状态。"""
    ensure_course_access(db, current_user, course_id)
    course = CourseRepository(db).get_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    if settings.RAG_BACKEND == "local_pgvector":
        readiness = LocalKnowledgeService(db).readiness(course.get("id") or course_id)
        knowledge_ready = bool(readiness["ready"])
        return {
            "course_id": readiness["course_id"],
            "course_title": readiness["course_title"],
            "knowledge_ready": knowledge_ready,
            "chat_input_enabled": knowledge_ready,
            "primary_file_id": None,
            "file_ids_count": int(readiness["document_count"]),
            "integration_key": "",
            "spark_version": None,
            "qa_mode": "LOCAL" if knowledge_ready else None,
            "rag_backend": settings.RAG_BACKEND,
            "require_citation_for_course_answer": True,
            "default_use_course_evidence_for_resource": True,
            "blocking_reason": None if knowledge_ready else "当前课程尚未导入可检索资料，请管理员先在知识库上传课程资料。",
            "status_label": (
                f"{readiness['course_title']} · 本地知识库已就绪"
                if knowledge_ready
                else f"{readiness['course_title']} · 本地知识库未就绪"
            ),
        }
    binding = resolve_course_chatdoc_binding(db, course_id, concept_code=concept_id)
    if binding:
        return course_ai_context_payload(binding)
    return {
        "course_id": course.get("id") or course_id,
        "course_title": course.get("title") or course_id,
        "knowledge_ready": False,
        "chat_input_enabled": False,
        "primary_file_id": None,
        "file_ids_count": 0,
        "integration_key": "",
        "spark_version": None,
        "qa_mode": None,
        "rag_backend": settings.RAG_BACKEND,
        "require_citation_for_course_answer": True,
        "default_use_course_evidence_for_resource": True,
        "blocking_reason": "课程 AI 上下文暂不可用",
        "status_label": f"{course.get('title') or course_id} · 知识库未就绪",
    }


@router.get("/courses/{course_id}/documents", response_model=CourseDocumentListResponse)
async def course_documents(
    course_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """用户侧课程资料列表，用于学习路径和课程资料问答入口。"""
    ensure_course_access(db, current_user, course_id)
    return KnowledgeRepository(db).list_documents(course_id)


@router.get("/courses/{course_id}/documents/{document_id}/file", response_model=None)
async def preview_course_document_file(
    course_id: str,
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """用户侧查看当前课程原始教材文件。"""
    ensure_course_access(db, current_user, course_id)
    document = _resolve_course_document(db, course_id, document_id)
    file_uri = (document.file_uri or "").strip()
    if not file_uri:
        raise HTTPException(
            status_code=404,
            detail="文档未保存本地原件，无法预览。请联系管理员重新上传该教材。",
        )
    path = Path(file_uri).expanduser().resolve()
    storage_root = _document_storage_root()
    if not path.is_relative_to(storage_root):
        raise HTTPException(status_code=403, detail="文档原件路径不在课程资料存储目录内，已拒绝预览。")
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"本地文件不存在或已被清理（{path.name}）。请联系管理员重新上传该教材。",
        )
    media_type = document.mime_type or "application/octet-stream"
    if path.suffix.lower() == ".pdf":
        media_type = "application/pdf"
    return FileResponse(path, media_type=media_type, filename=document.filename or path.name)


@router.get("/courses/{course_id}/extracted-qa", response_model=CourseExtractedQaResponse)
async def course_extracted_qa(
    course_id: str,
    limit: int = 12,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """本地影子库中的萃取 QA 对（点击展示答案不消耗讯飞问答额度）。"""
    ensure_course_access(db, current_user, course_id)
    items = ExtractedQaRepository(db).list_for_course(course_id, limit=limit)
    return {"course_id": course_id, "items": items}


@router.get("/courses/{course_id}/extracted-qa/{qa_id}", response_model=ExtractedQaItemResponse)
async def course_extracted_qa_detail(
    course_id: str,
    qa_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """读取单条本地萃取 QA，供学生在不消耗问答额度时展开答案。"""
    ensure_course_access(db, current_user, course_id)
    try:
        parsed_id = uuid.UUID(qa_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="无效的 QA 标识") from exc
    item = ExtractedQaRepository(db).get_by_id(parsed_id)
    if not item:
        raise HTTPException(status_code=404, detail="萃取问答不存在")
    return item
