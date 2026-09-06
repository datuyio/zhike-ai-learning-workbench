from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Counter, TypedDict, cast

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.tracing import get_trace_id
from app.models import (
    Course,
    CourseConcept,
    CommunityResource,
    Document,
    DocumentChunk,
    DocumentPage,
    PathNode,
    Resource,
    ResourceAsset,
    ResourceGenerationTask,
    ResourceVersion,
    User,
)
from app.schemas.resource import ResourceGenerateRequest, ResourceReviewRequest, ResourceUpdateRequest
from app.services.resource.progress_events import publish_resource_task_progress
from app.services.resource.asset_service import ReferenceImageUploadPayload, ResourceAssetService
from app.services.resource.deletion_results import (
    ResourceBatchDeleteResult,
    ResourceDeleteResult,
)
from app.services.resource.deletion_service import ResourceDeletionService
from app.services.resource.curation_service import ResourceCurationService
from app.services.resource.generation_content_service import ResourceGenerationContentService
from app.services.resource.generation_workflow import run_resource_generation_workflow
from app.services.resource.generation_context_service import ResourceGenerationContextService
from app.services.resource.generation_retrieval_service import ResourceGenerationRetrievalService
from app.services.resource.generation_result_service import ResourceGenerationResultService
from app.services.resource.generation_course_service import ResourceCourseTaskRunner
from app.services.resource.generation_general_service import ResourceGeneralTaskRunner
from app.services.resource.diagram_pack_service import DiagramPackTaskRunner
from app.services.resource.review_service import ResourceReviewService
from app.services.resource import task_metadata
from app.services.resource.list_service import ResourceListService
from app.services.resource.resource_serializer import ResourceSerializerService
from app.services.resource.errors import ResourceTaskCancelled
from app.services.resource.task_metadata import RESOURCE_TASK_TERMINAL_STATUSES
from app.services.resource.task_payloads import ResourceTaskPayloadService
from app.services.resource.task_lifecycle_service import ResourceTaskLifecycleService
from app.services.resource.generation_task_service import ResourceGenerationTaskService
from app.services.resource.generation_task_query_service import ResourceGenerationTaskQueryService
from app.services.resource.upload_service import UploadedResourceService, slugify_resource_code, summarize_uploaded_content
from app.services.resource.version_service import ResourceVersionService
from app.services.resource.hall_helpers import (
    append_recommendation_evidence,
    compact_evidence_summary,
    hall_filter_options,
    hall_match_reason,
    hall_recommendation_score,
    hall_sort_time,
    is_featured_hall_resource,
    is_public_hall_resource,
    matches_hall_scope,
)
from app.services.resource.hall_service import ResourceHallService
from app.services.resource.hall_recommendation_service import ResourceHallRecommendationService

logger = logging.getLogger(__name__)

try:
    from langgraph.graph import END, StateGraph
except (ImportError, ModuleNotFoundError):  # pragma: no cover - 精简本地环境缺少可选依赖时的兜底。
    logger.info("可选依赖 langgraph 未安装，资源生成将使用顺序执行器。")
    END = "__end__"
    StateGraph = None  # type: ignore[assignment]


def _utc_iso() -> str:
    """返回当前 UTC 时间的 ISO 字符串。"""
    return datetime.now(timezone.utc).isoformat()


class ResourceGenerationState(TypedDict, total=False):
    """资源生成工作流在各节点之间传递的状态载荷。"""

    task_id: str
    task: ResourceGenerationTask
    course: Course | None
    concept: CourseConcept | None
    profile_summary: str
    profile_context_snapshot: str
    mastery_context: str
    recent_dialog: str
    personalization: dict
    citations: list[dict]
    content: str
    quality: dict
    safety_status: str
    resource: Resource


class ResourceAssetAccessContext(TypedDict):
    """资源资产访问校验所需的最小上下文。"""

    course_id: str | None
    resource_status: str | None
    is_owner: bool


def _safe_uuid(value: str | None) -> uuid.UUID | None:
    """把外部传入的字符串安全转换为 UUID，非法输入返回 None。"""
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _course_identity_clause(course_slug: str) -> Any:
    """按课程 slug 或 UUID 构造筛选条件。"""
    clauses = [Course.slug == course_slug]
    course_uuid = _safe_uuid(course_slug)
    if course_uuid:
        clauses.append(Course.id == course_uuid)
    return or_(*clauses)


def _resource_identity_clause(resource_code: str) -> Any:
    """按资源 code 或 UUID 构造筛选条件。"""
    clauses = [Resource.code == resource_code]
    resource_uuid = _safe_uuid(resource_code)
    if resource_uuid:
        clauses.append(Resource.id == resource_uuid)
    return or_(*clauses)


