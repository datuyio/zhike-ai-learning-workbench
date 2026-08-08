"""管理员知识库路由，通过 ChatDoc 云端入库支持所有允许格式。"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import NoReturn, TYPE_CHECKING

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.tracing import get_trace_id
from app.schemas.chatdoc_native_chunks import (
    NativeChunkEmbedRequest,
    NativeChunkItem,
    NativeChunkListResponse,
    NativeChunkRevisionListResponse,
    NativeChunkRevisionRestoreResponse,
    NativeChunkResplitRequest,
    NativeChunkSyncResponse,
    NativeChunkUpdateRequest,
)
from app.schemas.knowledge_cloud import (
    ChatdocDocumentChunksResponse,
    ChatdocRepoDebugResponse,
    CoursesWithKnowledgeResponse,
    DocumentExtractRequest,
    DocumentExtractResponse,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentPurgeResponse,
    KnowledgeDocumentRecycleResponse,
    KnowledgeDocumentRestoreResponse,
    KnowledgeDocumentScopedListResponse,
    KnowledgeDocumentUploadResponse,
    KnowledgeIngestionStatusResponse,
    KnowledgeSearchResponse,
    KnowledgeUploadPolicyResponse,
    NativeChunkResplitResponse,
    NativeChunkVectorizeSubmitResponse,
    RecycledKnowledgeDocumentListResponse,
    VectorizeActivateRequest,
    VectorizeActivateResponse,
)
from app.schemas.model_gateway import CourseModelConfigPayload, CourseModelConfigResponse
from app.services.knowledge.iflytek.client import IflytekChatDocError
from app.services.knowledge.iflytek.client_factory import chatdoc_client_for_db
from app.services.knowledge.iflytek.document_service import IflytekDocumentService
from app.services.knowledge.iflytek.repo_service import IflytekRepoService
from app.services.knowledge.iflytek.config_service import ChatdocConfigService
from app.services.knowledge.iflytek.retrieval_adapter import IflytekRetrievalAdapter
from app.services.knowledge.iflytek.native_chunk_revision import NativeChunkRevisionService
from app.services.knowledge.iflytek.native_chunk_sync import ChatdocNativeChunkSync
from app.services.knowledge.iflytek.pipeline_config import PipelineConfigJsonError, parse_pipeline_stage_json
from app.services.knowledge.local_knowledge import LocalKnowledgeError, LocalKnowledgeService
from app.services.knowledge.admin_service import KnowledgeAdminMutationService
from app.services.knowledge.repository import KnowledgeRepository
from app.services.knowledge.upload_service import KnowledgeUploadError, KnowledgeUploadService

if TYPE_CHECKING:
    from app.models import Document

router = APIRouter()
logger = logging.getLogger(__name__)


def _raise_chatdoc_error(exc: IflytekChatDocError, operation: str) -> NoReturn:
    """记录 ChatDoc 云端调用失败日志，并保持既有 502 响应语义。"""
    logger.warning(
        "ChatDoc 云端调用失败：operation=%s trace_id=%s",
        operation,
        get_trace_id(),
        exc_info=True,
    )
    raise HTTPException(status_code=502, detail=str(exc)) from exc


def _raise_pipeline_config_error(exc: PipelineConfigJsonError, operation: str) -> NoReturn:
    """记录 pipeline 配置解析失败日志，并保持既有 400 响应语义。"""
    logger.warning(
        "ChatDoc pipeline 配置解析失败：operation=%s trace_id=%s",
        operation,
        get_trace_id(),
        exc_info=True,
    )
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/knowledge/upload-policy", response_model=KnowledgeUploadPolicyResponse)
async def knowledge_upload_policy() -> KnowledgeUploadPolicyResponse:
    """返回管理端上传预校验所需的限制信息，并与服务端校验保持一致。"""
    return KnowledgeUploadPolicyResponse(
        max_upload_bytes=settings.MAX_DOCUMENT_UPLOAD_BYTES,
        allowed_extensions=sorted(settings.allowed_document_extensions_set),
        allowed_mime_types=sorted(settings.allowed_document_mime_types_set),
        block_duplicate_upload=settings.BLOCK_DUPLICATE_DOCUMENT_UPLOAD,
        block_duplicate_filename=settings.BLOCK_DUPLICATE_FILENAME,
        upload_timeout_seconds=180,
        rag_backend=settings.RAG_BACKEND,
    )


@router.get("/knowledge/chatdoc-repo-debug", response_model=ChatdocRepoDebugResponse)
async def chatdoc_repo_debug(
    course_id: str = Query(..., description="课程 slug，如 deep_learning_001"),
    integration_key: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ChatdocRepoDebugResponse:
    """诊断指定课程的 ChatDoc 仓库绑定和云端状态。"""
    _ = current_user
    if settings.RAG_BACKEND != "iflytek_chatdoc":
        raise HTTPException(status_code=503, detail="RAG_BACKEND 非 iflytek_chatdoc")
    try:
        result = await IflytekRepoService(
            db,
            chatdoc_client_for_db(db, integration_key=integration_key),
        ).debug_course_repo(course_id)
        return ChatdocRepoDebugResponse.model_validate(result)
    except IflytekChatDocError as exc:
        _raise_chatdoc_error(exc, "chatdoc_repo_debug")


@router.post("/courses/{course_id}/documents", response_model=KnowledgeDocumentUploadResponse)
async def upload_document(
    course_id: str,
    file: UploadFile = File(...),
    integration_key: str | None = Form(default=None),
    pipeline_stage_json: str | None = Form(default=None),
    force_reupload: bool = Form(default=False),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeDocumentUploadResponse:
    """按配置将课程资料写入本地 pgvector 或现有 ChatDoc 云端知识库。"""
    content = await file.read()
    filename = file.filename or "未命名文档"
    if settings.RAG_BACKEND == "local_pgvector":
        try:
            result = LocalKnowledgeService(db).ingest(course_id, filename, file.content_type, content, str(current_user.id))
        except LocalKnowledgeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return KnowledgeDocumentUploadResponse.model_validate(result)
    try:
        upload_stage_body = parse_pipeline_stage_json(pipeline_stage_json)
    except PipelineConfigJsonError as exc:
        _raise_pipeline_config_error(exc, "upload_document")
    try:
        result = await KnowledgeUploadService(db).upload_chatdoc_document(
            course_id=course_id,
            filename=filename,
            mime_type=file.content_type,
            content=content,
            user_external_id=current_user.id,
            integration_key=integration_key,
            upload_stage_body=upload_stage_body,
            force_reupload=force_reupload,
        )
    except KnowledgeUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return KnowledgeDocumentUploadResponse.model_validate(result)


@router.get("/knowledge/documents", response_model=KnowledgeDocumentScopedListResponse)
async def list_knowledge_documents(
    course_id: str | None = Query(default=None),
    limit: int = Query(default=300, ge=1, le=500),
    db: Session = Depends(get_db),
) -> KnowledgeDocumentScopedListResponse:
    """列出知识库文档；省略 course_id 时返回全部课程，传入时仅返回单课文档。"""
    return KnowledgeDocumentScopedListResponse.model_validate(
        KnowledgeRepository(db).list_documents_scoped(course_id, limit=limit)
    )


@router.get("/courses/{course_id}/documents", response_model=KnowledgeDocumentListResponse)
async def list_documents(course_id: str, db: Session = Depends(get_db)) -> KnowledgeDocumentListResponse:
    """列出指定课程的知识库文档。"""
    return KnowledgeDocumentListResponse.model_validate(KnowledgeRepository(db).list_documents(course_id))


@router.get("/courses/with-knowledge", response_model=CoursesWithKnowledgeResponse)
async def courses_with_knowledge(db: Session = Depends(get_db)) -> CoursesWithKnowledgeResponse:
    """列出已经具备可检索知识库的课程。"""
    return CoursesWithKnowledgeResponse.model_validate(KnowledgeRepository(db).get_courses_with_knowledge())


@router.get("/documents/{document_id}/chatdoc-chunks", response_model=ChatdocDocumentChunksResponse)
async def chatdoc_document_chunks(
    document_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ChatdocDocumentChunksResponse:
    """读取 ChatDoc 云端切片预览。"""
    document = KnowledgeRepository(db).get_active_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    file_id = str((document.meta_json or {}).get("iflytek_file_id") or "")
    if not file_id:
        raise HTTPException(status_code=409, detail="该文档未绑定云端知识库，无分段预览")
    try:
        result = await IflytekDocumentService(db).list_chunks_for_document(document, limit=limit, offset=offset)
        return ChatdocDocumentChunksResponse.model_validate(result)
    except IflytekChatDocError as exc:
        _raise_chatdoc_error(exc, "chatdoc_document_chunks")


def _get_active_chatdoc_document(db: Session, document_id: str) -> Document:
    """读取未删除的 ChatDoc 文档，缺失时统一映射为 404。"""
    document = KnowledgeRepository(db).get_active_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    return document


@router.get("/documents/{document_id}/native-chunks", response_model=NativeChunkListResponse)
async def list_native_chunks(
    document_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    page: int | None = Query(default=None, ge=1, description="按 PDF 页码过滤"),
    db: Session = Depends(get_db),
) -> NativeChunkListResponse:
    """本地持久化的讯飞原生切片（GET file/chunks 入库后）。"""
    document = _get_active_chatdoc_document(db, document_id)
    return ChatdocNativeChunkSync(db).list_local(document, limit=limit, offset=offset, page=page)


@router.post("/documents/{document_id}/native-chunks/sync", response_model=NativeChunkSyncResponse)
async def sync_native_chunks(
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NativeChunkSyncResponse:
    """通过 GET file/chunks 全量拉取并覆盖写入 document_chunks。"""
    try:
        result = await KnowledgeAdminMutationService(db).sync_native_chunks(document_id, current_user.id)
    except IflytekChatDocError as exc:
        _raise_chatdoc_error(exc, "sync_native_chunks")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="文档不存在")
    return NativeChunkSyncResponse(**result)


@router.post("/documents/{document_id}/native-chunks/resplit", response_model=NativeChunkResplitResponse)
async def resplit_native_chunks(
    document_id: str,
    payload: NativeChunkResplitRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NativeChunkResplitResponse:
    """调用讯飞 /file/split 重切，可选自动 sync 覆盖本地。"""
    try:
        result = await KnowledgeAdminMutationService(db).resplit_native_chunks(
            document_id,
            split_body=payload.split_body,
            sync_after=payload.sync_after,
            integration_key=payload.integration_key,
            actor_external_id=current_user.id,
        )
    except IflytekChatDocError as exc:
        _raise_chatdoc_error(exc, "resplit_native_chunks")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="文档不存在")
    return NativeChunkResplitResponse.model_validate(result)


@router.patch("/native-chunks/{chunk_id}", response_model=NativeChunkItem)
async def update_native_chunk(
    chunk_id: str,
    payload: NativeChunkUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NativeChunkItem:
    """人工修订本地原生切片内容、标签或页码。"""
    if not payload.content and payload.tags is None and payload.page is None:
        raise HTTPException(status_code=400, detail="请提供 content、tags 或 page")
    try:
        item = KnowledgeAdminMutationService(db).update_native_chunk(
            chunk_id,
            content=payload.content,
            tags=payload.tags,
            page_no=payload.page,
            actor_external_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=404, detail="分片不存在")
    return NativeChunkItem.model_validate(item)


@router.post("/documents/{document_id}/native-chunks/embed", response_model=NativeChunkVectorizeSubmitResponse)
async def embed_native_chunks_document(
    document_id: str,
    payload: NativeChunkEmbedRequest | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NativeChunkVectorizeSubmitResponse:
    """对已切分文档提交讯飞 file/embedding（等同 batch-embed 单文档）。"""
    integration_key = payload.integration_key if payload else None
    try:
        result = await KnowledgeAdminMutationService(db).embed_native_chunks_document(
            document_id,
            integration_key=integration_key,
        )
    except IflytekChatDocError as exc:
        _raise_chatdoc_error(exc, "embed_native_chunks_document")
    if not result:
        raise HTTPException(status_code=404, detail="文档不存在")
    return NativeChunkVectorizeSubmitResponse.model_validate(result)


@router.get("/documents/{document_id}/file", response_model=None)
async def download_document_file(
    document_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    """返回本地备份的原始 PDF/文档，供切片面板预览。"""
    document = _get_active_chatdoc_document(db, document_id)
    file_uri = (document.file_uri or "").strip()
    if not file_uri:
        raise HTTPException(
            status_code=404,
            detail="文档未保存本地原件，无法预览。请重新上传该 PDF 以生成本地备份。",
        )
    path = Path(file_uri).expanduser().resolve()
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"本地文件不存在或已被清理（{path.name}）。请重新上传该文档。",
        )
    media = document.mime_type or "application/pdf"
    if path.suffix.lower() == ".pdf":
        media = "application/pdf"
    return FileResponse(path, media_type=media, filename=document.filename or path.name)


@router.get("/documents/{document_id}/native-chunks/revisions", response_model=NativeChunkRevisionListResponse)
async def list_native_chunk_revisions(document_id: str, db: Session = Depends(get_db)) -> NativeChunkRevisionListResponse:
    """列出文档原生切片历史快照。"""
    document = _get_active_chatdoc_document(db, document_id)
    items = NativeChunkRevisionService(db).list_revisions(document.id)
    baseline = next((item for item in items if item.get("is_baseline")), None)
    return NativeChunkRevisionListResponse.model_validate(
        {
            "document_id": str(document.id),
            "items": items,
            "baseline_revision_id": baseline.get("revision_id") if baseline else None,
        }
    )


@router.post(
    "/documents/{document_id}/native-chunks/revisions/{revision_id}/restore",
    response_model=NativeChunkRevisionRestoreResponse,
)
async def restore_native_chunk_revision(
    document_id: str,
    revision_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NativeChunkRevisionRestoreResponse:
    """恢复指定原生切片历史快照。"""
    try:
        result = KnowledgeAdminMutationService(db).restore_native_chunk_revision(
            document_id,
            revision_id,
            current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="文档不存在")
    return NativeChunkRevisionRestoreResponse.model_validate(result)


@router.get("/documents/{document_id}/ingestion-status", response_model=KnowledgeIngestionStatusResponse)
async def ingestion_status(document_id: str, db: Session = Depends(get_db)) -> KnowledgeIngestionStatusResponse:
    """读取知识库文档入库状态和阶段进度。"""
    return KnowledgeIngestionStatusResponse.model_validate(KnowledgeRepository(db).ingestion_status(document_id))


@router.post("/knowledge/documents/batch-embed", response_model=VectorizeActivateResponse)
async def batch_embed_documents(
    payload: VectorizeActivateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VectorizeActivateResponse:
    """管理员批量激活 splited / pending_activation 状态文档的 ChatDoc 向量化。"""
    try:
        result = await KnowledgeAdminMutationService(db).batch_embed_documents(
            payload.document_ids,
            integration_key=payload.integration_key,
            actor_external_id=current_user.id,
        )
    except IflytekChatDocError as exc:
        _raise_chatdoc_error(exc, "batch_embed_documents")
    return VectorizeActivateResponse.model_validate(result)


@router.post("/knowledge/documents/extract", response_model=DocumentExtractResponse)
async def extract_documents(
    payload: DocumentExtractRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentExtractResponse:
    """管理员为已向量化文档提交 ChatDoc 问答萃取任务。"""
    try:
        result = await KnowledgeAdminMutationService(db).extract_documents(
            payload.document_ids,
            integration_key=payload.integration_key,
            extract_stage_body=payload.pipeline_stage_json,
            actor_external_id=current_user.id,
        )
    except IflytekChatDocError as exc:
        _raise_chatdoc_error(exc, "extract_documents")
    return DocumentExtractResponse.model_validate(result)


@router.post("/documents/{document_id}/purge", response_model=KnowledgeDocumentPurgeResponse)
async def purge_recycled_document(
    document_id: str,
    sync_chatdoc: bool = Query(default=True, description="是否同步删除讯飞云端文件"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeDocumentPurgeResponse:
    """物理清理回收站中的知识库文档。"""
    try:
        result = await KnowledgeAdminMutationService(db).purge_recycled_document(
            document_id,
            sync_chatdoc=sync_chatdoc,
            actor_external_id=current_user.id,
        )
    except IflytekChatDocError as exc:
        _raise_chatdoc_error(exc, "purge_recycled_document")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="文档不存在或已物理删除")
    return KnowledgeDocumentPurgeResponse.model_validate({"status": "purged", **result})


@router.delete(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentPurgeResponse | KnowledgeDocumentRecycleResponse,
)
async def delete_document(
    document_id: str,
    purge: bool = Query(default=False, description="true=物理删除含云端 file/del"),
    sync_chatdoc: bool = Query(default=True, description="物理删除时是否同步讯飞云端"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeDocumentPurgeResponse | KnowledgeDocumentRecycleResponse:
    """软回收知识库文档，或按 purge 参数执行物理删除。"""
    if purge:
        try:
            result = await KnowledgeAdminMutationService(db).purge_document(
                document_id,
                sync_chatdoc=sync_chatdoc,
                actor_external_id=current_user.id,
            )
        except IflytekChatDocError as exc:
            _raise_chatdoc_error(exc, "delete_document.purge")
        if not result:
            raise HTTPException(status_code=404, detail="文档不存在")
        return KnowledgeDocumentPurgeResponse.model_validate({"status": "purged", **result})

    result = KnowledgeAdminMutationService(db).recycle_document(document_id, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="文档不存在")
    return KnowledgeDocumentRecycleResponse.model_validate({"status": "recycled", **result})


@router.get("/knowledge/documents/recycled", response_model=RecycledKnowledgeDocumentListResponse)
async def list_recycled_documents(
    course_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> RecycledKnowledgeDocumentListResponse:
    """列出知识库回收站文档。"""
    return RecycledKnowledgeDocumentListResponse.model_validate(
        KnowledgeRepository(db).list_recycled_documents(course_id, limit=limit)
    )


@router.post("/documents/{document_id}/restore", response_model=KnowledgeDocumentRestoreResponse)
async def restore_recycled_document(
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeDocumentRestoreResponse:
    """从知识库回收站恢复文档。"""
    result = KnowledgeAdminMutationService(db).restore_recycled_document(document_id, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="文档不在回收站或已物理删除")
    return KnowledgeDocumentRestoreResponse.model_validate(result)


@router.get("/courses/{course_id}/model-config", response_model=CourseModelConfigResponse)
async def get_course_model_config(course_id: str, db: Session = Depends(get_db)) -> CourseModelConfigResponse:
    """读取课程级模型和知识库绑定配置。"""
    return CourseModelConfigResponse.model_validate(KnowledgeRepository(db).get_course_model_config(course_id))


@router.put("/courses/{course_id}/model-config", response_model=CourseModelConfigResponse)
async def update_course_model_config(
    course_id: str,
    payload: CourseModelConfigPayload,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CourseModelConfigResponse:
    """更新课程级模型和知识库绑定配置。"""
    body = payload.model_dump(exclude_unset=True)
    result = KnowledgeAdminMutationService(db).update_course_model_config(course_id, body, current_user.id)
    return CourseModelConfigResponse.model_validate(result)


@router.get("/knowledge/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    course_id: str = Query(...),
    q: str = Query(..., min_length=1),
    concept_id: str | None = None,
    limit: int = Query(10, ge=1, le=50),
    document_id: str | None = None,
    integration_key: str | None = None,
    pipeline_stage_json: str | None = None,
    wiki_filter_score: float | None = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
) -> KnowledgeSearchResponse:
    """执行当前配置的本地 pgvector 或 ChatDoc 云端检索并返回引用证据。"""
    if settings.RAG_BACKEND == "local_pgvector":
        started = time.perf_counter()
        try:
            citations = LocalKnowledgeService(db).search(course_id, q, limit, document_id=document_id)
        except LocalKnowledgeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return KnowledgeSearchResponse.model_validate({
            "course_id": course_id,
            "query": q,
            "retrieval_mode": "local_pgvector",
            "items": [citation.model_dump() for citation in citations],
            "latency_ms": int((time.perf_counter() - started) * 1000),
        })
    if settings.RAG_BACKEND != "iflytek_chatdoc":
        raise HTTPException(status_code=503, detail=f"不支持的知识库后端：{settings.RAG_BACKEND}")
    adapter = IflytekRetrievalAdapter(db, integration_key=integration_key)
    started = time.perf_counter()
    config_service = ChatdocConfigService(db)
    active_key = integration_key or config_service.active_template_key()
    resolved_wiki_filter = (
        float(wiki_filter_score)
        if wiki_filter_score is not None
        else config_service.wiki_filter_score(active_key)
    )
    try:
        retrieval_stage_body = parse_pipeline_stage_json(pipeline_stage_json)
    except PipelineConfigJsonError as exc:
        _raise_pipeline_config_error(exc, "search_knowledge")
    citations, filter_meta = await adapter.search(
        course_id,
        q,
        concept_id,
        limit,
        document_id=document_id,
        retrieval_stage_body=retrieval_stage_body,
        wiki_filter_score=resolved_wiki_filter,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    items = [citation.model_dump() for citation in citations[:limit]]
    return KnowledgeSearchResponse.model_validate(
        {
            "course_id": course_id,
            "query": q,
            "retrieval_mode": "iflytek_vector",
            "items": items,
            "latency_ms": latency_ms,
            "wiki_filter_score": resolved_wiki_filter,
            **filter_meta,
        }
    )
