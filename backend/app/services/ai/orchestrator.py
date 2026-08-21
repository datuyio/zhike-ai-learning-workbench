from __future__ import annotations

import time
import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tracing import get_trace_id
from app.models import Course, ModelCallLog, User
from app.schemas.ai import AgentTraceEvent, AiAvailability, AiMessageRequest, AiMessageResponse, ChatQuality
from app.schemas.resource import ResourceGenerateRequest
from app.services.agent.workflow import AgentWorkflow
from app.services.ai.intent_router import HybridIntentRouter, IntentRoute
from app.services.knowledge.iflytek.config_service import ChatdocConfigService
from app.services.knowledge.iflytek.course_chat_binding import CourseChatdocBinding, resolve_course_chatdoc_binding
from app.services.knowledge.local_knowledge import LocalKnowledgeService
from app.services.learning.repository import LearningRepository
from app.services.model_gateway.router import ModelGateway
from app.services.rag.retriever import CourseRetriever
from app.services.resource.queue import enqueue_resource_generation
from app.services.resource.repository import ResourceRepository


CHAT_PROVIDER_UNAVAILABLE_MESSAGE = (
    "当前未配置 Chat 模型，暂时无法进行普通 AI 对话和资源生成。"
    "已配置的课程资料问答 / 云端 RAG 只能用于上传课程文档后的资料问答。"
    "请在网关中心添加 Chat 供应商后重试。"
)
COURSE_RAG_NO_HIT_MESSAGE = "当前课程资料中没有找到足够依据。你可以切换为普通 AI 问答，我将基于通用知识解释。"
COURSE_EVIDENCE_UNAVAILABLE_MESSAGE = (
    "当前课程资料还未完成云端向量化，无法基于课件生成。"
    "你可以继续使用普通 AI 生成，但不会带课程资料引用。"
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CourseAiBinding:
    """课程 AI 能力绑定快照。"""

    course_id: str
    chat_provider_id: str | None
    cloud_rag_provider_id: str | None
    remote_knowledge_base_id: str | None
    default_answer_mode: str
    allow_rag_fallback_to_chat: bool
    require_citation_for_course_answer: bool
    default_use_course_evidence_for_resource: bool
    is_enabled: bool
    chatdoc: CourseChatdocBinding | None = None
    local_rag_ready: bool = False
    local_ready_document_count: int = 0
    local_ready_chunk_count: int = 0

    @property
    def cloud_rag_ready(self) -> bool:
        """判断课程云端 RAG 是否可用于资料问答。"""
        return bool(self.is_enabled and self.chatdoc and self.chatdoc.knowledge_ready and self.chatdoc.primary_file_id)

    @property
    def rag_ready(self) -> bool:
        """按当前 RAG 后端判断课程资料问答是否可用。"""
        if settings.RAG_BACKEND == "local_pgvector":
            return bool(self.is_enabled and self.local_rag_ready)
        return self.cloud_rag_ready


class CourseAiBindingService:
    """从课程配置中解析 ChatProvider 与 CloudRagProvider 绑定。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _safe_bool(value: object, default: bool) -> bool:
        """按配置值解析布尔开关。"""
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _course(self, course_id: str) -> Course | None:
        clauses = [Course.slug == course_id]
        try:
            from uuid import UUID

            clauses.append(Course.id == UUID(str(course_id)))
        except (TypeError, ValueError):
            logger.debug("课程标识不是 UUID，按 slug 查询：course_id=%s", course_id)
        return self.db.execute(select(Course).where(or_(*clauses))).scalar_one_or_none()

    def get(self, course_id: str) -> CourseAiBinding | None:
        """返回课程 AI 绑定；课程不存在时返回 None。"""
        course = self._course(course_id)
        if not course:
            return None
        config = dict(course.model_config_json or {})
        chatdoc_binding = None
        active_rag_key = None
        local_readiness: dict[str, Any] = {}
        if settings.RAG_BACKEND == "local_pgvector":
            local_readiness = LocalKnowledgeService(self.db).readiness(course.slug)
        else:
            active_rag_key = config.get("cloud_rag_provider_id") or config.get("cloud_rag_provider")
            if not active_rag_key:
                try:
                    active_rag_key = ChatdocConfigService(self.db).active_template_key()
                except Exception:
                    logger.warning("读取默认 ChatDoc 配置失败，将按未绑定云端 RAG 处理：course_id=%s", course_id, exc_info=True)
                    active_rag_key = None
            chatdoc_binding = resolve_course_chatdoc_binding(
                self.db,
                course.slug,
                integration_key=str(active_rag_key) if active_rag_key else None,
            )
        return CourseAiBinding(
            course_id=course.slug,
            chat_provider_id=str(config.get("chat_provider")).strip() if config.get("chat_provider") else None,
            cloud_rag_provider_id=str(active_rag_key).strip() if active_rag_key else None,
            remote_knowledge_base_id=(
                str(config.get("remote_knowledge_base_id") or course.iflytek_repo_id).strip()
                if (config.get("remote_knowledge_base_id") or course.iflytek_repo_id)
                else None
            ),
            default_answer_mode=str(config.get("default_answer_mode") or "default_chat"),
            allow_rag_fallback_to_chat=self._safe_bool(config.get("allow_rag_fallback_to_chat"), False),
            require_citation_for_course_answer=self._safe_bool(config.get("require_citation_for_course_answer"), True),
            default_use_course_evidence_for_resource=self._safe_bool(
                config.get("default_use_course_evidence_for_resource"),
                True,
            ),
            is_enabled=self._safe_bool(config.get("ai_binding_enabled"), True),
            chatdoc=chatdoc_binding,
            local_rag_ready=bool(local_readiness.get("ready")),
            local_ready_document_count=int(local_readiness.get("document_count") or 0),
            local_ready_chunk_count=int(local_readiness.get("chunk_count") or 0),
        )

    def default_general(self) -> CourseAiBinding:
        """返回无课程场景的默认绑定。"""
        return CourseAiBinding(
            course_id="general",
            chat_provider_id=None,
            cloud_rag_provider_id=None,
            remote_knowledge_base_id=None,
            default_answer_mode="default_chat",
            allow_rag_fallback_to_chat=False,
            require_citation_for_course_answer=False,
            default_use_course_evidence_for_resource=False,
            is_enabled=True,
            chatdoc=None,
        )


class AiOrchestratorService:
    """用户侧统一 AI 编排入口。"""

    def __init__(self, workflow: AgentWorkflow | None = None) -> None:
        self.workflow = workflow or AgentWorkflow()
        self.intent_router = HybridIntentRouter()

    async def handle_message(self, payload: AiMessageRequest, db: Session, user_id: str) -> AiMessageResponse:
        """根据显式 mode/actionType 调度 Chat、课程资料问答或资源生成。"""
        route = await self.intent_router.classify_async(payload, db=db)
        self._record_intent_route_trace(db, payload, user_id, route)
        binding_service = CourseAiBindingService(db)
        binding = binding_service.get(payload.course_id) if payload.course_id else binding_service.default_general()
        if payload.course_id and binding is None:
            return self._unavailable_response(
                payload,
                route=self._response_route(route),
                code="course_not_found",
                message="课程不存在或无权访问，请重新选择课程。",
            )
        if route.needs_clarification and settings.INTENT_ROUTER_LOW_CONFIDENCE_CLARIFY:
            return self._handle_intent_clarification(payload, route)
        if route.intent in {"start_learning_session", "learning_plan_request"}:
            return await self._handle_learning_plan(payload, db, user_id, binding, route)
        if route.intent == "learning_progress_query":
            return await self._handle_learning_progress(payload, db, user_id)
        if route.intent == "course_rag_qa":
            return await self._handle_course_rag_qa(payload, db, user_id, binding)
        if route.intent == "resource_generation":
            return await self._handle_resource_generation(payload, db, user_id, binding)
        return await self._handle_default_chat(payload, db, user_id, binding)

    @staticmethod
    def _response_route(route: IntentRoute) -> str:
        """将内部意图名称映射为前端已有响应 route。"""
        if route.intent in {"start_learning_session", "learning_plan_request"}:
            return "learning_plan"
        if route.intent == "learning_progress_query":
            return "learning_progress"
        if route.intent in {"course_rag_qa", "resource_generation"}:
            return route.intent
        return "default_chat"

    @staticmethod
    def _handle_intent_clarification(payload: AiMessageRequest, route: IntentRoute) -> AiMessageResponse:
        """低置信度业务意图先追问，避免错误读取学情或误触发资源生成。"""
        intent_labels = {
            "start_learning_session": "开始今天的学习",
            "learning_plan_request": "制定学习计划",
            "learning_progress_query": "查看当前课程的个人学习进度",
            "course_rag_qa": "基于课程资料回答",
            "resource_generation": "生成学习资源",
        }
        candidate = intent_labels.get(route.fallback_intent or "", "继续普通问答")
        answer = route.clarification_prompt or f"我不太确定你的意图。你是想让我{candidate}，还是继续按普通学习问题回答？"
        return AiMessageResponse(
            conversation_id=payload.conversation_id or f"conv_{uuid4().hex[:12]}",
            answer=answer,
            citations=[],
            agent_trace=[
                AgentTraceEvent(
                    step="意图路由",
                    status="warning",
                    detail=f"低置信度 {route.confidence:.2f}，候选意图：{route.fallback_intent or 'unknown'}",
                )
            ],
            suggested_actions=[],
            quality=ChatQuality(cite_check="skipped", safety="passed"),
            resource_task_id=None,
            route="default_chat",
            availability=AiAvailability(ok=True, code="intent_clarification_required", message=answer),
        )

    async def _handle_learning_plan(
        self,
        payload: AiMessageRequest,
        db: Session,
        user_id: str,
        binding: CourseAiBinding,
        route: IntentRoute,
    ) -> AiMessageResponse:
        """处理开始学习和学习计划请求。"""
        gateway = ModelGateway(db)
        if not gateway.has_configured_chat_provider(binding.chat_provider_id):
            return self._unavailable_response(payload, route="learning_plan", code="chat_provider_unavailable", message=CHAT_PROVIDER_UNAVAILABLE_MESSAGE)
        response = await self.workflow.run_chat(payload.to_chat_request(), db, user_id)
        response.agent_trace.insert(0, AgentTraceEvent(step="意图识别", status="completed", detail=f"识别为 {route.intent}"))
        return self._with_route(response, route="learning_plan")

    async def _handle_learning_progress(
        self,
        payload: AiMessageRequest,
        db: Session,
        user_id: str,
    ) -> AiMessageResponse:
        """基于当前账号的课程掌握度和路径节点返回学习进度快照。"""
        if not payload.course_id:
            return self._unavailable_response(
                payload,
                route="learning_progress",
                code="course_required",
                message="请选择当前课程后，我才能读取该课程下你的真实学习进度。",
            )

        repository = LearningRepository(db)
        nodes = repository.get_path_nodes(payload.course_id, user_id)
        mastery = repository.get_mastery(payload.course_id, user_id)
        answer = self._format_learning_progress_answer(payload.course_id, db, mastery, nodes)
        return AiMessageResponse(
            conversation_id=payload.conversation_id or f"conv_{uuid4().hex[:12]}",
            answer=answer,
            citations=[],
            agent_trace=[
                AgentTraceEvent(step="意图识别", status="completed", detail="识别为学习进度查询"),
                AgentTraceEvent(
                    step="学习进度快照",
                    status="completed",
                    detail=f"读取 {len(mastery.get('dimensions') or {})} 个掌握度维度、{len(nodes)} 个路径节点",
                ),
                AgentTraceEvent(step="回答生成", status="completed", detail="基于数据库中的掌握度、学习路径和学习事件生成"),
            ],
            suggested_actions=[],
            quality=ChatQuality(cite_check="skipped", safety="passed"),
            resource_task_id=None,
            route="learning_progress",
            availability=AiAvailability(ok=True),
        )

    @staticmethod
    def _format_learning_progress_answer(
        course_id: str,
        db: Session,
        mastery: dict[str, Any],
        nodes: list[dict],
    ) -> str:
        """把学习进度数据格式化为稳定、可核验的回答。"""
        course_title = AiOrchestratorService._course_title(db, course_id)
        dimensions = mastery.get("dimensions") or {}
        overall = int(mastery.get("overall") or 0)
        overall_delta = mastery.get("overall_delta")
        mastered_nodes = [node for node in nodes if node.get("status") == "mastered" or int(node.get("mastery") or 0) >= 80]
        active_nodes = [
            node for node in nodes
            if node.get("status") in {"learning", "review", "needs_remedial"} and node not in mastered_nodes
        ]
        weak_dimensions = sorted(
            ((str(title), int(score or 0)) for title, score in dimensions.items()),
            key=lambda item: item[1],
        )[:3]
        next_nodes = [
            node for node in nodes
            if node.get("status") in {"learning", "needs_remedial", "review", "not_started"} and node not in mastered_nodes
        ][:3]

        if not dimensions and not nodes:
            return (
                f"当前课程「{course_title}」还没有可用的个人学习进度记录。\n\n"
                "我没有足够数据判断你真实学到了哪里。请先完成一次课程测评，或在学习路径中标记节点状态；之后我会基于 "
                "concept_mastery、learning_path/path_nodes 和学习事件返回进度快照。"
            )

        delta_text = ""
        if isinstance(overall_delta, int) and overall_delta != 0:
            delta_text = f"（近 24 小时 {'+' if overall_delta > 0 else ''}{overall_delta}%）"
        lines = [
            f"这是基于当前账号在「{course_title}」中的真实学习进度快照：",
            "",
            f"- 总体掌握度：{overall}%{delta_text}",
            f"- 路径完成：{len(mastered_nodes)}/{len(nodes)} 个节点已掌握" if nodes else "- 路径完成：暂无路径节点记录",
        ]
        if mastered_nodes:
            mastered_text = "、".join(f"{node.get('title')} {int(node.get('mastery') or 0)}%" for node in mastered_nodes[:4])
            lines.append(f"- 已掌握内容：{mastered_text}")
        if active_nodes:
            active_text = "、".join(f"{node.get('title')} {int(node.get('mastery') or 0)}%" for node in active_nodes[:4])
            lines.append(f"- 正在学习/复习：{active_text}")
        if weak_dimensions:
            weak_text = "、".join(f"{title} {score}%" for title, score in weak_dimensions)
            lines.append(f"- 需要优先补强：{weak_text}")
        if next_nodes:
            next_text = " -> ".join(str(node.get("title") or node.get("concept_name") or node.get("id")) for node in next_nodes)
            lines.extend(["", f"下一步建议：先处理 {next_text}。"])

        lines.extend(["", "数据来源：当前用户的概念掌握度、学习路径节点、测评结果和路径状态更新事件。"])
        return "\n".join(lines)

    @staticmethod
    def _course_title(db: Session, course_id: str) -> str:
        """按 slug 或 UUID 获取课程名称。"""
        clauses = [Course.slug == course_id]
        try:
            from uuid import UUID

            clauses.append(Course.id == UUID(str(course_id)))
        except (TypeError, ValueError):
            logger.debug("课程标识不是 UUID，按 slug 查询课程标题：course_id=%s", course_id)
        course = db.execute(select(Course).where(or_(*clauses))).scalar_one_or_none()
        return course.title if course else course_id

    async def _handle_default_chat(
        self,
        payload: AiMessageRequest,
        db: Session,
        user_id: str,
        binding: CourseAiBinding,
    ) -> AiMessageResponse:
        """处理普通学习对话。"""
        gateway = ModelGateway(db)
        if not gateway.has_configured_chat_provider(binding.chat_provider_id):
            return self._unavailable_response(payload, route="default_chat", code="chat_provider_unavailable", message=CHAT_PROVIDER_UNAVAILABLE_MESSAGE)
        response = await self.workflow.run_chat(payload.to_chat_request(), db, user_id)
        return self._with_route(response, route="default_chat")

    async def _handle_resource_generation(
        self,
        payload: AiMessageRequest,
        db: Session,
        user_id: str,
        binding: CourseAiBinding,
    ) -> AiMessageResponse:
        """处理资源生成编排。"""
        gateway = ModelGateway(db)
        if not gateway.has_configured_chat_provider(binding.chat_provider_id):
            return self._unavailable_response(payload, route="resource_generation", code="chat_provider_unavailable", message=CHAT_PROVIDER_UNAVAILABLE_MESSAGE)

        need_evidence = bool(
            payload.course_id
            and (
                payload.need_course_evidence
                if payload.need_course_evidence is not None
                else binding.default_use_course_evidence_for_resource
            )
        )
        if need_evidence and not binding.rag_ready:
            message = (
                "当前课程还没有完成本地资料向量化，暂时无法基于课程内容生成。"
                if settings.RAG_BACKEND == "local_pgvector"
                else COURSE_EVIDENCE_UNAVAILABLE_MESSAGE
            )
            return self._unavailable_response(
                payload,
                route="resource_generation",
                code="course_evidence_unavailable",
                message=message,
                fallback_action="continue_without_course_evidence",
            )

        resource_type = payload.resource_type or payload.preferred_resource_type or "lecture"
        task_payload = ResourceGenerateRequest(
            scope="course" if payload.course_id else "general",
            course_id=payload.course_id,
            concept_id=payload.concept_id,
            path_node_id=payload.path_node_id,
            resource_type=resource_type,
            difficulty=str(payload.client_context.get("difficulty") or "medium"),
            goal=payload.message[:500],
            requirements=str(payload.client_context.get("requirements") or ""),
            topic=payload.message[:120] if not payload.course_id else None,
            need_course_evidence=need_evidence,
            action_type="resource_generation",
            client_context=payload.client_context,
        )
        task = ResourceRepository(db).create_generation_task(task_payload, user_id)
        resource_task_id = task.get("task_id")
        label = str(payload.client_context.get("label") or resource_type)
        if not resource_task_id:
            failure_code = str(task.get("error_code") or "resource_task_failed")
            failure_message = str(task.get("error_message") or task.get("message") or "资源生成任务创建失败，请稍后重试。")
            logger.warning(
                "资源生成任务创建失败：course_id=%s resource_type=%s user_id=%s trace_id=%s error_code=%s error_message=%s",
                payload.course_id,
                resource_type,
                user_id,
                get_trace_id(),
                failure_code,
                failure_message,
            )
            self._record_resource_agent_trace(
                db,
                payload,
                user_id,
                status="failed",
                resource_task_id=None,
                error_message=failure_message,
            )
            return AiMessageResponse(
                conversation_id=payload.conversation_id or f"conv_{uuid4().hex[:12]}",
                answer=failure_message,
                citations=[],
                agent_trace=[AgentTraceEvent(step="资源编排", status="failed", detail=failure_message)],
                suggested_actions=[],
                quality=ChatQuality(cite_check="skipped", safety="passed"),
                resource_task_id=None,
                route="resource_generation",
                availability=AiAvailability(ok=False, code=failure_code, message=failure_message),
            )

        enqueue_ok = enqueue_resource_generation(resource_task_id)
        if not enqueue_ok:
            failure_message = "资源生成任务已创建，但任务队列暂时不可用，请稍后重试。"
            logger.warning(
                "资源生成任务入队失败：task_id=%s course_id=%s resource_type=%s user_id=%s trace_id=%s",
                resource_task_id,
                payload.course_id,
                resource_type,
                user_id,
                get_trace_id(),
            )
            self._record_resource_agent_trace(
                db,
                payload,
                user_id,
                status="failed",
                resource_task_id=resource_task_id,
                error_message=failure_message,
            )
            return AiMessageResponse(
                conversation_id=payload.conversation_id or f"conv_{uuid4().hex[:12]}",
                answer=failure_message,
                citations=[],
                agent_trace=[AgentTraceEvent(step="资源编排", status="failed", detail=failure_message)],
                suggested_actions=[],
                quality=ChatQuality(cite_check="skipped", safety="passed"),
                resource_task_id=resource_task_id,
                route="resource_generation",
                availability=AiAvailability(ok=False, code="resource_enqueue_failed", message=failure_message),
            )

        self._record_resource_agent_trace(db, payload, user_id, status="success", resource_task_id=resource_task_id)
        return AiMessageResponse(
            conversation_id=payload.conversation_id or f"conv_{uuid4().hex[:12]}",
            answer=f"已创建「{label}」资源生成任务，请在资源工坊预览进度。",
            citations=[],
            agent_trace=[AgentTraceEvent(step="资源编排", status="completed", detail=resource_task_id)],
            suggested_actions=[],
            quality=ChatQuality(cite_check="skipped", safety="passed"),
            resource_task_id=resource_task_id,
            route="resource_generation",
            availability=AiAvailability(ok=True),
        )

    async def _handle_course_rag_qa(
        self,
        payload: AiMessageRequest,
        db: Session,
        user_id: str,
        binding: CourseAiBinding,
    ) -> AiMessageResponse:
        """处理显式课程资料问答。"""
        if not payload.course_id:
            return self._unavailable_response(payload, route="course_rag_qa", code="course_required", message="请选择课程后使用课程资料问答")
        if not binding.rag_ready:
            message = (
                "当前课程还没有完成本地资料向量化，暂时不能使用课程资料问答。"
                if settings.RAG_BACKEND == "local_pgvector"
                else (binding.chatdoc.blocking_reason if binding.chatdoc else None)
            )
            return self._unavailable_response(
                payload,
                route="course_rag_qa",
                code="knowledge_not_ready",
                message=message or "当前课程资料还没有完成云端向量化，暂时不能使用课程资料问答。你可以切换为普通 AI 问答。",
                fallback_action="switch_to_default_chat",
        )

        started_at = time.perf_counter()
        if settings.RAG_BACKEND == "local_pgvector":
            try:
                response = await self.workflow.run_chat(payload.to_chat_request(), db, user_id)
            except Exception as exc:
                error_message = str(exc) or "本地课程资料问答失败"
                logger.warning(
                    "本地课程资料问答生成失败：course_id=%s conversation_id=%s trace_id=%s exc_type=%s",
                    payload.course_id,
                    payload.conversation_id,
                    get_trace_id(),
                    type(exc).__name__,
                    exc_info=True,
                )
                return self._unavailable_response(payload, route="course_rag_qa", code="local_rag_error", message=error_message)
            trace = list(response.agent_trace or [])
            trace.insert(0, AgentTraceEvent(step="本地课程检索", status="completed", detail=f"命中 {len(response.citations)} 条本地引用"))
            return AiMessageResponse.model_validate(
                {
                    **response.model_dump(),
                    "route": "course_rag_qa",
                    "agent_trace": trace,
                    "availability": AiAvailability(ok=bool(response.answer and response.citations)),
                }
            )

        try:
            citations = await CourseRetriever().retrieve(
                db,
                binding.course_id,
                payload.message,
                payload.concept_id,
                document_id=payload.uploaded_doc_id,
            )
        except Exception as exc:
            error_message = str(exc) or "课程资料检索失败"
            logger.warning(
                "课程资料问答检索失败：course_id=%s concept_id=%s uploaded_doc_id=%s conversation_id=%s trace_id=%s exc_type=%s",
                payload.course_id,
                payload.concept_id,
                payload.uploaded_doc_id,
                payload.conversation_id,
                get_trace_id(),
                type(exc).__name__,
                exc_info=True,
            )
            self._record_doc_qa_trace(
                db,
                payload,
                user_id,
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                status="failed",
                error_message=error_message,
                citation_count=0,
            )
            return self._unavailable_response(payload, route="course_rag_qa", code="cloud_rag_error", message=error_message)
        if binding.require_citation_for_course_answer and not citations:
            self._record_doc_qa_trace(
                db,
                payload,
                user_id,
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                status="failed",
                error_message="no course evidence hit",
                citation_count=0,
            )
            return AiMessageResponse(
                conversation_id=payload.conversation_id or f"conv_{uuid4().hex[:12]}",
                answer=COURSE_RAG_NO_HIT_MESSAGE,
                citations=[],
                agent_trace=[
                    AgentTraceEvent(step="课程资料依据", status="warning", detail="未命中可靠课程依据"),
                    AgentTraceEvent(step="回答生成", status="skipped", detail="课程资料问答要求引用，未调用普通 Chat 回退"),
                ],
                suggested_actions=[],
                quality=ChatQuality(cite_check="missing", safety="passed", citation_coverage="missing_course_evidence"),
                resource_task_id=None,
                route="course_rag_qa",
                availability=AiAvailability(ok=False, code="course_evidence_not_found", message=COURSE_RAG_NO_HIT_MESSAGE, fallback_action="switch_to_default_chat"),
            )

        done_payload: dict[str, Any] | None = None
        error_message: str | None = None
        try:
            async for event in self.workflow.stream_chatdoc_qa(payload.to_chat_request(), db, user_id):
                if event.get("type") == "done":
                    done_payload = event
                elif event.get("type") == "error":
                    error_message = str(event.get("message") or event.get("code") or "课程资料问答失败")
        except Exception as exc:
            error_message = str(exc) or "课程资料问答失败"
            logger.warning(
                "课程资料问答流式生成失败：course_id=%s concept_id=%s uploaded_doc_id=%s conversation_id=%s trace_id=%s exc_type=%s",
                payload.course_id,
                payload.concept_id,
                payload.uploaded_doc_id,
                payload.conversation_id,
                get_trace_id(),
                type(exc).__name__,
                exc_info=True,
            )
            self._record_doc_qa_trace(
                db,
                payload,
                user_id,
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                status="failed",
                error_message=error_message,
                citation_count=len(citations),
            )
            return self._unavailable_response(payload, route="course_rag_qa", code="cloud_rag_error", message=error_message)
        if error_message and not done_payload:
            self._record_doc_qa_trace(
                db,
                payload,
                user_id,
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                status="failed",
                error_message=error_message,
                citation_count=len(citations),
            )
            return self._unavailable_response(payload, route="course_rag_qa", code="cloud_rag_error", message=error_message)

        answer = str((done_payload or {}).get("answer") or COURSE_RAG_NO_HIT_MESSAGE)
        trace = list((done_payload or {}).get("agent_trace") or [])
        trace.insert(0, AgentTraceEvent(step="课程资料依据", status="completed", detail=f"命中 {len(citations)} 条引用"))
        self._record_doc_qa_trace(
            db,
            payload,
            user_id,
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            status="success",
            error_message=None,
            citation_count=len(citations),
        )
        return AiMessageResponse(
            conversation_id=str((done_payload or {}).get("conversation_id") or payload.conversation_id or f"conv_{uuid4().hex[:12]}"),
            answer=answer,
            citations=citations,
            agent_trace=trace,
            suggested_actions=[],
            quality=ChatQuality(cite_check="passed" if citations else "missing", safety="passed"),
            resource_task_id=None,
            route="course_rag_qa",
            availability=AiAvailability(ok=True),
        )

    def _with_route(self, response: Any, *, route: str) -> AiMessageResponse:
        """将旧 ChatResponse 包装为统一响应。"""
        return AiMessageResponse(
            conversation_id=response.conversation_id,
            answer=response.answer,
            citations=response.citations,
            agent_trace=response.agent_trace,
            suggested_actions=response.suggested_actions,
            quality=response.quality,
            resource_task_id=response.resource_task_id,
            route=route,
            availability=AiAvailability(ok=True),
        )

    def _unavailable_response(
        self,
        payload: AiMessageRequest,
        *,
        route: str,
        code: str,
        message: str,
        fallback_action: str | None = None,
    ) -> AiMessageResponse:
        """生成用户侧不可用响应。"""
        return AiMessageResponse(
            conversation_id=payload.conversation_id or f"conv_{uuid4().hex[:12]}",
            answer=message,
            citations=[],
            agent_trace=[AgentTraceEvent(step="可用性检查", status="blocked", detail=message)],
            suggested_actions=[],
            quality=ChatQuality(cite_check="skipped", safety="passed"),
            resource_task_id=None,
            route=route,
            availability=AiAvailability(ok=False, code=code, message=message, fallback_action=fallback_action),
        )

    def _record_doc_qa_trace(
        self,
        db: Session,
        payload: AiMessageRequest,
        user_external_id: str,
        *,
        latency_ms: int,
        status: str,
        error_message: str | None,
        citation_count: int,
    ) -> None:
        """记录课程资料问答编排层日志。"""
        self._record_model_call_log(
            db,
            payload,
            user_external_id,
            agent_name="课程资料问答编排",
            capability="doc_qa",
            model_name="iflytek-chatdoc",
            status=status,
            latency_ms=latency_ms,
            error_message=error_message,
            meta_json={"request_type": "course_rag_qa", "provider_type": "cloud_rag", "citation_count": citation_count},
        )

    def _record_resource_agent_trace(
        self,
        db: Session,
        payload: AiMessageRequest,
        user_external_id: str,
        *,
        status: str,
        resource_task_id: str | None,
        error_message: str | None = None,
    ) -> None:
        """记录资源编排层日志。"""
        self._record_model_call_log(
            db,
            payload,
            user_external_id,
            agent_name="资源编排",
            capability="resource_agent",
            model_name="resource-agent",
            status=status,
            latency_ms=0,
            error_message=error_message,
            meta_json={"request_type": "resource_generation", "provider_type": "resource_agent", "resource_task_id": resource_task_id},
        )

    def _record_intent_route_trace(
        self,
        db: Session,
        payload: AiMessageRequest,
        user_external_id: str,
        route: IntentRoute,
    ) -> None:
        """记录意图路由决策，用于后续评测、反馈和灰度分析。"""
        self._record_model_call_log(
            db,
            payload,
            user_external_id,
            agent_name="HybridIntentRouter",
            capability="intent_route",
            model_name=route.source,
            status="clarify" if route.needs_clarification else "success",
            latency_ms=route.latency_ms,
            error_message=None,
            meta_json={
                "request_type": "intent_routing",
                "conversation_id": payload.conversation_id,
                "message": payload.message[:500],
                "intent": route.intent,
                "confidence": route.confidence,
                "reason": route.reason,
                "source": route.source,
                "needs_clarification": route.needs_clarification,
                "fallback_intent": route.fallback_intent,
                "candidates": [
                    {
                        "intent": candidate.intent,
                        "score": candidate.score,
                        "source": candidate.source,
                        "reason": candidate.reason,
                    }
                    for candidate in route.candidates[:3]
                ],
            },
        )

    def _record_model_call_log(
        self,
        db: Session,
        payload: AiMessageRequest,
        user_external_id: str,
        *,
        agent_name: str,
        capability: str,
        model_name: str,
        status: str,
        latency_ms: int,
        error_message: str | None,
        meta_json: dict[str, Any],
    ) -> None:
        """写入统一 trace 可查询日志。"""
        try:
            course = None
            if payload.course_id:
                clauses = [Course.slug == payload.course_id]
                try:
                    from uuid import UUID

                    clauses.append(Course.id == UUID(str(payload.course_id)))
                except (TypeError, ValueError):
                    logger.debug("课程标识不是 UUID，模型调用日志按 slug 关联：course_id=%s", payload.course_id)
                course = db.execute(select(Course).where(or_(*clauses))).scalar_one_or_none()
            user = db.execute(select(User).where(User.external_id == user_external_id)).scalar_one_or_none()
            db.add(
                ModelCallLog(
                    course_id=course.id if course else None,
                    user_id=user.id if user else None,
                    provider_id=None,
                    agent_name=agent_name,
                    capability=capability,
                    model_name=model_name,
                    request_count=1,
                    latency_ms=max(0, latency_ms),
                    status=status,
                    error_message=error_message,
                    meta_json={
                        "trace_id": get_trace_id(),
                        "course_slug": payload.course_id,
                        "mode": payload.mode,
                        "actionType": payload.action_type,
                        **meta_json,
                    },
                )
            )
            db.commit()
        except Exception as exc:
            logger.warning(
                "写入模型调用日志失败：trace_id=%s user=%s course_id=%s conversation_id=%s agent=%s capability=%s model=%s mode=%s status=%s exc_type=%s",
                get_trace_id(),
                user_external_id,
                payload.course_id,
                payload.conversation_id,
                agent_name,
                capability,
                model_name,
                payload.mode,
                status,
                type(exc).__name__,
                exc_info=True,
            )
            try:
                db.rollback()
            except Exception:
                logger.debug(
                    "模型调用日志失败后回滚数据库会话失败：trace_id=%s user=%s course_id=%s conversation_id=%s",
                    get_trace_id(),
                    user_external_id,
                    payload.course_id,
                    payload.conversation_id,
                    exc_info=True,
                )