class ResourceRepository:
    """资源、资源大厅、生成任务和版本操作的仓储门面。"""

    def __init__(self, db: Session) -> None:
        """初始化资源仓储门面及其下游资产、任务载荷和列表服务。"""
        self.db = db
        self.asset_service = ResourceAssetService(db)
        self.task_payload_service = ResourceTaskPayloadService(db, self.asset_service)
        self.upload_service = UploadedResourceService(db)
        self.deletion_service = ResourceDeletionService(db, utc_iso=_utc_iso)
        self.curation_service = ResourceCurationService(db, utc_iso=_utc_iso)
        self.resource_serializer = ResourceSerializerService(db, self.asset_service)
        self.list_service = ResourceListService(
            db,
            resource_serializer=self.resource_to_dict,
            knowledge_citation_checker=self._has_live_knowledge_citation,
        )

    def _course(self, slug_or_id: str) -> Course | None:
        """按课程 slug 或 UUID 查询课程实体。"""
        return self.db.execute(
            select(Course).where(or_(Course.slug == slug_or_id, Course.id == _safe_uuid(slug_or_id)))
        ).scalar_one_or_none()

    def _concept(self, course: Course, code_or_id: str | None) -> CourseConcept | None:
        """在指定课程下按知识点 code 或 UUID 查询知识点实体。"""
        if not code_or_id:
            return None
        return self.db.execute(
            select(CourseConcept).where(
                CourseConcept.course_id == course.id,
                or_(CourseConcept.code == code_or_id, CourseConcept.id == _safe_uuid(code_or_id)),
            )
        ).scalar_one_or_none()

    def _path_node(self, node_id: str | None) -> PathNode | None:
        """按路径节点 UUID 或 code 查询学习路径节点。"""
        if not node_id:
            return None
        node_uuid = _safe_uuid(node_id)
        if node_uuid:
            return self.db.get(PathNode, node_uuid)
        return self.db.execute(select(PathNode).where(PathNode.code == node_id).order_by(PathNode.updated_at.desc())).scalars().first()

    def _user(self, external_id: str | None) -> User | None:
        """按外部用户 ID 查询用户实体。"""
        if not external_id:
            return None
        return self.db.execute(select(User).where(User.external_id == external_id)).scalar_one_or_none()

    def get_course_by_slug_or_id(self, slug_or_id: str) -> Course | None:
        """按 slug 或 UUID 读取课程，供 API 层避免穿透私有查询 helper。"""
        return self._course(slug_or_id)

    def get_user_by_external_id(self, external_id: str | None) -> User | None:
        """按外部用户 ID 读取用户实体。"""
        return self._user(external_id)

    def get_asset_access_context(self, asset: ResourceAsset, user_external_id: str | None) -> ResourceAssetAccessContext:
        """读取资产访问校验需要的课程、资源状态和归属信息。"""
        user = self._user(user_external_id)
        resource = self.db.get(Resource, asset.resource_id) if asset.resource_id else None
        course_id = resource.course_id if resource else asset.course_id
        return {
            "course_id": str(course_id) if course_id else None,
            "resource_status": resource.status if resource else None,
            "is_owner": bool(user and asset.created_by_user_id and asset.created_by_user_id == user.id),
        }

    def _ensure_resource_write_access(self, resource: Resource, user_external_id: str | None, *, is_admin: bool = False) -> None:
        """校验当前用户是否可以编辑资源或恢复资源版本。"""
        if is_admin:
            return
        user = self._user(user_external_id)
        if not user or resource.created_by_user_id != user.id:
            raise PermissionError("无权修改该资源")

    def _resource_by_code(self, resource_id: str, *, include_deleted: bool = False) -> Resource | None:
        """按资源 code 或 UUID 查询资源，默认排除已删除资源。"""
        stmt = select(Resource).where(or_(Resource.code == resource_id, Resource.id == _safe_uuid(resource_id)))
        if not include_deleted:
            stmt = stmt.where(Resource.status != "deleted")
        return self.db.execute(stmt.order_by(Resource.updated_at.desc(), Resource.created_at.desc()).limit(1)).scalars().first()

    def _has_live_knowledge_citation(self, resource: Resource) -> bool:
        """判断资源引用中是否仍存在可追溯的知识库对象。"""
        for citation in resource.citations_json or []:
            if not isinstance(citation, dict):
                continue
            chunk_id = _safe_uuid(str(citation.get("chunk_id") or ""))
            if chunk_id and self.db.get(DocumentChunk, chunk_id):
                return True
            page_asset_id = _safe_uuid(str(citation.get("page_asset_id") or ""))
            if page_asset_id and self.db.get(DocumentPage, page_asset_id):
                return True
            source_id = _safe_uuid(str(citation.get("source_id") or citation.get("document_id") or ""))
            if source_id and self.db.get(Document, source_id):
                return True
        return False

    @staticmethod
    def _task_orchestration(task: ResourceGenerationTask) -> dict[str, Any]:
        """读取任务编排元数据，兼容迁移前创建的旧任务。"""
        return task_metadata.task_orchestration(task)

    @classmethod
    def _task_requires_course_evidence(cls, task: ResourceGenerationTask) -> bool:
        """判断资源生成任务是否必须先命中课程资料依据。"""
        return task_metadata.task_requires_course_evidence(task)

    @classmethod
    def _task_material_document_id(cls, task: ResourceGenerationTask) -> str | None:
        """读取资源生成任务绑定的资料文档 ID。"""
        return task_metadata.task_material_document_id(task)

    @staticmethod
    def _image_context_from_client_context(client_context: dict | None) -> dict:
        """读取前端传入的图片生成上下文。"""
        return task_metadata.image_context_from_client_context(client_context)

    @classmethod
    def _image_context_from_payload(cls, payload: ResourceGenerateRequest) -> dict:
        """读取创建任务请求中的图片生成参数。"""
        return task_metadata.image_context_from_payload(payload)

    @staticmethod
    def _course_image_provider(course: Course | None) -> str | None:
        """读取课程级图片生成供应商绑定。"""
        return task_metadata.course_image_provider(course)

    @classmethod
    def _image_provider_from_payload(cls, payload: ResourceGenerateRequest, course: Course | None) -> str | None:
        """解析任务创建时应使用的图片生成供应商。"""
        return task_metadata.image_provider_from_payload(payload, course)

    @classmethod
    def _image_context_from_task(cls, task: ResourceGenerationTask) -> dict:
        """读取任务编排元数据中的图片生成参数。"""
        return task_metadata.image_context_from_task(task)

    @classmethod
    def _image_provider_from_task(cls, task: ResourceGenerationTask, course: Course | None) -> str | None:
        """解析任务执行时应使用的图片生成供应商。"""
        return task_metadata.image_provider_from_task(task, course)

    @staticmethod
    def _generator_agent(resource_type: str) -> str:
        """按资源类型选择对外展示的生成智能体。"""
        return task_metadata.generator_agent(resource_type)

    @classmethod
    def _workflow_agents(cls, resource_type: str, *, need_course_evidence: bool, course_scope: bool) -> list[str]:
        """生成资源任务的概念智能体序列，用于 trace 和前端展示。"""
        return task_metadata.workflow_agents(resource_type, need_course_evidence=need_course_evidence, course_scope=course_scope)

    @classmethod
    def _initial_task_steps(cls, resource_type: str, *, course_scope: bool, need_course_evidence: bool, topic: str | None = None) -> list[dict]:
        """构造当前执行节点使用的任务步骤。"""
        return task_metadata.initial_task_steps(
            resource_type,
            course_scope=course_scope,
            need_course_evidence=need_course_evidence,
            topic=topic,
        )

    @staticmethod
    def _step_phase(steps: list[dict], index: int) -> str:
        """读取步骤对应的对外任务阶段。"""
        return task_metadata.step_phase(steps, index)

    @staticmethod
    def _current_agent_from_steps(steps: list[dict]) -> str | None:
        """从步骤列表中推导当前智能体名称。"""
        return task_metadata.current_agent_from_steps(steps)

    def _normalized_task_status(self, task: ResourceGenerationTask) -> str:
        """将旧任务状态映射为 docs 05 的对外状态枚举。"""
        return task_metadata.normalized_task_status(task)

    @staticmethod
    def _task_error_code(message: str | None) -> str | None:
        """将内部错误归类为前端可用的错误码。"""
        return task_metadata.task_error_code(message)

    @staticmethod
    def _safe_personalization_summary(personalization: dict[str, Any] | None) -> dict[str, Any]:
        """返回可展示的画像适配摘要，避免泄露完整画像快照。"""
        return task_metadata.safe_personalization_summary(personalization)

    def _raise_if_cancelled(self, task: ResourceGenerationTask) -> None:
        """在阶段边界检查用户取消状态。"""
        try:
            self.db.refresh(task)
        except Exception:
            logger.warning(
                "刷新资源生成任务取消状态失败，将由外层失败处理：task_id=%s status=%s trace_id=%s",
                getattr(task, "task_id", None),
                getattr(task, "status", None),
                get_trace_id(),
                exc_info=True,
            )
            raise
        if getattr(task, "status", None) == "cancelled":
            raise ResourceTaskCancelled("资源生成任务已取消")

    def _create_failed_generation_task(
        self,
        payload: ResourceGenerateRequest,
        user: User | None,
        course: Course | None,
        concept: CourseConcept | None,
        path_node: PathNode | None,
        *,
        message: str,
        need_course_evidence: bool,
    ) -> dict:
        """兼容旧内部入口，实际创建逻辑由资源生成任务服务维护。"""
        return self._generation_task_service().create_failed_generation_task(
            payload,
            user,
            course,
            concept,
            path_node,
            message=message,
            need_course_evidence=need_course_evidence,
        )

    def _course_slug_by_id(self, course_id: uuid.UUID | None) -> str | None:
        """按课程 ID 读取对外课程标识，兼容旧内部调用入口。"""
        return self.task_payload_service.course_slug_by_id(course_id)

    def _latest_version(self, resource_id: uuid.UUID) -> ResourceVersion | None:
        """读取资源最新版本，供编辑和版本恢复流程复用。"""
        return self._resource_version_service().latest_version(resource_id)

    def _next_version_number(self, resource_id: uuid.UUID) -> int:
        """计算资源下一次保存应使用的版本号。"""
        return self._resource_version_service().next_version_number(resource_id)

    @staticmethod
    def _asset_file_url(asset_id: uuid.UUID | str) -> str:
        """生成受鉴权资产文件接口路径。"""
        return ResourceAssetService.asset_file_url(asset_id)

    def _asset_to_dict(self, asset: ResourceAsset) -> dict[str, object]:
        """将资源资产转换为前端画廊可消费的结构。"""
        return self.asset_service.asset_to_dict(asset)

    def resource_asset_to_dict(self, asset: ResourceAsset) -> dict[str, object]:
        """对外序列化单个资源资产。"""
        return self.asset_service.resource_asset_to_dict(asset)

    def resource_assets_to_dict(self, assets: list[ResourceAsset]) -> list[dict[str, object]]:
        """对外批量序列化资源资产。"""
        return self.asset_service.resource_assets_to_dict(assets)

    def _assets_for_resource(self, resource_id: uuid.UUID | None) -> list[dict[str, object]]:
        """读取资源下的图片资产，MagicMock 测试环境下返回空列表。"""
        return self.asset_service.assets_for_resource(resource_id)

    def _assets_for_task(self, task_id: uuid.UUID | None) -> list[dict[str, object]]:
        """读取任务临时资产，任务完成前也可用于画布预览。"""
        return self.asset_service.assets_for_task(task_id)

    def _storage_root(self) -> Path:
        """兼容旧内部入口，实际存储根目录由资产服务管理。"""
        return self.asset_service.storage_root()

    def _absolute_asset_path(self, file_path: str | None) -> Path | None:
        """解析资产文件路径并确保仍在对象存储根目录内。"""
        return self.asset_service.absolute_asset_path(file_path)

    def get_resource_asset(self, asset_id: str) -> ResourceAsset | None:
        """按 ID 读取资源资产。"""
        return self.asset_service.get_resource_asset(asset_id)

    def asset_file_path(self, asset: ResourceAsset) -> Path | None:
        """返回资产真实文件路径。"""
        return self.asset_service.asset_file_path(asset)

    def create_reference_image_asset(
        self,
        *,
        data: bytes,
        filename: str,
        mime_type: str,
        course: Course | None,
        user: User | None,
        sort_order: int,
    ) -> ResourceAsset:
        """保存用户上传的参考图资产。"""
        return self.asset_service.create_reference_image_asset(
            data=data,
            filename=filename,
            mime_type=mime_type,
            course=course,
            user=user,
            sort_order=sort_order,
        )

    def create_reference_image_assets(
        self,
        uploads: list[ReferenceImageUploadPayload],
        *,
        course_id: str | None,
        user_external_id: str | None,
    ) -> list[ResourceAsset] | None:
        """按课程和用户上下文批量保存参考图资产，供 API 层调用公共入口。

        参数:
            uploads: 已校验的参考图上传载荷。
            course_id: 可选课程 slug 或 UUID；传入但找不到课程时返回 None。
            user_external_id: 当前登录用户的外部 ID。

        返回:
            成功时返回资产列表；指定课程不存在时返回 None。
        """
        course = self._course(course_id) if course_id else None
        if course_id and not course:
            return None
        user = self._user(user_external_id)
        return self.asset_service.create_reference_image_assets(uploads, course=course, user=user)

    def upload_reference_image_assets(
        self,
        uploads: list[ReferenceImageUploadPayload],
        *,
        course_id: str | None,
        user_external_id: str | None,
    ) -> dict[str, object] | None:
        """保存参考图上传并返回 API 响应载荷。

        参数:
            uploads: 已完成大小和 MIME 校验的参考图上传载荷。
            course_id: 可选课程 slug 或 UUID；传入但找不到课程时返回 None。
            user_external_id: 当前登录用户的外部 ID。

        返回:
            成功时返回参考图上传响应字典；指定课程不存在时返回 None。
        """

        assets = self.create_reference_image_assets(uploads, course_id=course_id, user_external_id=user_external_id)
        if assets is None:
            return None
        self.db.commit()
        return {"items": self.resource_assets_to_dict(assets), "count": len(assets)}

    def resource_to_dict(self, resource: Resource, course_slug: str | None = None, include_content: bool = False) -> dict:
        """将资源实体序列化为前端资源大厅和详情页使用的字典，兼容旧调用入口。"""

        return self.resource_serializer.resource_to_dict(resource, course_slug, include_content)

    def _resource_review_service(self) -> ResourceReviewService:
        """创建资源审核服务，延迟绑定序列化回调以兼容测试替换。"""
        return ResourceReviewService(self.db, resource_serializer=self.resource_to_dict)

    def _resource_version_service(self, *, is_admin: bool = False) -> ResourceVersionService:
        """创建资源版本服务，隔离版本查询、恢复和手动编辑职责。"""

        return ResourceVersionService(
            self.db,
            serialize_resource=lambda resource: self.resource_to_dict(resource, include_content=True),
            utc_iso=_utc_iso,
        )

    def _task_lifecycle_service(self) -> ResourceTaskLifecycleService:
        """创建任务生命周期服务，隔离大纲、取消和步骤状态更新职责。"""

        return ResourceTaskLifecycleService(
            self.db,
            task_payload_service=self.task_payload_service,
            progress_publisher=publish_resource_task_progress,
        )

    def _generation_task_service(self) -> ResourceGenerationTaskService:
        """创建资源生成任务命令服务，隔离创建、重跑和终态落库职责。"""

        return ResourceGenerationTaskService(
            self.db,
            task_payload_service=self.task_payload_service,
            progress_publisher=publish_resource_task_progress,
        )

    def _generation_task_query_service(self) -> ResourceGenerationTaskQueryService:
        """创建资源生成任务查询服务，隔离列表筛选和访问控制职责。"""

        return ResourceGenerationTaskQueryService(
            self.db,
            task_payload_service=self.task_payload_service,
        )

    def _generation_context_service(self) -> ResourceGenerationContextService:
        """创建资源生成上下文服务，隔离画像、掌握度和近期对话查询职责。"""

        return ResourceGenerationContextService(self.db, update_task_step=self.update_task_step)

    def _generation_result_service(self) -> ResourceGenerationResultService:
        """创建资源生成结果服务，隔离质量核验和生成结果保存职责。"""

        return ResourceGenerationResultService(
            self.db,
        )

    def _generation_content_service(self) -> ResourceGenerationContentService:
        """创建资源正文生成服务，隔离模型调用、草稿分片和本地模板兜底。"""

        return ResourceGenerationContentService(self.db, update_task_draft=self.update_task_draft)

    def _course_task_runner(self) -> ResourceCourseTaskRunner:
        """创建课程资源生成节点编排器，隔离 LangGraph 节点业务实现。"""

        return ResourceCourseTaskRunner(
            self.db,
            content_service=self._generation_content_service(),
            result_service=self._generation_result_service(),
            update_task_step=self.update_task_step,
            update_task_draft=self.update_task_draft,
            emit_task_progress=self._emit_task_progress,
        )

    def _generation_retrieval_service(self) -> ResourceGenerationRetrievalService:
        """创建资源生成检索服务，隔离课程 RAG 检索和草稿标题占位职责。"""

        return ResourceGenerationRetrievalService(
            self.db,
            update_task_step=self.update_task_step,
            update_task_draft=self.update_task_draft,
        )

    def _community_for_resource(self, resource_id: uuid.UUID) -> CommunityResource | None:
        """兼容旧私有入口，实际查询交给资源审核服务。"""
        return self._resource_review_service().community_for_resource(resource_id)

    def _review_item_to_dict(self, community: CommunityResource, include_content: bool = False) -> dict:
        """兼容旧私有入口，实际序列化交给资源审核服务。"""
        return self._resource_review_service().review_item_to_dict(community, include_content=include_content)

    def list_review_queue(
        self,
        course_slug: str | None = None,
        review_status: str | None = None,
        limit: int = 80,
    ) -> list[dict]:
        """列出资源审核队列，保留仓储公共入口并委托审核服务。"""
        return self._resource_review_service().list_review_queue(
            course_slug=course_slug,
            review_status=review_status,
            limit=limit,
        )

    def get_review_item(self, resource_code: str) -> dict | None:
        """读取资源审核详情，保留仓储公共入口并委托审核服务。"""
        return self._resource_review_service().get_review_item(resource_code)

    def review_stats(self, course_slug: str | None = None) -> dict:
        """统计资源审核指标，保留仓储公共入口并委托审核服务。"""
        return self._resource_review_service().review_stats(course_slug)

    def list_review_logs(
        self,
        course_slug: str | None = None,
        resource_code: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """列出资源审核日志，保留仓储公共入口并委托审核服务。"""
        return self._resource_review_service().list_review_logs(
            course_slug=course_slug,
            resource_code=resource_code,
            limit=limit,
        )

    def review_resource(
        self,
        resource_code: str,
        payload: ResourceReviewRequest,
        reviewer_external_id: str | None = None,
    ) -> dict | None:
        """执行资源审核动作，保留仓储公共入口并委托审核服务。"""
        return self._resource_review_service().review_resource(resource_code, payload, reviewer_external_id)

    def _resource_hall_service(self) -> ResourceHallService:
        """创建资源大厅聚合服务，保留仓储门面与序列化回调。"""
        return ResourceHallService(
            self.db,
            resource_serializer=self.resource_to_dict,
        )

    @staticmethod
    def _is_public_hall_resource(resource: Resource, community: CommunityResource | None = None) -> bool:
        """判断资源是否可作为社区资源展示，兼容仓储内既有调用。"""
        return is_public_hall_resource(resource, community)

    @staticmethod
    def _is_featured_hall_resource(resource: Resource, community: CommunityResource | None = None) -> bool:
        """判断资源是否属于大厅精选，兼容仓储内既有调用。"""
        return is_featured_hall_resource(resource, community)

    @staticmethod
    def _hall_recommendation_score(
        resource: Resource,
        *,
        current_course: Course | None,
        community: CommunityResource | None = None,
    ) -> float:
        """按质量、引用、复用和课程相关度计算大厅推荐分。"""
        return hall_recommendation_score(resource, current_course=current_course, community=community)

    @staticmethod
    def _hall_match_reason(resource: Resource, *, current_course: Course | None, score: float) -> str:
        """生成前端卡片上可读的推荐原因。"""
        return hall_match_reason(resource, current_course=current_course, score=score)

    @staticmethod
    def _compact_evidence_summary(value: Any, limit: int = 96) -> str:
        """压缩推荐证据文案，避免资源卡片出现长文本溢出。"""
        return compact_evidence_summary(value, limit=limit)

    @classmethod
    def _append_recommendation_evidence(
        cls,
        items: list[dict],
        *,
        key: str,
        label: str,
        summary: Any,
        source: str,
        score: int | None = None,
    ) -> None:
        """追加去重后的推荐解释证据。"""
        append_recommendation_evidence(items, key=key, label=label, summary=summary, source=source, score=score)

    def _hall_recommendation_service(self) -> ResourceHallRecommendationService:
        """创建资源大厅推荐解释服务，隔离画像和学习事件证据读取。"""
        return ResourceHallRecommendationService(self.db)

    def _profile_weak_point_labels(self, *, current_course: Course | None, current_user: User | None) -> list[str]:
        """读取当前课程画像中的薄弱点标签，用于资源大厅推荐解释。"""
        return self._hall_recommendation_service().profile_weak_point_labels(
            current_course=current_course,
            current_user=current_user,
        )

    def _concept_mastery_evidence(
        self,
        resource: Resource,
        *,
        current_user: User | None,
    ) -> tuple[int, str] | None:
        """读取资源绑定知识点的掌握度短板。"""
        return self._hall_recommendation_service().concept_mastery_evidence(resource, current_user=current_user)

    def _recent_learning_event_evidence(
        self,
        resource: Resource,
        *,
        current_course: Course | None,
        current_user: User | None,
    ) -> str | None:
        """读取最近学习事件，说明推荐与近期学习行为的关系。"""
        return self._hall_recommendation_service().recent_learning_event_evidence(
            resource,
            current_course=current_course,
            current_user=current_user,
        )

    def _hall_recommendation_evidence(
        self,
        resource: Resource,
        *,
        current_course: Course | None,
        current_user: User | None,
        community: CommunityResource | None,
        score: float,
    ) -> list[dict]:
        """构造资源大厅可解释推荐证据。"""
        return self._hall_recommendation_service().recommendation_evidence(
            resource,
            current_course=current_course,
            current_user=current_user,
            community=community,
            score=score,
        )

    def _hall_search_text(
        self,
        resource: Resource,
        *,
        current_course: Course | None,
        current_user: User | None,
        community: CommunityResource | None,
        score: float,
    ) -> str:
        """拼接资源大厅可搜索文本，覆盖推荐理由和推荐证据。"""
        return self._hall_recommendation_service().search_text(
            resource,
            current_course=current_course,
            current_user=current_user,
            community=community,
            score=score,
        )

    @staticmethod
    def _hall_filter_options(counts: Counter[str], labels: dict[str, str]) -> list[dict]:
        """把计数器转换为前端筛选项。"""
        return hall_filter_options(counts, labels)

    @staticmethod
    def _hall_sort_time(resource: Resource) -> str:
        """返回稳定的资源更新时间排序键。"""
        return hall_sort_time(resource)

    def _hall_item_to_dict(
        self,
        resource: Resource,
        course: Course | None,
        *,
        current_course: Course | None,
        current_user: User | None,
        community: CommunityResource | None = None,
        recommended: bool = False,
    ) -> dict:
        """构造资源大厅专用资源卡片数据。"""
        return self._resource_hall_service().item_to_dict(
            resource,
            course,
            current_course=current_course,
            current_user=current_user,
            community=community,
            recommended=recommended,
        )

    @staticmethod
    def _matches_hall_scope(item: dict, scope: str, current_course_slug: str | None) -> bool:
        """判断大厅资源是否命中当前范围筛选。"""
        return matches_hall_scope(item, scope, current_course_slug)

    @staticmethod
    def _is_owned_by_current_user(resource: Resource, current_user: User | None) -> bool:
        """判断资源是否属于当前用户，兼容测试中的轻量对象。"""
        return bool(current_user and resource.created_by_user_id == current_user.id)

    def _matches_hall_scope_resource(
        self,
        resource: Resource,
        *,
        community: CommunityResource | None,
        current_course: Course | None,
        current_user: User | None,
        recommended_ids: set[uuid.UUID],
        scope: str,
    ) -> bool:
        """直接基于 ORM 对象判断大厅范围，避免先把全量资源转成前端字典。"""
        return self._resource_hall_service().matches_scope_resource(
            resource,
            community=community,
            current_course=current_course,
            current_user=current_user,
            recommended_ids=recommended_ids,
            scope=scope,
        )

    def list_resource_hall(
        self,
        *,
        course_slug: str | None = None,
        current_user_external_id: str | None = None,
        query: str | None = None,
        scope: str = "all",
        resource_type: str | None = None,
        difficulty: str | None = None,
        page: int = 1,
        page_size: int = 12,
    ) -> dict:
        """返回资源大厅聚合视图，包含资源、筛选项、统计和高亮区域。"""
        return self._resource_hall_service().list_resource_hall(
            course_slug=course_slug,
            current_user_external_id=current_user_external_id,
            query=query,
            scope=scope,
            resource_type=resource_type,
            difficulty=difficulty,
            page=page,
            page_size=page_size,
        )

    def list_resources(
        self,
        course_slug: str | None = None,
        concept_code: str | None = None,
        resource_type: str | None = None,
        difficulty: str | None = None,
        public_only: bool = False,
        require_knowledge_link: bool = False,
        user_external_id: str | None = None,
        include_all: bool = False,
    ) -> list[dict]:
        """按课程、知识点和资源属性筛选资源列表，兼容旧调用入口。"""

        current_user = self._user(user_external_id)
        return self.list_service.list_resources(
            course_slug=course_slug,
            concept_code=concept_code,
            resource_type=resource_type,
            difficulty=difficulty,
            public_only=public_only,
            require_knowledge_link=require_knowledge_link,
            current_user=current_user,
            include_all=include_all,
        )

    def _can_read_resource(self, resource: Resource, user_external_id: str | None, *, is_admin: bool = False) -> bool:
        """判断当前用户是否可读取资源正文。公开资源可读，私有资源仅创建者和管理员可读。"""

        if is_admin or resource.status in {"published", "featured"}:
            return True
        user = self._user(user_external_id)
        return bool(user and resource.created_by_user_id == user.id)

    def get_resource(self, resource_code: str, user_external_id: str | None = None, *, is_admin: bool = False) -> dict | None:
        """读取单个资源详情，并携带最新版本内容；私有资源必须校验归属。"""

        row = self.db.execute(
            select(Resource, Course).join(Course, Course.id == Resource.course_id, isouter=True).where(
                Resource.status != "deleted",
                or_(Resource.code == resource_code, Resource.id == _safe_uuid(resource_code)),
            )
        ).first()
        if not row:
            return None
        if not self._can_read_resource(row[0], user_external_id, is_admin=is_admin):
            raise PermissionError("无权查看该资源")
        return self.resource_to_dict(row[0], row[1].slug if row[1] else None, include_content=True)

    def create_generation_task(self, payload: ResourceGenerateRequest, user_external_id: str | None = None) -> dict:
        """创建资源生成任务，并在不可生成时返回失败任务摘要。"""

        return self._generation_task_service().create_generation_task(payload, user_external_id)

    def get_generation_task(self, task_id: str, user_external_id: str | None = None, *, is_admin: bool = False) -> dict | None:
        """读取资源生成任务详情，并按需校验用户访问权限。"""

        return self._generation_task_query_service().get_generation_task(
            task_id,
            user_external_id=user_external_id,
            is_admin=is_admin,
        )

    def list_generation_tasks(
        self,
        course_slug: str | None = None,
        limit: int = 20,
        user_external_id: str | None = None,
        *,
        include_all: bool = True,
    ) -> list[dict]:
        """列出资源生成任务，支持课程和当前用户范围过滤。"""

        return self._generation_task_query_service().list_generation_tasks(
            course_slug,
            limit=limit,
            user_external_id=user_external_id,
            include_all=include_all,
        )

    def task_to_dict(self, task: ResourceGenerationTask, course_slug: str | None = None) -> dict[str, Any]:
        """将资源生成任务实体序列化为前端轮询和 WebSocket 推送载荷。"""

        return self.task_payload_service.task_to_dict(task, course_slug)

    @staticmethod
    def _citations_from_task_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """从任务步骤中提取生成前检索到的真实引用依据。"""
        return ResourceTaskPayloadService.citations_from_task_steps(steps)

    @staticmethod
    def _task_error_fields(message: str | None) -> dict[str, str | None]:
        """把内部错误信息转换为安全的摘要和根因字段。"""
        return ResourceTaskPayloadService.task_error_fields(message)

    def _emit_task_progress(self, task: ResourceGenerationTask) -> None:
        """发布资源生成任务进度事件，供 WebSocket 网关转发。"""
        self._task_lifecycle_service().emit_task_progress(task)

    def update_task_draft(self, task: ResourceGenerationTask, content: str, progress: int | None = None) -> None:
        """更新任务草稿内容、进度和可编辑大纲。"""

        self._raise_if_cancelled(task)
        self.task_payload_service.update_task_draft(
            task,
            content,
            progress,
            publisher=publish_resource_task_progress,
        )

    def update_generation_task_outline(
        self,
        task_id: str,
        sections: list[dict],
        user_external_id: str | None = None,
        *,
        is_admin: bool = False,
    ) -> dict | None:
        """按用户调整后的顺序更新生成任务大纲。"""

        task = self.db.get(ResourceGenerationTask, _safe_uuid(task_id))
        if not task:
            return None
        return self._task_lifecycle_service().update_generation_task_outline(
            task,
            sections,
            user_external_id,
            is_admin=is_admin,
        )

    def rerun_generation_task(
        self,
        task_id: str,
        need_course_evidence: bool | None = None,
        user_external_id: str | None = None,
        *,
        is_admin: bool = False,
    ) -> dict | None:
        """重置资源生成任务并允许覆盖课程资料依据策略。"""
        return self._generation_task_service().rerun_generation_task(
            task_id,
            need_course_evidence,
            user_external_id,
            is_admin=is_admin,
        )

    def cancel_generation_task(
        self,
        task_id: str,
        user_external_id: str | None = None,
        *,
        is_admin: bool = False,
    ) -> dict | None:
        """取消尚未完成的资源生成任务。"""
        task = self.db.get(ResourceGenerationTask, _safe_uuid(task_id))
        if not task:
            return None
        return self._task_lifecycle_service().cancel_generation_task(
            task,
            user_external_id,
            is_admin=is_admin,
        )

    def update_task_step(
        self,
        task: ResourceGenerationTask,
        index: int,
        status: str,
        detail: str | None = None,
        progress: int | None = None,
        citations: list[dict] | None = None,
    ) -> None:
        """更新生成任务的单个步骤状态，并同步整体任务状态。"""

        self._task_lifecycle_service().update_task_step(
            task,
            index,
            status,
            detail=detail,
            progress=progress,
            citations=citations,
        )

    async def run_generation_task(self, task_id: str) -> dict | None:
        """执行资源生成任务，并把成功、失败或取消结果落库。"""

        task = self.db.get(ResourceGenerationTask, _safe_uuid(task_id))
        if not task:
            return None
        if task.status == "cancelled":
            return self.task_to_dict(task, self._course_slug_by_id(task.course_id))
        course = self.db.get(Course, task.course_id) if task.course_id else None
        concept = self.db.get(CourseConcept, task.concept_id) if task.concept_id else None
        if task.course_id and not course:
            task.status = "failed"
            task.error_message = "course not found"
            self.db.commit()
            return self.task_to_dict(task)

        try:
            state: ResourceGenerationState = {"task_id": str(task.id), "task": task, "concept": concept}
            if course:
                state["course"] = course
            state = await run_resource_generation_workflow(
                state,
                resource_type=task.resource_type,
                has_course=bool(course),
                state_schema=ResourceGenerationState,
                state_graph=StateGraph,
                end_marker=END,
                run_diagram_pack_generation_task=self._run_diagram_pack_generation_task,
                run_general_generation_task=self._run_general_generation_task,
                run_generation_without_graph=self._run_generation_without_graph,
                retrieve_node=self._resource_node_retrieve,
                profile_node=self._resource_node_profile,
                generate_node=self._resource_node_generate,
                cite_check_node=self._resource_node_cite_check,
                safety_node=self._resource_node_safety,
                save_node=self._resource_node_save,
            )
            task = state["task"]
            resource = state.get("resource")
            return self._generation_task_service().mark_completed(task, course, resource)
        except ResourceTaskCancelled:
            return self._generation_task_service().mark_cancelled(task, course)
        except Exception as exc:
            trace_id = get_trace_id()
            logger.warning(
                "执行课程资源生成任务失败：task_id=%s public_task_id=%s resource_type=%s course_id=%s trace_id=%s exc_type=%s",
                getattr(task, "id", None),
                getattr(task, "task_id", None),
                getattr(task, "resource_type", None),
                getattr(course, "slug", None),
                trace_id,
                type(exc).__name__,
                exc_info=True,
            )
            try:
                self.db.rollback()
            except Exception:
                logger.debug(
                    "资源生成任务失败后回滚数据库会话失败：task_id=%s trace_id=%s",
                    getattr(task, "id", None),
                    trace_id,
                    exc_info=True,
                )
            try:
                return self._generation_task_service().mark_failed(task, course, exc, trace_id=trace_id)
            except Exception as persist_exc:
                logger.warning(
                    "记录资源生成失败状态失败，保留原始生成异常：task_id=%s public_task_id=%s trace_id=%s persist_exc_type=%s",
                    getattr(task, "id", None),
                    getattr(task, "task_id", None),
                    trace_id,
                    type(persist_exc).__name__,
                    exc_info=True,
                )
                try:
                    self.db.rollback()
                except Exception:
                    logger.debug(
                        "记录资源生成失败状态失败后回滚数据库会话失败：task_id=%s trace_id=%s",
                        getattr(task, "id", None),
                        trace_id,
                        exc_info=True,
                    )
                raise exc from persist_exc

    async def _run_general_generation_task(self, state: ResourceGenerationState) -> ResourceGenerationState:
        """执行不绑定课程资料的通用资源生成流程。"""
        result = await ResourceGeneralTaskRunner(
            context_service=self._generation_context_service(),
            content_service=self._generation_content_service(),
            result_service=self._generation_result_service(),
            update_task_step=self.update_task_step,
            update_task_draft=self.update_task_draft,
        ).run(dict(state))
        return cast(ResourceGenerationState, result)

    async def _run_diagram_pack_generation_task(self, state: ResourceGenerationState) -> ResourceGenerationState:
        """生成教学图解包，并保存真实图片资产。"""
        result = await DiagramPackTaskRunner(
            self.db,
            self.asset_service,
            update_task_step=self.update_task_step,
            update_task_draft=self.update_task_draft,
            retrieve_node=self._resource_node_retrieve,
            profile_node=self._resource_node_profile,
            save_generated_resource=self._save_generated_resource,
            asset_to_dict=self._asset_to_dict,
        ).run(dict(state))
        return cast(ResourceGenerationState, result)

    async def _run_generation_without_graph(self, state: ResourceGenerationState) -> ResourceGenerationState:
        """在缺少 LangGraph 依赖时按固定顺序执行资源生成节点。"""
        result = await self._course_task_runner().run_without_graph(
            dict(state),
            retrieve_node=self._resource_node_retrieve,
            profile_node=self._resource_node_profile,
        )
        return cast(ResourceGenerationState, result)

    async def _resource_node_retrieve(self, state: ResourceGenerationState) -> ResourceGenerationState:
        """执行课程资料检索节点，并把引用依据写入任务草稿上下文。"""
        return await self._generation_retrieval_service().retrieve_node(state)

    def _resource_node_profile(self, state: ResourceGenerationState) -> ResourceGenerationState:
        """执行学习画像节点，生成画像、掌握度和近期对话上下文。"""
        return self._generation_context_service().resolve_profile_state(state)

    def _mastery_context_for_task(self, task: ResourceGenerationTask) -> str:
        """兼容旧私有入口，实际查询交给资源生成上下文服务。"""
        return self._generation_context_service().mastery_context_for_task(task)

    def _recent_dialog_for_task(self, task: ResourceGenerationTask) -> str:
        """兼容旧私有入口，实际查询交给资源生成上下文服务。"""
        return self._generation_context_service().recent_dialog_for_task(task)

    async def _resource_node_generate(self, state: ResourceGenerationState) -> ResourceGenerationState:
        """执行正文生成节点，调用模型网关并同步任务草稿。"""
        result = await self._course_task_runner().generate_node(dict(state))
        return cast(ResourceGenerationState, result)

    def _resource_node_cite_check(self, state: ResourceGenerationState) -> ResourceGenerationState:
        """执行引用核验节点，并把引用覆盖状态写回任务编排元数据。"""
        result = self._course_task_runner().cite_check_node(dict(state))
        return cast(ResourceGenerationState, result)

    def _resource_node_safety(self, state: ResourceGenerationState) -> ResourceGenerationState:
        """执行安全审查节点，阻断被安全策略拒绝的生成结果。"""
        result = self._course_task_runner().safety_node(dict(state))
        return cast(ResourceGenerationState, result)

    def _resource_node_save(self, state: ResourceGenerationState) -> ResourceGenerationState:
        """执行资源保存节点，持久化资源实体和首个版本。"""
        result = self._course_task_runner().save_node(dict(state))
        return cast(ResourceGenerationState, result)

    async def _generate_resource_content(
        self,
        course: Course | None,
        concept: CourseConcept | None,
        task: ResourceGenerationTask,
        citations: list[dict],
        profile_summary: str | None = None,
        mastery_context: str | None = None,
        recent_dialog: str | None = None,
    ) -> str:
        """兼容旧私有入口，实际正文生成交给资源生成内容服务。"""
        return await self._generation_content_service().generate_resource_content(
            course,
            concept,
            task,
            citations,
            profile_summary=profile_summary,
            mastery_context=mastery_context,
            recent_dialog=recent_dialog,
        )

    async def _publish_draft_chunks(self, task: ResourceGenerationTask, content: str, chunk_size: int = 64) -> None:
        """兼容旧私有入口，实际草稿分片推送交给资源生成内容服务。"""
        await self._generation_content_service().publish_draft_chunks(task, content, chunk_size=chunk_size)

    def _local_resource_template(
        self,
        course: Course | None,
        concept: CourseConcept | None,
        task: ResourceGenerationTask,
        profile_summary: str | None = None,
    ) -> str:
        """兼容旧私有入口，实际本地模板生成交给资源生成内容服务。"""
        return self._generation_content_service().local_resource_template(course, concept, task, profile_summary)

    def _quality_check(self, content: str, citations: list[dict]) -> dict:
        """兼容旧私有入口，实际质量核验交给资源生成结果服务。"""
        return self._generation_result_service().quality_check(content, citations)

    def _save_generated_resource(
        self,
        course: Course | None,
        concept: CourseConcept | None,
        task: ResourceGenerationTask,
        content: str,
        citations: list[dict],
        quality: dict,
        safety_status: str,
        personalization: dict | None = None,
        profile_context_snapshot: str | None = None,
        extra_basis: dict | None = None,
    ) -> Resource:
        """兼容旧私有入口，实际结果落库交给资源生成结果服务。"""
        return self._generation_result_service().save_generated_resource(
            course,
            concept,
            task,
            content,
            citations,
            quality,
            safety_status,
            personalization=personalization,
            profile_context_snapshot=profile_context_snapshot,
            extra_basis=extra_basis,
        )

    @staticmethod
    def _summarize_content(content: str, fallback: str) -> str:
        """从 Markdown 正文中提取短摘要，内容为空时使用兜底文案。"""
        return summarize_uploaded_content(content, fallback)

    def create_uploaded_resource(
        self,
        *,
        title: str,
        summary: str | None,
        content: str,
        resource_type: str,
        difficulty: str,
        course_id: str | None = None,
        concept_id: str | None = None,
        path_node_id: str | None = None,
        user_external_id: str | None = None,
        source_filename: str | None = None,
        submit_for_review: bool = False,
    ) -> dict | None:
        """创建用户上传的个人资源，并保存首个正文版本。

        参数:
            title: 资源标题。
            summary: 可选摘要；为空时从正文自动截取。
            content: Markdown/TXT 正文内容。
            resource_type: 资源类型枚举。
            difficulty: 难度枚举。
            course_id: 可选课程 slug 或 UUID。
            concept_id: 可选知识点 code 或 UUID。
            path_node_id: 可选学习路径节点 code 或 UUID。
            user_external_id: 当前用户外部 ID。
            source_filename: 上传文件名；粘贴正文时为空。
            submit_for_review: 是否创建后直接提交资源大厅审核。

        返回:
            创建后的资源字典；课程不存在时返回 None。
        """
        course = self._course(course_id) if course_id else None
        if course_id and not course:
            return None
        concept = self._concept(course, concept_id) if course else None
        path_node = self._path_node(path_node_id)
        user = self._user(user_external_id)
        resource = self.upload_service.create_uploaded_resource(
            title=title,
            summary=summary,
            content=content,
            resource_type=resource_type,
            difficulty=difficulty,
            course=course,
            concept=concept,
            path_node=path_node,
            user=user,
            source_filename=source_filename,
            submit_for_review=submit_for_review,
        )
        return self.resource_to_dict(resource, course.slug if course else None, include_content=True)

    def list_versions(
        self,
        resource_code: str,
        user_external_id: str | None = None,
        *,
        is_admin: bool = False,
    ) -> dict:
        """列出指定资源的历史版本内容和版本元数据；私有资源必须校验归属。"""
        return self._resource_version_service(is_admin=is_admin).list_versions(
            resource_code,
            user_external_id,
            is_admin=is_admin,
        )

    def restore_version(
        self,
        resource_code: str,
        version_number: int,
        user_external_id: str | None = None,
        *,
        is_admin: bool = False,
    ) -> dict | None:
        """从历史版本恢复资源内容，并生成新的当前版本。"""
        return self._resource_version_service(is_admin=is_admin).restore_version(
            resource_code,
            version_number,
            user_external_id,
            is_admin=is_admin,
        )

    def update_resource(
        self,
        resource_code: str,
        payload: ResourceUpdateRequest,
        user_external_id: str | None = None,
        *,
        is_admin: bool = False,
    ) -> dict | None:
        """更新资源基础信息或追加手动编辑版本。"""
        return self._resource_version_service(is_admin=is_admin).update_resource(
            resource_code,
            payload,
            user_external_id,
            is_admin=is_admin,
        )

    def _mark_own_resource_deleted(self, resource: Resource, user: User) -> ResourceDeleteResult:
        """兼容旧内部调用点，将资源软删除委托给删除服务。"""
        return self.deletion_service.mark_own_resource_deleted(resource, user, self._community_for_resource(resource.id))

    def delete_own_resource(self, resource_code: str, user_external_id: str | None = None) -> ResourceDeleteResult | None:
        """软删除当前用户生成的资源，并保留版本记录用于审计。"""
        resource = self._resource_by_code(resource_code)
        if not resource:
            return None
        user = self._user(user_external_id)
        return self.deletion_service.delete_own_resource(
            resource=resource,
            user=user,
            community=self._community_for_resource(resource.id),
        )

    def batch_delete_own_resources(self, resource_codes: list[str], user_external_id: str | None = None) -> ResourceBatchDeleteResult:
        """批量软删除当前用户生成的资源，非本人资源只记录为拒绝项。"""
        user = self._user(user_external_id)
        targets = []
        for resource_code in resource_codes:
            resource = self._resource_by_code(resource_code)
            targets.append((resource_code, resource, self._community_for_resource(resource.id) if resource else None))
        return self.deletion_service.batch_delete_own_resources(targets=targets, user=user)

    def copy_resource(self, resource_code: str, user_external_id: str | None = None) -> dict | None:
        """复制资源为当前用户可编辑的私有副本。"""

        source = self._resource_by_code(resource_code)
        if not source:
            return None
        user = self._user(user_external_id)
        latest = self._latest_version(source.id)
        copy_code = slugify_resource_code(f"copy-{source.code}-{uuid.uuid4().hex[:6]}")
        copied = self.curation_service.copy_resource(
            source=source,
            latest_version=latest,
            user=user,
            copy_code=copy_code,
        )
        return self.resource_to_dict(copied, include_content=True)

    def submit_community(self, resource_code: str, user_external_id: str | None = None) -> dict:
        """将资源提交到社区审核队列。"""

        row = self.db.execute(
            select(Resource, Course).join(Course, Course.id == Resource.course_id, isouter=True).where(
                or_(Resource.code == resource_code, Resource.id == _safe_uuid(resource_code))
            )
        ).first()
        user = self._user(user_external_id)
        if not row:
            return {"resource_id": resource_code, "status": "not_found"}
        resource, course = row
        return self.curation_service.submit_community(resource=resource, course=course, user=user)

    def archive_resource_to_course(
        self,
        resource_code: str,
        *,
        course_id: str,
        concept_id: str | None = None,
        path_node_id: str | None = None,
        user_external_id: str | None = None,
    ) -> dict | None:
        """将通用资源归档到指定课程、知识点或路径节点下。"""

        resource = self._resource_by_code(resource_code)
        course = self._course(course_id)
        if not resource or not course:
            return None
        concept = self._concept(course, concept_id)
        path_node = self._path_node(path_node_id)
        user = self._user(user_external_id)
        community = self._community_for_resource(resource.id)
        archived = self.curation_service.archive_resource_to_course(
            resource=resource,
            course=course,
            concept=concept,
            path_node=path_node,
            user=user,
            community=community,
            requested_path_node_id=path_node_id,
        )
        return self.resource_to_dict(archived, course.slug, include_content=True)


async def process_resource_generation_task(task_id: str) -> None:
    """后台任务入口，自行持有数据库会话，避免复用请求会话。"""
    db = SessionLocal()
    try:
        await ResourceRepository(db).run_generation_task(task_id)
    finally:
        db.close()


def run_resource_generation_task_sync(task_id: str) -> None:
    """同步执行后台资源生成任务，供非异步调度器调用。"""

    asyncio.run(process_resource_generation_task(task_id))
