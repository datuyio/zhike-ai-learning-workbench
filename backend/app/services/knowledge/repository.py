from __future__ import annotations

import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AdminAuditLog, Course, CourseConcept, CourseMembership, Document, DocumentChunk, DocumentPage, ModelProvider, RagIntegrationConfig, User
from app.services.knowledge.ingestion_status_builder import (
    build_ingestion_stages,
    compute_ingestion_progress,
    ingestion_flags,
    resolve_chatdoc_file_status,
)


logger = logging.getLogger(__name__)


class KnowledgeRepository:
    """知识库文档、入库状态、课程模型配置和回收站的仓储服务。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _course(self, slug: str) -> Course | None:
        return self.db.execute(
            select(Course).where(or_(Course.slug == slug, Course.id == self._safe_uuid(slug)))
        ).scalar_one_or_none()

    def _user(self, external_id: str | None) -> User | None:
        if not external_id:
            return None
        return self.db.execute(select(User).where(User.external_id == external_id)).scalar_one_or_none()

    @staticmethod
    def _safe_uuid(value: str | None) -> uuid.UUID | None:
        if not value:
            return None
        try:
            return uuid.UUID(str(value))
        except ValueError:
            return None

    @staticmethod
    def parse_uuid(value: str | None) -> uuid.UUID | None:
        """安全解析外部传入的 UUID 字符串，无法解析时返回 None。"""
        return KnowledgeRepository._safe_uuid(value)

    def _concept(self, course: Course, concept_code_or_id: str | None) -> CourseConcept | None:
        if not concept_code_or_id:
            return None
        clauses = [CourseConcept.course_id == course.id, CourseConcept.code == concept_code_or_id]
        if safe_uuid := self._safe_uuid(concept_code_or_id):
            clauses = [
                CourseConcept.course_id == course.id,
                or_(CourseConcept.code == concept_code_or_id, CourseConcept.id == safe_uuid),
            ]
        return self.db.execute(select(CourseConcept).where(*clauses)).scalar_one_or_none()

    def get_course_concept_model(self, course: Course, concept_code_or_id: str | None) -> CourseConcept | None:
        """按课程和知识点 code 或 UUID 读取知识点实体，供知识库适配服务复用。"""

        return self._concept(course, concept_code_or_id)

    @staticmethod
    def _normalize_upload_display_name(value: str | None) -> str:
        return (value or "").strip().lower()

    def find_active_duplicate_filename(self, course_slug: str, filename: str) -> Document | None:
        """按课程范围查找仍处于有效列表中的同名文档。"""

        normalized = self._normalize_upload_display_name(filename)
        if not normalized:
            return None
        course = self._course(course_slug)
        if not course:
            return None
        rows = self.db.execute(
            select(Document).where(Document.course_id == course.id, *self._is_active_list_clause())
        ).scalars().all()
        for document in rows:
            if self._normalize_upload_display_name(document.filename) == normalized:
                return document
            if self._normalize_upload_display_name(document.title) == normalized:
                return document
        return None

    def find_active_duplicate_document(self, course_slug: str, content_hash: str) -> Document | None:
        """按内容哈希查找课程内仍有效的重复文档。"""

        if not content_hash:
            return None
        course = self._course(course_slug)
        if not course:
            return None
        return self.db.execute(
            select(Document)
            .where(
                Document.course_id == course.id,
                Document.content_hash == content_hash,
                *self._is_active_list_clause(),
            )
            .order_by(Document.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def get_active_document(self, document_id: str) -> Document | None:
        """返回未硬删除且 parse_status 未标记删除的知识库文档。"""
        document_uuid = self._safe_uuid(document_id)
        if not document_uuid:
            return None
        return self.db.execute(
            select(Document).where(
                Document.id == document_uuid,
                Document.deleted_at.is_(None),
                Document.parse_status != "deleted",
            )
        ).scalar_one_or_none()

    def get_active_course_document(self, course_id_or_slug: str, document_id: str) -> Document | None:
        """返回指定课程下的有效知识库文档，课程和文档均可使用外部标识。"""
        document_uuid = self._safe_uuid(document_id)
        if not document_uuid:
            return None
        course_clauses = [Course.slug == course_id_or_slug]
        if course_uuid := self._safe_uuid(course_id_or_slug):
            course_clauses.append(Course.id == course_uuid)
        return self.db.execute(
            select(Document)
            .join(Course, Document.course_id == Course.id)
            .where(
                Document.id == document_uuid,
                *self._is_active_list_clause(),
                or_(*course_clauses),
            )
        ).scalar_one_or_none()

    def record_admin_audit(
        self,
        actor_external_id: str | None,
        action: str,
        target_type: str,
        target_id: str,
        detail: dict[str, Any],
    ) -> None:
        """写入后台操作审计记录，隐藏路由层对审计表和用户表的直接访问。"""

        actor = self._user(actor_external_id)
        self.db.add(
            AdminAuditLog(
                actor_user_id=actor.id if actor else None,
                action=action,
                target_type=target_type,
                target_id=target_id,
                detail_json=detail,
            )
        )

    def create_document_record(
        self,
        course_slug: str,
        filename: str,
        mime_type: str | None,
        user_external_id: str | None = None,
        file_uri: str | None = None,
        content_hash: str | None = None,
        ingestion_options: dict | None = None,
    ) -> dict:
        """创建知识库文档记录，并标记重复来源和入库选项。"""

        course = self._course(course_slug)
        user = self._user(user_external_id)
        if not course:
            return {"course_id": course_slug, "filename": filename, "parse_status": "failed", "message": "course not found"}
        duplicate = self.find_active_duplicate_document(course_slug, content_hash or "") if content_hash else None
        document = Document(
            course_id=course.id,
            uploaded_by_user_id=user.id if user else None,
            title=filename,
            filename=filename,
            mime_type=mime_type,
            source_type="course_material",
            parse_status="processing",
            vector_status="processing",
            text_vector_status="processing",
            visual_vector_status="skipped",
            review_status="pending",
            publish_readiness="blocked",
            file_uri=file_uri,
            content_hash=content_hash,
            source_hash=content_hash,
            parser_version="iflytek_chatdoc",
            chunker_version="iflytek_chatdoc",
            meta_json={
                **({"duplicate_of": str(duplicate.id)} if duplicate else {}),
                **({"ingestion_options": ingestion_options} if ingestion_options else {}),
            },
        )
        self.db.add(document)
        self.db.flush()
        self.db.commit()
        return {
            "document_id": str(document.id),
            "course_id": course.slug,
            "course_title": course.title,
            "filename": filename,
            "parse_status": document.parse_status,
            "vector_status": document.vector_status,
            "review_status": document.review_status,
            "publish_readiness": document.publish_readiness,
            "duplicate_of": str(duplicate.id) if duplicate else None,
        }

    def get_course_model_config(self, course_slug: str) -> dict:
        """读取课程级模型、RAG 和成本限制配置。"""

        course = self._course(course_slug)
        if not course:
            return {"course_id": course_slug, "status": "not_found", "use_global_embedding": True}
        config = course.model_config_json or {}
        provider_code = config.get("embedding_provider")
        provider = (
            self.db.execute(select(ModelProvider).where(ModelProvider.provider == provider_code)).scalar_one_or_none()
            if provider_code
            else None
        )
        chat_provider_code = config.get("chat_provider")
        chat_provider = (
            self.db.execute(select(ModelProvider).where(ModelProvider.provider == chat_provider_code)).scalar_one_or_none()
            if chat_provider_code
            else None
        )
        image_provider_code = config.get("image_provider")
        image_provider = (
            self.db.execute(select(ModelProvider).where(ModelProvider.provider == image_provider_code)).scalar_one_or_none()
            if image_provider_code
            else None
        )
        cloud_rag_provider_code = config.get("cloud_rag_provider") or config.get("cloud_rag_provider_id")
        cloud_rag_provider = (
            self.db.execute(select(RagIntegrationConfig).where(RagIntegrationConfig.integration_key == cloud_rag_provider_code)).scalar_one_or_none()
            if cloud_rag_provider_code
            else None
        )
        return {
            "course_id": course.slug,
            "chat_provider": chat_provider_code,
            "chat_provider_name": chat_provider.display_name if chat_provider else None,
            "chat_model": chat_provider.chat_model if chat_provider else None,
            "image_provider": image_provider_code,
            "image_provider_name": image_provider.display_name if image_provider else None,
            "image_model": (
                (image_provider.meta_json or {}).get("image_model") or image_provider.vision_model or image_provider.chat_model
                if image_provider
                else None
            ),
            "cloud_rag_provider": cloud_rag_provider_code,
            "cloud_rag_provider_id": cloud_rag_provider_code,
            "cloud_rag_provider_name": cloud_rag_provider.display_label if cloud_rag_provider else None,
            "remote_knowledge_base_id": config.get("remote_knowledge_base_id") or course.iflytek_repo_id,
            "default_answer_mode": config.get("default_answer_mode") or "default_chat",
            "allow_rag_fallback_to_chat": bool(config.get("allow_rag_fallback_to_chat", False)),
            "require_citation_for_course_answer": bool(config.get("require_citation_for_course_answer", True)),
            "default_use_course_evidence_for_resource": bool(config.get("default_use_course_evidence_for_resource", True)),
            "ai_binding_enabled": bool(config.get("ai_binding_enabled", True)),
            "use_global_embedding": not bool(provider_code) or bool(config.get("use_global_embedding", False)),
            "embedding_provider": provider_code,
            "embedding_provider_name": provider.display_name if provider else None,
            "embedding_model": config.get("embedding_model"),
            "embedding_dimension": config.get("embedding_dimension"),
            "text_embedding_provider": config.get("text_embedding_provider") or provider_code,
            "text_embedding_model": config.get("text_embedding_model") or config.get("embedding_model"),
            "text_embedding_dimension": config.get("text_embedding_dimension") or config.get("embedding_dimension"),
            "multimodal_embedding_provider": config.get("multimodal_embedding_provider"),
            "multimodal_embedding_model": config.get("multimodal_embedding_model"),
            "multimodal_embedding_dimension": config.get("multimodal_embedding_dimension"),
            "rerank_provider": config.get("rerank_provider"),
            "rerank_model": config.get("rerank_model"),
            "vlm_provider": config.get("vlm_provider"),
            "ocr_provider": config.get("ocr_provider"),
            "daily_token_limit": config.get("daily_token_limit") or (config.get("cost_limits") or {}).get("daily_token_limit"),
            "daily_cost_limit": (config.get("cost_limits") or {}).get("daily_cost_limit"),
        }

    def update_course_model_config(self, course_slug: str, payload: dict) -> dict:
        """更新课程级模型、RAG 和成本限制配置。"""

        course = self._course(course_slug)
        if not course:
            return {"course_id": course_slug, "status": "not_found"}
        config = dict(course.model_config_json or {})

        if "chat_provider" in payload:
            chat_code = payload.get("chat_provider")
            if chat_code:
                chat_row = self.db.execute(select(ModelProvider).where(ModelProvider.provider == chat_code)).scalar_one_or_none()
                if not chat_row:
                    return {"course_id": course.slug, "status": "failed", "message": "chat provider not found"}
                config["chat_provider"] = chat_row.provider
            else:
                config.pop("chat_provider", None)

        if "image_provider" in payload:
            image_code = payload.get("image_provider")
            if image_code:
                image_row = self.db.execute(select(ModelProvider).where(ModelProvider.provider == image_code)).scalar_one_or_none()
                if not image_row:
                    return {"course_id": course.slug, "status": "failed", "message": "image provider not found"}
                image_model = (image_row.meta_json or {}).get("image_model") or image_row.vision_model or image_row.chat_model
                if image_row.provider_type not in {"image", "image_generation", "both"} or not image_model:
                    return {"course_id": course.slug, "status": "failed", "message": "image provider capability unavailable"}
                config["image_provider"] = image_row.provider
            else:
                config.pop("image_provider", None)

        cloud_key = payload.get("cloud_rag_provider_id") if "cloud_rag_provider_id" in payload else payload.get("cloud_rag_provider")
        if "cloud_rag_provider" in payload or "cloud_rag_provider_id" in payload:
            if cloud_key:
                rag_row = self.db.execute(
                    select(RagIntegrationConfig).where(RagIntegrationConfig.integration_key == cloud_key)
                ).scalar_one_or_none()
                if not rag_row:
                    return {"course_id": course.slug, "status": "failed", "message": "cloud rag provider not found"}
                config["cloud_rag_provider"] = rag_row.integration_key
                config["cloud_rag_provider_id"] = rag_row.integration_key
            else:
                config.pop("cloud_rag_provider", None)
                config.pop("cloud_rag_provider_id", None)

        if "remote_knowledge_base_id" in payload:
            remote_id = payload.get("remote_knowledge_base_id")
            if remote_id:
                config["remote_knowledge_base_id"] = str(remote_id).strip()
            else:
                config.pop("remote_knowledge_base_id", None)

        if "default_answer_mode" in payload:
            mode = payload.get("default_answer_mode")
            config["default_answer_mode"] = mode if mode in {"default_chat", "course_rag_qa"} else "default_chat"

        for key in (
            "allow_rag_fallback_to_chat",
            "require_citation_for_course_answer",
            "default_use_course_evidence_for_resource",
            "ai_binding_enabled",
        ):
            if key in payload and payload.get(key) is not None:
                config[key] = bool(payload.get(key))

        if "daily_token_limit" in payload:
            raw = payload.get("daily_token_limit")
            if raw in (None, "", 0):
                config.pop("daily_token_limit", None)
                limits = dict(config.get("cost_limits") or {})
                limits.pop("daily_token_limit", None)
                if limits:
                    config["cost_limits"] = limits
                else:
                    config.pop("cost_limits", None)
            else:
                token_limit = int(raw)
                config["daily_token_limit"] = token_limit
                limits = dict(config.get("cost_limits") or {})
                limits["daily_token_limit"] = token_limit
                config["cost_limits"] = limits

        if "daily_cost_limit" in payload:
            raw = payload.get("daily_cost_limit")
            if raw in (None, "", 0):
                limits = dict(config.get("cost_limits") or {})
                limits.pop("daily_cost_limit", None)
                if limits:
                    config["cost_limits"] = limits
                else:
                    config.pop("cost_limits", None)
            else:
                cost_limit = float(raw)
                limits = dict(config.get("cost_limits") or {})
                limits["daily_cost_limit"] = cost_limit
                config["cost_limits"] = limits

        embedding_touched = any(
            key in payload
            for key in (
                "use_global_embedding",
                "embedding_provider",
                "text_embedding_provider",
                "embedding_model",
                "embedding_dimension",
                "text_embedding_model",
                "text_embedding_dimension",
            )
        )
        if embedding_touched:
            use_global = payload.get("use_global_embedding")
            if use_global is None:
                use_global = config.get("use_global_embedding", True)
            if use_global:
                for key in (
                    "embedding_provider",
                    "embedding_model",
                    "embedding_dimension",
                    "text_embedding_provider",
                    "text_embedding_model",
                    "text_embedding_dimension",
                    "multimodal_embedding_provider",
                    "multimodal_embedding_model",
                    "multimodal_embedding_dimension",
                    "rerank_provider",
                    "rerank_model",
                    "vlm_provider",
                    "ocr_provider",
                ):
                    config.pop(key, None)
                config["use_global_embedding"] = True
            else:
                provider_code = payload.get("text_embedding_provider") or payload.get("embedding_provider")
                provider = self.db.execute(select(ModelProvider).where(ModelProvider.provider == provider_code)).scalar_one_or_none()
                if not provider:
                    return {"course_id": course.slug, "status": "failed", "message": "embedding provider not found"}
                config.update(
                    {
                        "use_global_embedding": False,
                        "embedding_provider": provider.provider,
                        "embedding_model": payload.get("embedding_model") or provider.embedding_model,
                        "embedding_dimension": payload.get("embedding_dimension") or provider.embedding_dimension,
                        "text_embedding_provider": provider.provider,
                        "text_embedding_model": payload.get("text_embedding_model")
                        or payload.get("embedding_model")
                        or provider.embedding_model,
                        "text_embedding_dimension": payload.get("text_embedding_dimension")
                        or payload.get("embedding_dimension")
                        or provider.embedding_dimension,
                        "multimodal_embedding_provider": payload.get("multimodal_embedding_provider"),
                        "multimodal_embedding_model": payload.get("multimodal_embedding_model"),
                        "multimodal_embedding_dimension": payload.get("multimodal_embedding_dimension"),
                        "rerank_provider": payload.get("rerank_provider"),
                        "rerank_model": payload.get("rerank_model"),
                        "vlm_provider": payload.get("vlm_provider"),
                        "ocr_provider": payload.get("ocr_provider"),
                    }
                )

        course.model_config_json = config
        self.db.commit()
        return self.get_course_model_config(course.slug)

    def _chatdoc_document_fields(self, document: Document, course: Course | None = None) -> dict:
        meta = document.meta_json or {}
        chatdoc_status = meta.get("chatdoc_status") or {}
        from app.services.knowledge.iflytek.status_labels import normalize_chatdoc_file_status

        file_status = normalize_chatdoc_file_status(
            meta.get("chatdoc_file_status")
            or chatdoc_status.get("fileStatus")
            or chatdoc_status.get("file_status")
        )
        from app.services.knowledge.iflytek.cloud_status import (
            AWAITING_PUBLISH_READINESS,
            PENDING_ACTIVATION_VECTOR_STATUS,
            is_awaiting_activation,
        )

        cloud_status = meta.get("cloud_status") or file_status or None
        awaiting = is_awaiting_activation(document.vector_status, file_status)
        from app.services.knowledge.iflytek.native_chunk_sync import NATIVE_PARSER_VERSION

        local_native_chunk_count = self.db.scalar(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.parser_version == NATIVE_PARSER_VERSION,
                DocumentChunk.lifecycle_status == "active",
            )
        )
        duplicate_of = meta.get("duplicate_of")
        if duplicate_of:
            dup_id = self._safe_uuid(str(duplicate_of))
            if dup_id:
                dup_doc = self.db.get(Document, dup_id)
                if (not dup_doc or dup_doc.deleted_at is not None or dup_doc.parse_status == "deleted"
                        or (dup_doc.meta_json or {}).get("recycled_at")
                        or not dup_doc.content_hash or dup_doc.content_hash != document.content_hash):
                    duplicate_of = None
            else:
                duplicate_of = None
        return {
            "duplicate_of": str(duplicate_of) if duplicate_of else None,
            "iflytek_file_id": meta.get("iflytek_file_id"),
            "iflytek_repo_id": meta.get("iflytek_repo_id") or (course.iflytek_repo_id if course else None),
            "chatdoc_sid": meta.get("chatdoc_sid"),
            "chatdoc_file_status": file_status or None,
            "cloud_status": cloud_status,
            "awaiting_activation": awaiting,
            "chatdoc_step_by_step": meta.get("chatdoc_step_by_step"),
            "parse_type": meta.get("parse_type"),
            "chatdoc_error": meta.get("chatdoc_error"),
            "last_synced_at": meta.get("last_synced_at"),
            "ingestion_duration_ms": meta.get("ingestion_duration_ms"),
            "native_chunks_synced_at": meta.get("native_chunks_synced_at"),
            "local_native_chunk_count": int(local_native_chunk_count or 0),
            "rag_backend": meta.get("rag_backend") or "iflytek_chatdoc",
            "pending_activation_vector_status": [PENDING_ACTIVATION_VECTOR_STATUS],
            "awaiting_publish_readiness": [AWAITING_PUBLISH_READINESS],
        }

    def ingestion_status(self, document_id: str) -> dict:
        """返回知识库文档当前入库进度和阶段状态。"""

        document_uuid = self._safe_uuid(document_id)
        document = self.db.get(Document, document_uuid)
        if not document:
            return {
                "document_id": document_id,
                "status": "not_found",
                "progress": 100,
                "parse_status": "failed",
                "vector_status": "failed",
                "error": "文档记录不存在，可能已被清理。",
                "stages": [],
            }
        meta = document.meta_json or {}
        file_status = resolve_chatdoc_file_status(meta)
        failed, ready, awaiting, processing = ingestion_flags(
            document.parse_status,
            document.vector_status,
            file_status,
        )
        progress = compute_ingestion_progress(
            ready=ready,
            awaiting=awaiting,
            processing=processing,
            failed=failed,
        )

        course = self.db.get(Course, document.course_id)
        chatdoc_fields = self._chatdoc_document_fields(document, course)
        local_native_chunk_count = int(chatdoc_fields.get("local_native_chunk_count") or 0)
        return {
            "document_id": str(document.id),
            "status": document.parse_status if not failed else "failed",
            "progress": progress,
            "parse_status": document.parse_status,
            "vector_status": document.vector_status,
            "awaiting_activation": awaiting,
            "cloud_status": file_status or chatdoc_fields.get("cloud_status"),
            "local_native_chunk_count": local_native_chunk_count,
            "error": meta.get("chatdoc_error"),
            "result": {
                **chatdoc_fields,
                "chatdoc_file_status": file_status or None,
                "awaiting_activation": awaiting,
            },
            "events": [],
            "stages": build_ingestion_stages(
                file_status=file_status,
                ready=ready,
                processing=processing,
                failed=failed,
            ),
        }

    def _serialize_document_item(self, document: Document, course: Course) -> dict:
        return {
            "id": str(document.id),
            "title": document.title,
            "filename": document.filename,
            "mime_type": document.mime_type,
            "parse_status": document.parse_status,
            "vector_status": document.vector_status,
            "text_vector_status": document.text_vector_status,
            "visual_vector_status": document.visual_vector_status,
            "review_status": document.review_status,
            "publish_readiness": document.publish_readiness,
            "chunk_count": int(
                (document.meta_json or {}).get("chatdoc_chunk_total")
                or (document.meta_json or {}).get("local_chunk_total")
                or 0
            ),
            "page_count": 0,
            "source_type": document.source_type,
            "created_at": document.created_at.isoformat() if document.created_at else None,
            "updated_at": document.updated_at.isoformat() if document.updated_at else None,
            "parser_version": document.parser_version,
            "chunker_version": document.chunker_version,
            "course_id": course.slug,
            "course_title": course.title,
            **self._chatdoc_document_fields(document, course),
        }

    def list_documents_scoped(self, course_slug: str | None = None, *, limit: int = 300) -> dict:
        """按全部课程或单课程范围列出有效知识库文档。"""

        stmt = (
            select(Document, Course)
            .join(Course, Document.course_id == Course.id)
            .where(*self._is_active_list_clause())
            .order_by(Document.updated_at.desc().nullslast(), Document.created_at.desc())
            .limit(limit)
        )
        scope_course_title: str | None = None
        if course_slug:
            course = self._course(course_slug)
            if not course:
                return {
                    "scope": "course",
                    "course_id": course_slug,
                    "course_title": None,
                    "total": 0,
                    "items": [],
                }
            stmt = stmt.where(Document.course_id == course.id)
            scope_course_title = course.title

        rows = self.db.execute(stmt).all()
        items = [self._serialize_document_item(document, course) for document, course in rows]
        return {
            "scope": "course" if course_slug else "all",
            "course_id": course_slug,
            "course_title": scope_course_title,
            "total": len(items),
            "items": items,
        }

    def list_documents(self, course_slug: str, limit: int = 50) -> dict:
        """列出指定课程的有效知识库文档。"""

        course = self._course(course_slug)
        if not course:
            return {"course_id": course_slug, "items": []}
        rows = (
            self.db.execute(
                select(Document)
                .where(
                    Document.course_id == course.id,
                    *self._is_active_list_clause(),
                )
                .order_by(Document.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return {
            "course_id": course.slug,
            "iflytek_repo_id": course.iflytek_repo_id,
            "items": [
                self._serialize_document_item(document, course)
                for document in rows
            ],
        }

    def get_courses_with_knowledge(self, user_external_id: str | None = None) -> dict:
        """返回已经具备可检索知识库文档的课程 ID 集合。"""

        stmt = (
            select(Document.course_id)
            .where(
                Document.deleted_at.is_(None),
                or_(Document.parse_status == "completed", Document.parse_status == "parsed"),
                Document.vector_status == "ready",
            )
            .distinct()
        )
        if settings.RAG_BACKEND == "local_pgvector":
            stmt = (
                stmt
                .where(Document.source_type == "local_pgvector")
                .join(DocumentChunk, DocumentChunk.document_id == Document.id)
                .where(
                    DocumentChunk.lifecycle_status == "active",
                    DocumentChunk.embedding_status == "ready",
                    DocumentChunk.embedding.is_not(None),
                )
            )
        if user_external_id:
            user = self._user(user_external_id)
            if not user:
                return {"course_ids": []}
            # 管理员可查看全部已就绪课程；普通用户只返回有效选课记录。
            if user.role_code != "admin":
                stmt = stmt.join(CourseMembership, CourseMembership.course_id == Document.course_id).where(
                    CourseMembership.user_id == user.id,
                    CourseMembership.status == "active",
                )
        rows = self.db.execute(stmt).scalars().all()
        return {"course_ids": [str(row) for row in rows]}

    @staticmethod
    def _recycled_at_expr():
        return Document.meta_json["recycled_at"].astext

    @classmethod
    def _is_active_list_clause(cls):
        return (
            Document.deleted_at.is_(None),
            Document.parse_status != "deleted",
            func.coalesce(cls._recycled_at_expr(), "") == "",
        )

    def recycle_document(self, document_id: str) -> dict | None:
        """软回收文档：从管理列表隐藏，但保留 vector_status 供学生 RAG 使用。"""
        document = self.db.get(Document, self._safe_uuid(document_id))
        if not document or document.deleted_at is not None:
            return None
        now_iso = datetime.now(timezone.utc).isoformat()
        document.meta_json = {
            **(document.meta_json or {}),
            "recycled_at": now_iso,
            "recycled_from": "admin_soft_delete",
        }
        self.db.flush()
        return {
            "document_id": str(document.id),
            "title": document.title,
            "filename": document.filename,
            "status": "recycled",
            "recycled_at": now_iso,
            "chatdoc_preserved": True,
        }

    def restore_recycled_document(self, document_id: str) -> dict | None:
        """从知识库回收站恢复文档。"""

        document = self.db.get(Document, self._safe_uuid(document_id))
        if not document or document.deleted_at is not None:
            return None
        meta = dict(document.meta_json or {})
        if not meta.get("recycled_at"):
            return None
        meta.pop("recycled_at", None)
        meta.pop("recycled_from", None)
        meta["restored_at"] = datetime.now(timezone.utc).isoformat()
        document.meta_json = meta
        self.db.flush()
        return {"document_id": str(document.id), "title": document.title, "status": "restored"}

    def list_recycled_documents(self, course_slug: str | None = None, *, limit: int = 200) -> dict:
        """列出知识库回收站文档，可按课程过滤。"""

        stmt = (
            select(Document, Course)
            .join(Course, Document.course_id == Course.id)
            .where(
                Document.deleted_at.is_(None),
                func.coalesce(self._recycled_at_expr(), "") != "",
            )
            .order_by(Document.updated_at.desc().nullslast())
            .limit(limit)
        )
        if course_slug:
            course = self._course(course_slug)
            if not course:
                return {"items": [], "total": 0}
            stmt = stmt.where(Document.course_id == course.id)
        rows = self.db.execute(stmt).all()
        return {
            "total": len(rows),
            "items": [self._serialize_document_item(document, course) for document, course in rows],
        }

    async def purge_document(
        self,
        document_id: str,
        *,
        sync_chatdoc: bool = True,
        doc_service: Any | None = None,
    ) -> dict | None:
        """物理清理知识库文档，并可同步删除 ChatDoc 云端文件。"""

        document = self.db.get(Document, self._safe_uuid(document_id))
        if not document:
            return None
        meta = document.meta_json or {}
        file_id = str(meta.get("iflytek_file_id") or "").strip()
        chatdoc_result: dict = {"attempted": False, "deleted": False, "file_id": file_id or None}
        if sync_chatdoc and file_id and document.parser_version == "iflytek_chatdoc":
            from app.services.knowledge.iflytek.document_service import IflytekDocumentService

            service = doc_service or IflytekDocumentService(self.db)
            chatdoc_result["attempted"] = True
            try:
                await service.delete_remote_file(file_id)
                chatdoc_result["deleted"] = True
            except Exception as exc:
                chatdoc_result["error"] = str(exc)
                logger.warning(
                    "物理清理知识库文档时删除 ChatDoc 云端文件失败：document_id=%s file_id=%s sync_chatdoc=%s",
                    document_id,
                    file_id,
                    sync_chatdoc,
                    exc_info=True,
                )
                raise
        purge = self._purge_document_row(document)
        return {**purge, "chatdoc": chatdoc_result}

    async def purge_recycled_document(
        self,
        document_id: str,
        *,
        sync_chatdoc: bool = True,
        doc_service: Any | None = None,
    ) -> dict | None:
        """物理清理回收站文档；非回收站文档以 ValueError 交给 API 层映射为 409。"""

        document_uuid = self._safe_uuid(document_id)
        if not document_uuid:
            return None
        document = self.db.get(Document, document_uuid)
        if not document or document.deleted_at is not None:
            return None
        if not (document.meta_json or {}).get("recycled_at"):
            raise ValueError("文档不在回收站中，请先移入回收站")
        return await self.purge_document(document_id, sync_chatdoc=sync_chatdoc, doc_service=doc_service)

    def _purge_document_row(self, document: Document) -> dict:
        result = {"document_id": str(document.id), "title": document.title, "filename": document.filename}
        now = datetime.now(timezone.utc)
        document.deleted_at = now
        document.cleanup_queued_at = now
        document.parse_status = "deleted"
        document.vector_status = "skipped"
        document.text_vector_status = "skipped"
        document.visual_vector_status = "skipped"
        document.publish_readiness = "blocked"
        self.db.execute(
            update(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .values(lifecycle_status="deleted", embedding_status="skipped", embedding_deleted_at=now)
        )
        self.db.execute(
            update(DocumentPage)
            .where(DocumentPage.document_id == document.id)
            .values(lifecycle_status="deleted", visual_embedding_status="skipped", embedding_status="skipped", visual_embedding_deleted_at=now)
        )
        self.db.flush()
        result["cleanup"] = self._cleanup_document_files(str(document.id))
        result["status"] = "purged"
        return result

    def delete_document(self, document_id: str) -> dict | None:
        """默认删除为软回收，会保留 ChatDoc 向量以供 RAG 使用。"""
        return self.recycle_document(document_id)

    def _cleanup_document_files(self, document_id: str) -> dict:
        document = self.db.get(Document, self._safe_uuid(document_id))
        if not document:
            return {"status": "not_found"}
        course = self.db.get(Course, document.course_id)
        if not course:
            return {"status": "skipped", "reason": "course_not_found"}
        removed_dirs: list[str] = []
        removed_files: list[str] = []
        storage_root = Path(settings.OBJECT_STORAGE_ROOT).expanduser().resolve() / "documents"
        course_root = storage_root / course.slug
        doc_root = course_root / str(document.id)
        if doc_root.is_dir():
            shutil.rmtree(doc_root, ignore_errors=True)
            removed_dirs.append(str(doc_root))
        if document.file_uri:
            others = self.db.execute(
                select(Document.id)
                .where(Document.file_uri == document.file_uri, Document.id != document.id, Document.deleted_at.is_(None))
                .limit(1)
            ).scalar_one_or_none()
            if not others:
                src = Path(document.file_uri).expanduser().resolve()
                if src.is_file():
                    try:
                        src.relative_to(storage_root)
                    except ValueError:
                        pass
                    else:
                        src.unlink(missing_ok=True)
                        removed_files.append(str(src))
        if course_root.is_dir() and not any(course_root.iterdir()):
            course_root.rmdir()
            removed_dirs.append(str(course_root))
        document.cleanup_completed_at = datetime.now(timezone.utc)
        self.db.flush()
        return {"status": "completed", "removed_dirs": removed_dirs, "removed_files": removed_files}
