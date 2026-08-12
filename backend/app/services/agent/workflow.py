from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any, TypedDict
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tracing import get_trace_id
from app.schemas.ai import (
    AgentTraceEvent,
    ChatQuality,
    ChatRequest,
    ChatResponse,
    SuggestedAction,
    WorkflowStateSnapshot,
    WorkflowStateUpdate,
)
from app.schemas.common import Citation
from app.schemas.resource import ResourceGenerateRequest
from app.services.agent.cite_verifier import CiteVerifier
from app.services.agent.retrieval_guard import should_refuse_low_confidence
from app.services.resource.queue import enqueue_resource_generation
from app.services.resource.repository import ResourceRepository
from app.models import Course, CourseConcept, CourseProfile, User
from app.models.model_gateway import ModelCallLog
from app.services.conversation.repository import ConversationRepository
from app.services.course.context import CourseContext, CourseContextService
from app.services.learning.events import LearningEventRecorder
from app.services.learning.repository import LearningRepository
from app.services.profile.repository import LearningProfileRepository, ProfileContext
from app.services.profile.extractor import DIMENSION_NAMES, ExtractedDimension, ProfileExtractor
from app.services.model_gateway.router import ModelGateway
from app.services.knowledge.extracted_qa_repository import ExtractedQaRepository
from app.services.knowledge.iflytek.client_factory import chatdoc_client_for_db
from app.services.knowledge.iflytek.config_service import ChatdocConfigService
from app.services.knowledge.iflytek.course_chat_binding import resolve_course_chatdoc_binding
from app.services.knowledge.iflytek.doc_qa_stream import stream_chatdoc_doc_qa
from app.services.knowledge.iflytek.vendor_quota import ChatdocVendorQuotaService
from app.services.safety.guardrail import SafetyGuardrail
from app.services.rag.retriever import CourseRetriever
from app.services.shared.citation_context import build_llm_context
from app.services.onboarding.service import OnboardingService
from app.schemas.onboarding import ChipOption, OnboardingHistoryMessage

logger = logging.getLogger(__name__)

try:  # LangGraph 是运行时依赖；保留兜底可以让本地测试更容易运行。
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover - 仅在受限环境无法导入可选依赖时使用。
    logger.debug("LangGraph 可选依赖不可用，将使用顺序执行兜底：trace_id=%s", get_trace_id(), exc_info=True)
    END = "__end__"
    StateGraph = None  # type: ignore[assignment]


def is_general_learning(payload: ChatRequest) -> bool:
    """判断当前请求是否属于不绑定课程的通用学习场景。"""
    return payload.learning_scope == "general" or not payload.course_id


def _parse_onboarding_structured_answer(
    raw: str,
) -> tuple[str, list[dict[str, Any]], list[ChipOption]]:
    """解析引导模式 LLM 的结构化 JSON 返回。

    约定 LLM 返回包含 user_visible / dimensions / chips 三个字段的 JSON 对象。
    后端解析后：
    - user_visible 作为分块打字机文本下发给前端；
    - dimensions 由 workflow 直写全局画像（跳过 extractor）；
    - chips 在第 2 轮起注入 onboarding_service._llm_chips。

    降级策略：解析失败时 user_visible 退回 raw 原文，dimensions 与 chips 均返回空，
    由 _node_profile 走 extractor 兜底抽取画像。

    返回：(user_visible, dimensions, chips)。
    """

    # LLM 可能在 JSON 前后多余文本，取第一个 { 到最后一个 } 作为候选 JSON 片段
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return raw.strip(), [], []
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        # 非 JSON：退回原文给前端展示，画像交给 extractor 兜底
        return raw.strip(), [], []
    if not isinstance(data, dict):
        return raw.strip(), [], []
    user_visible = str(data.get("user_visible", "")).strip() or raw.strip()
    dims_raw = data.get("dimensions") or []
    dimensions: list[dict[str, Any]] = []
    if isinstance(dims_raw, list):
        for dim in dims_raw:
            if not isinstance(dim, dict):
                continue
            key = dim.get("key")
            if not key:
                continue
            try:
                confidence = float(dim.get("confidence", 0.8))
            except (TypeError, ValueError):
                confidence = 0.8
            dimensions.append(
                {
                    "key": str(key),
                    "label": str(dim.get("label", "") or "待观察"),
                    "confidence": confidence,
                }
            )
    chips_raw = data.get("chips") or []
    chips: list[ChipOption] = []
    if isinstance(chips_raw, list):
        for chip in chips_raw:
            if not isinstance(chip, dict):
                continue
            # 仅当必填字段齐全才采纳，避免前端渲染异常
            if not all(k in chip for k in ("id", "label", "payload")):
                continue
            chips.append(
                ChipOption(
                    id=str(chip["id"]),
                    label=str(chip["label"]),
                    icon=chip.get("icon"),
                    payload=str(chip["payload"]),
                    category=chip.get("category", "knowledge_base"),
                )
            )
    return user_visible, dimensions, chips


RESOURCE_TYPE_LABELS = {
    "lecture": "高白话讲义",
    "quiz": "阶段测评题",
    "code_lab": "PyTorch 实操案例",
    "reading": "拓展阅读包",
    "ppt": "PPT 大纲",
    "mindmap": "思维导图",
    "video": "视频脚本",
}


class AgentWorkflowState(TypedDict, total=False):
    """智能体节点之间传递的共享状态载荷。"""

    db: Session
    payload: ChatRequest
    user_id: str
    context: CourseContext
    conversation_id: str
    intent: str
    route_decision: str
    citations: list[Citation]
    safe: bool
    answer: str
    model_meta: dict[str, Any]
    trace: list[AgentTraceEvent]
    quality: dict[str, Any]
    suggested_actions: list[SuggestedAction]
    resource_task_id: str | None
    retrieval_refusal_reason: str | None
    profile_context: ProfileContext
    onboarding_mode: bool
    onboarding_meta: dict[str, Any]


class AgentWorkflow:
    """感知课程上下文的智能体工作流。

    REST 入口调用 ``run_chat`` 生成一次性响应；WebSocket 入口调用 ``stream_chat``
    输出 UI 事件。答案生成节点优先经过模型网关，演示环境未配置供应商 API Key 时
    回退到确定性的本地答案。
    """

    def __init__(self) -> None:
        self.context_service = CourseContextService()
        self.retriever = CourseRetriever()
        self.safety = SafetyGuardrail()
        self.cite_verifier = CiteVerifier()
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        """构建 LangGraph 工作流；依赖不可用时返回空图并交给顺序兜底执行。

        采用「公共前缀 + 按意图分支」的图结构：
        - 公共前缀：load_context → route → safety，所有请求都先完成上下文加载、意图路由与安全审查。
        - 意图分支：safety 之后按 route_decision 分流到不同 Agent 执行链。
          - course_rag_qa / learning_plan / learning_progress / assessment_feedback：走完整检索链
          - default_chat：普通课程聊天，跳过强制检索（检索节点内部已按路由跳过）
          - general_chat：通用聊天，只走生成，不校验引用、不更新画像与学习路径
        - generate 之后再次按分支决定是否继续引用检查（general_chat 直接结束）。
        """
        if StateGraph is None:
            return None
        graph = StateGraph(AgentWorkflowState)
        graph.add_node("load_context", self._node_context)
        graph.add_node("route", self._node_route)
        graph.add_node("safety", self._node_safety)
        graph.add_node("retrieve", self._node_retrieve)
        graph.add_node("generate", self._node_generate)
        graph.add_node("cite_check", self._node_cite_check)
        graph.add_node("profile", self._node_profile)
        graph.add_node("path", self._node_path)
        graph.add_node("orchestrate", self._node_orchestrate)
        graph.set_entry_point("load_context")
        graph.add_edge("load_context", "route")
        graph.add_edge("route", "safety")
        # 第一条条件边：按意图分流是否执行课程检索
        graph.add_conditional_edges(
            "safety",
            self._route_to_next_after_safety,
            {
                "retrieve": "retrieve",
                "generate": "generate",
            },
        )
        graph.add_edge("retrieve", "generate")
        # 第二条条件边：general_chat 结束，其余意图继续引用检查与画像/路径沉淀
        graph.add_conditional_edges(
            "generate",
            self._route_to_next_after_generate,
            {
                "cite_check": "cite_check",
                "end": END,
            },
        )
        graph.add_edge("cite_check", "profile")
        graph.add_edge("profile", "path")
        graph.add_edge("path", "orchestrate")
        graph.add_edge("orchestrate", END)
        return graph.compile()

    @staticmethod
    def _route_to_next_after_safety(state: AgentWorkflowState) -> str:
        """安全审查后按意图决定是否进入课程检索节点。

        普通聊天（default_chat）与通用聊天（general_chat）不强制课程资料检索，
        直接进入生成；其余意图（课程问答、学习计划、学习进度、评估反馈）需要检索依据。
        """
        decision = state.get("route_decision", "default_chat")
        if decision in {"default_chat", "general_chat"}:
            return "generate"
        return "retrieve"

    @staticmethod
    def _route_to_next_after_generate(state: AgentWorkflowState) -> str:
        """回答生成后决定是否继续引用检查与画像/路径沉淀。

        general_chat 为不绑定课程的通用闲聊，无需引用校验与课程画像更新，直接结束。
        """
        if state.get("route_decision") == "general_chat":
            return "end"
        return "cite_check"

    @staticmethod
    def _append_trace(
        state: AgentWorkflowState,
        step: str,
        status: str,
        detail: str | None = None,
        *,
        duration_ms: int | None = None,
    ) -> list[AgentTraceEvent]:
        return [*(state.get("trace") or []), AgentTraceEvent(step=step, status=status, detail=detail, duration_ms=duration_ms)]

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return max(0, int((time.perf_counter() - started_at) * 1000))

    def _node_context(self, state: AgentWorkflowState) -> AgentWorkflowState:
        started_at = time.perf_counter()
        payload = state["payload"]
        conversation_repo = ConversationRepository(state["db"])
        if is_general_learning(payload):
            conversation = conversation_repo.get_or_create_general_conversation(
                user_external_id=state["user_id"],
                conversation_id=payload.conversation_id,
                title=payload.message[:120] if payload.message else None,
            )
            trace_step = "通用学习上下文"
            trace_detail = "通用学习 · 不使用课程知识库"
        else:
            conversation = conversation_repo.get_or_create_conversation(
                course_slug=payload.course_id or "",
                user_external_id=state["user_id"],
                conversation_id=payload.conversation_id,
                title=payload.message[:120] if payload.message else None,
            )
            trace_step = "课程上下文"
            trace_detail = None
        context = self.context_service.build(
            db=state["db"],
            course_id=payload.course_id,
            concept_id=payload.concept_id,
            path_node_id=payload.path_node_id,
            conversation_id=str(conversation.id),
        )
        try:
            profile_context = LearningProfileRepository(state["db"]).resolve_context(
                user_external_id=state["user_id"],
                course_id=None if is_general_learning(payload) else payload.course_id,
                conversation_id=str(conversation.id),
                message=payload.message,
                task_type=payload.intent_type,
            )
        except Exception:
            logger.warning(
                "解析学习画像上下文失败，将使用空画像继续对话：conversation_id=%s course_id=%s user_id=%s trace_id=%s",
                conversation.id,
                payload.course_id,
                state["user_id"],
                get_trace_id(),
                exc_info=True,
            )
            profile_context = ProfileContext(
                scope="general" if is_general_learning(payload) else "course",
                course_id=None if is_general_learning(payload) else payload.course_id,
                summary="",
                global_summary="",
            )
        return {
            "context": context,
            "conversation_id": str(conversation.id),
            "profile_context": profile_context,
            "trace": self._append_trace(
                state,
                trace_step,
                "completed",
                trace_detail or context.course_title,
                duration_ms=self._elapsed_ms(started_at),
            ),
        }

    async def _node_route(self, state: AgentWorkflowState) -> AgentWorkflowState:
        """增强意图路由：优先使用显式 intent_type，对未明确指定的场景使用 HybridIntentRouter 细粒度分类。

        支持更细粒度的路由决策：
        - resource_request: 资源生成请求
        - course_rag_qa: 课程资料问答
        - default_chat: 默认学习对话
        - learning_plan: 学习计划/开始学习
        - learning_progress: 学习进度查询
        - assessment_feedback: 评估反馈
        - general_chat: 通用闲聊（不绑定课程）
        """
        started_at = time.perf_counter()
        payload = state["payload"]
        route_decision: str

        # 第 1 层：显式 intent_type 覆盖（从前端或编排层传入）
        if payload.intent_type == "RESOURCE_GENERATION":
            route_decision = "resource_request"
        elif payload.intent_type in {"COURSE_RAG_QA", "KNOWLEDGE_QA"}:
            route_decision = "course_rag_qa"
        elif payload.intent_type == "GENERAL_CHAT":
            route_decision = "general_chat"
        elif payload.intent_type == "DEFAULT_CHAT" and not is_general_learning(payload):
            # 第 2 层：课程场景下使用 HybridIntentRouter 细粒度分类
            try:
                from app.schemas.ai import AiMessageRequest
                from app.services.ai.intent_router import HybridIntentRouter

                router = HybridIntentRouter()
                ai_request = AiMessageRequest(
                    user_id=state["user_id"],
                    course_id=payload.course_id,
                    conversation_id=payload.conversation_id,
                    message=payload.message,
                    mode="default_chat",
                    learning_scope=payload.learning_scope,
                )
                intent_route = await router.classify_async(ai_request, db=state["db"])
                intent_map: dict[str, str] = {
                    "start_learning_session": "learning_plan",
                    "learning_plan_request": "learning_plan",
                    "learning_progress_query": "learning_progress",
                    "course_rag_qa": "course_rag_qa",
                    "resource_generation": "resource_request",
                    "default_chat": "default_chat",
                    "general_chat": "general_chat",
                }
                route_decision = intent_map.get(intent_route.intent, "default_chat")
                detail = f"{intent_route.intent} ({intent_route.confidence:.2f}) via {intent_route.source}"
            except Exception as exc:
                logger.warning(
                    "HybridIntentRouter 分类失败，退回规则路由：trace_id=%s exc_type=%s",
                    get_trace_id(),
                    type(exc).__name__,
                    exc_info=True,
                )
                route_decision = self._resolve_route_decision(payload.message)
                detail = route_decision
        else:
            # 第 3 层：通用学习或无明确意图时使用规则路由
            route_decision = self._resolve_route_decision(payload.message)
            detail = route_decision

        return {
            "route_decision": route_decision,
            "intent": route_decision,
            "trace": self._append_trace(state, "意图路由", "completed", detail, duration_ms=self._elapsed_ms(started_at)),
        }

    @staticmethod
    def _resolve_route_decision(message: str) -> str:
        lowered = (message or "").lower()
        resource_keywords = ["生成", "讲义", "题库", "题单", "ppt", "实验", "实操", "资源", "思维导图", "阅读包", "出题"]
        assessment_keywords = ["评分", "我答", "自测", "解释得对吗", "批改", "答对了吗"]
        if any(keyword in lowered for keyword in resource_keywords):
            return "resource_request"
        if any(keyword in lowered for keyword in assessment_keywords):
            return "assessment_feedback"
        return "default_chat"

    @staticmethod
    def _infer_resource_type(message: str, preferred: str | None = None) -> str:
        if preferred:
            return preferred
        lowered = (message or "").lower()
        if any(keyword in lowered for keyword in ["题库", "题单", "出题", "测评", "练习"]):
            return "quiz"
        if any(keyword in lowered for keyword in ["实验", "代码", "pytorch", "实操"]):
            return "code_lab"
        if any(keyword in lowered for keyword in ["ppt", "幻灯"]):
            return "ppt"
        if any(keyword in lowered for keyword in ["思维导图", "导图"]):
            return "mindmap"
        if any(keyword in lowered for keyword in ["阅读", "文献"]):
            return "reading"
        return "lecture"

    def _build_suggested_actions(self, state: AgentWorkflowState) -> list[SuggestedAction]:
        if state.get("route_decision") != "resource_request":
            return []
        payload = state["payload"]
        resource_type = self._infer_resource_type(payload.message, payload.preferred_resource_type)
        label = RESOURCE_TYPE_LABELS.get(resource_type, resource_type)
        return [
            SuggestedAction(
                action="generate_resource",
                resource_type=resource_type,
                label=f"生成{label}",
                reason="检测到资源生成意图，确认后可创建资源任务",
            )
        ]

    def _apply_output_safety(self, answer: str) -> tuple[str, dict[str, Any]]:
        safety = self.safety.check_output(answer)
        if safety["status"] == "blocked":
            return self.safety.sanitize_output(answer), {"safety": "blocked", **safety}
        if safety["status"] == "warning":
            return self.safety.sanitize_output(answer), {"safety": "warning", **safety}
        return answer, {"safety": "passed", **safety}

    def _node_safety(self, state: AgentWorkflowState) -> AgentWorkflowState:
        started_at = time.perf_counter()
        payload = state["payload"]
        safe = self.safety.check_user_input(payload.message)
        return {
            "safe": safe,
            "trace": self._append_trace(
                state,
                "安全审查",
                "completed" if safe else "blocked",
                duration_ms=self._elapsed_ms(started_at),
            ),
        }

    async def _node_retrieve(self, state: AgentWorkflowState) -> AgentWorkflowState:
        started_at = time.perf_counter()
        if is_general_learning(state["payload"]):
            return {
                "citations": [],
                "trace": self._append_trace(
                    state,
                    "课程检索",
                    "skipped",
                    "通用学习模式，不使用课程知识库",
                    duration_ms=self._elapsed_ms(started_at),
                ),
            }
        if state.get("route_decision") == "default_chat":
            return {
                "citations": [],
                "trace": self._append_trace(
                    state,
                    "课程检索",
                    "skipped",
                    "普通 Chat 不强制课程资料检索",
                    duration_ms=self._elapsed_ms(started_at),
                ),
            }
        if not state.get("safe", True):
            return {
                "citations": [],
                "trace": self._append_trace(
                    state,
                    "课程检索",
                    "skipped",
                    "输入未通过安全审查",
                    duration_ms=self._elapsed_ms(started_at),
                ),
            }
        payload = state["payload"]
        context = state["context"]
        raw_citations = await self.retriever.retrieve(state["db"], context.course_id, payload.message, context.concept_id)
        refuse, top_score = should_refuse_low_confidence(raw_citations, require_citations=payload.require_citations)
        citations = [] if refuse else raw_citations
        refusal_reason = None
        if refuse:
            refusal_reason = "low_confidence" if raw_citations else "no_hit"
            self._record_guardrail_refusal(
                state,
                query=payload.message,
                top_score=top_score,
                reason=refusal_reason,
            )
        if citations:
            detail = f"命中 {len(citations)} 条引用（Top {top_score:.0%}）"
            trace_status = "completed"
        elif refuse and raw_citations:
            detail = (
                f"Top 置信度 {top_score:.0%} < 阈值 {settings.RAG_RETRIEVAL_MIN_SCORE:.0%}，"
                "已主动拒答以防幻觉"
            )
            trace_status = "blocked"
        else:
            detail = "未命中可靠课程依据"
            trace_status = "warning"
        return {
            "citations": citations,
            "retrieval_refusal_reason": refusal_reason,
            "trace": self._append_trace(
                state,
                "课程检索",
                trace_status,
                detail,
                duration_ms=self._elapsed_ms(started_at),
            ),
        }

    async def _node_generate(self, state: AgentWorkflowState) -> AgentWorkflowState:
        """根据路由、检索和安全状态生成回答或资源生成提示。"""
        started_at = time.perf_counter()
        payload = state["payload"]
        context = state["context"]
        citations = state.get("citations") or []
        safe = state.get("safe", True)

        if is_general_learning(payload) and self._resolve_route_decision(payload.message) == "resource_request":
            messages = self._build_model_messages(
                payload=payload,
                context=context,
                citations=[],
                intent="general_resource_markdown",
                profile_context=state.get("profile_context"),
            )
            gateway = ModelGateway(state["db"])
            result = await gateway.complete_chat(
                messages=messages,
                course_slug=None,
                provider_code=gateway.resolve_course_chat_provider(None),
                agent_name="回答生成",
                temperature=settings.MODEL_GATEWAY_TEMPERATURE,
                max_tokens=settings.MODEL_GATEWAY_MAX_TOKENS,
                allow_fallback=True,
            )
            answer, output_safety = self._apply_output_safety(result.answer)
            status = "completed" if not result.is_fallback else "warning"
            detail = f"{result.display_name}/{result.model} · 通用资料生成 · {result.latency_ms}ms"
            return {
                "answer": answer,
                "quality": output_safety,
                "model_meta": {
                    "provider": result.provider,
                    "display_name": result.display_name,
                    "model": result.model,
                    "status": result.status,
                    "latency_ms": result.latency_ms,
                    "is_fallback": result.is_fallback,
                    "error": result.error,
                },
                "trace": self._append_trace(state, "回答生成", status, detail, duration_ms=self._elapsed_ms(started_at)),
            }

        if state.get("route_decision") == "resource_request":
            resource_type = self._infer_resource_type(payload.message, payload.preferred_resource_type)
            label = RESOURCE_TYPE_LABELS.get(resource_type, resource_type)
            answer = (
                f"已识别为「{label}」资源生成请求。"
                "请确认右侧建议操作，或开启自动资源生成；系统会基于当前课程检索结果创建资源任务。"
            )
            if citations:
                answer += f"\n\n已检索到 {len(citations)} 条课程依据，可在引用面板查看。"
            return {
                "answer": answer,
                "model_meta": {"status": "skipped", "reason": "resource_request_short_circuit"},
                "trace": self._append_trace(
                    state,
                    "回答生成",
                    "skipped",
                    "资源意图短路，避免长篇对话生成",
                    duration_ms=self._elapsed_ms(started_at),
                ),
            }

        if not safe or (payload.require_citations and not citations):
            answer = self._compose_guarded_answer(
                payload=payload,
                context=context,
                citations=citations,
                safe=safe,
                refusal_reason=state.get("retrieval_refusal_reason"),
            )
            reason = "unsafe_or_no_citation"
            if state.get("retrieval_refusal_reason") == "low_confidence":
                reason = "low_confidence_guardrail"
            return {
                "answer": answer,
                "model_meta": {"status": "skipped", "reason": reason},
                "trace": self._append_trace(
                    state,
                    "回答生成",
                    "skipped",
                    "安全拦截或无可靠课程来源",
                    duration_ms=self._elapsed_ms(started_at),
                ),
            }

        model_intent = "general_chat" if is_general_learning(payload) else state.get("intent", "course_qa")
        messages = self._build_model_messages(
            payload=payload,
            context=context,
            citations=citations,
            intent=model_intent,
            profile_context=state.get("profile_context"),
        )
        gateway = ModelGateway(state["db"])
        course_slug = context.course_id or None
        result = await gateway.complete_chat(
            messages=messages,
            course_slug=course_slug,
            provider_code=gateway.resolve_course_chat_provider(course_slug),
            agent_name="回答生成",
            temperature=settings.MODEL_GATEWAY_TEMPERATURE,
            max_tokens=settings.MODEL_GATEWAY_MAX_TOKENS,
            allow_fallback=True,
        )
        answer, output_safety = self._apply_output_safety(result.answer)
        status = "completed" if not result.is_fallback else "warning"
        detail = f"{result.display_name}/{result.model} · {result.status} · {result.latency_ms}ms"
        return {
            "answer": answer,
            "quality": output_safety,
            "model_meta": {
                "provider": result.provider,
                "display_name": result.display_name,
                "model": result.model,
                "status": result.status,
                "latency_ms": result.latency_ms,
                "is_fallback": result.is_fallback,
                "error": result.error,
            },
            "trace": self._append_trace(state, "回答生成", status, detail, duration_ms=self._elapsed_ms(started_at)),
        }

    def _node_cite_check(self, state: AgentWorkflowState) -> AgentWorkflowState:
        started_at = time.perf_counter()
        citations = state.get("citations") or []
        quality = dict(state.get("quality") or {})
        if not state.get("safe", True):
            quality.update({"cite_check": "skipped", "citation_coverage": None})
            return {
                "quality": quality,
                "trace": self._append_trace(
                    state,
                    "引用核验",
                    "skipped",
                    "安全拦截场景不做引用核验",
                    duration_ms=self._elapsed_ms(started_at),
                ),
            }

        result = self.cite_verifier.verify(state.get("answer", ""), citations)
        quality.update(self.cite_verifier.quality_dict(result))
        trace_status = {"passed": "completed", "warning": "warning", "failed": "blocked"}[result.status]
        answer = state.get("answer", "")
        if result.status == "failed" and citations:
            answer = (
                "根据课程引用核验，当前回答中存在无法被课程资料支撑的事实表述，已拦截原回答。"
                f" 具体问题：{result.summary}。请结合右侧引用卡片重新提问或缩小问题范围。"
            )
        return {
            "answer": answer,
            "quality": quality,
            "trace": self._append_trace(
                state,
                "引用核验",
                trace_status,
                result.summary,
                duration_ms=self._elapsed_ms(started_at),
            ),
        }

    def _node_orchestrate(self, state: AgentWorkflowState) -> AgentWorkflowState:
        """根据资源意图决定是否创建生成任务或返回建议操作。"""
        started_at = time.perf_counter()
        payload = state["payload"]
        if is_general_learning(payload) and state.get("route_decision") != "resource_request":
            return {
                "suggested_actions": [],
                "resource_task_id": None,
                "trace": self._append_trace(
                    state,
                    "资源编排",
                    "skipped",
                    "通用模式不创建课程资源任务",
                    duration_ms=self._elapsed_ms(started_at),
                ),
            }
        suggested_actions = self._build_suggested_actions(state)
        resource_task_id = state.get("resource_task_id")
        if state.get("route_decision") == "resource_request" and payload.auto_generate_resource:
            context = state.get("context")
            concept_id = payload.concept_id or (context.concept_id if context else None)
            if concept_id or is_general_learning(payload):
                resource_type = self._infer_resource_type(payload.message, payload.preferred_resource_type)
                task_payload = ResourceGenerateRequest(
                    scope="general" if is_general_learning(payload) else "course",
                    course_id=payload.course_id,
                    concept_id=None if is_general_learning(payload) else concept_id,
                    path_node_id=payload.path_node_id,
                    resource_type=resource_type,
                    difficulty="medium",
                    goal=payload.message[:500],
                    topic=payload.message[:120] if is_general_learning(payload) else None,
                    requirements=(
                        "由 AI 对话意图自动触发的通用资源任务，不得伪造课程资料引用。"
                        if is_general_learning(payload)
                        else "由 AI 对话意图自动触发，需包含课程引用与可执行练习。"
                    ),
                    need_course_evidence=not is_general_learning(payload),
                )
                task = ResourceRepository(state["db"]).create_generation_task(task_payload, state["user_id"])
                resource_task_id = task.get("task_id") or None
                if resource_task_id:
                    enqueue_resource_generation(resource_task_id)
                    suggested_actions = []
        return {
            "suggested_actions": suggested_actions,
            "resource_task_id": resource_task_id,
            "trace": self._append_trace(
                state,
                "资源编排",
                "completed",
                resource_task_id or (suggested_actions[0].reason if suggested_actions else "无需后续资源动作"),
                duration_ms=self._elapsed_ms(started_at),
            ),
        }

    async def _node_profile(self, state: AgentWorkflowState) -> AgentWorkflowState:
        """把本轮对话沉淀为学习画像证据，并返回最新画像上下文。"""
        started_at = time.perf_counter()
        db = state["db"]
        payload = state["payload"]
        profile_repo = LearningProfileRepository(db)
        user = db.execute(select(User).where(User.external_id == state["user_id"])).scalar_one_or_none()
        if not user:
            return {
                "trace": self._append_trace(
                    state,
                    "画像更新",
                    "skipped",
                    "用户不存在",
                    duration_ms=self._elapsed_ms(started_at),
                )
            }
        extractor = ProfileExtractor(db)
        if is_general_learning(payload):
            conversation_id = state.get("conversation_id")
            # 引导模式已通过 LLM 结构化返回直写画像，跳过 extractor 避免重复抽取/冲突，
            # 仅记录会话证据以保留对话历史用于后续路径补救
            if state.get("onboarding_mode") and state.get("onboarding_dimensions_written"):
                profile_repo.record_session_evidence(
                    user=user,
                    conversation_id=conversation_id,
                    course=None,
                    message=payload.message,
                    intent=state.get("intent"),
                    answer=state.get("answer"),
                )
                db.commit()
                profile_context = profile_repo.resolve_context(
                    user_external_id=state["user_id"],
                    course_id=None,
                    conversation_id=conversation_id,
                    message=payload.message,
                    task_type=payload.intent_type,
                )
                return {
                    "profile_context": profile_context,
                    "trace": self._append_trace(
                        state,
                        "画像更新",
                        "completed",
                        "引导模式 LLM 直写画像，跳过 extractor",
                        duration_ms=self._elapsed_ms(started_at),
                    ),
                }
            dimensions, extraction_method = await extractor.extract(
                message=payload.message,
                course_slug="general",
                answer=state.get("answer"),
                intent=state.get("intent"),
            )
            profile_repo.apply_dimensions_to_global(
                user=user,
                dimensions=dimensions,
                source_type="conversation",
                source_id=conversation_id,
                conversation_id=conversation_id,
            )
            profile_repo.record_session_evidence(
                user=user,
                conversation_id=conversation_id,
                course=None,
                message=payload.message,
                intent=state.get("intent"),
                answer=state.get("answer"),
            )
            db.commit()
            method_label = "LLM" if extraction_method == "llm" else "规则"
            profile_context = profile_repo.resolve_context(
                user_external_id=state["user_id"],
                course_id=None,
                conversation_id=conversation_id,
                message=payload.message,
                task_type=payload.intent_type,
            )
            return {
                "profile_context": profile_context,
                "trace": self._append_trace(
                    state,
                    "画像更新",
                    "completed",
                    f"通用画像已抽取 {len(dimensions)} 个维度（{method_label}）",
                    duration_ms=self._elapsed_ms(started_at),
                ),
            }
        course = db.execute(select(Course).where(Course.slug == payload.course_id)).scalar_one_or_none()
        if not course:
            return {
                "trace": self._append_trace(
                    state,
                    "画像更新",
                    "skipped",
                    "课程不存在",
                    duration_ms=self._elapsed_ms(started_at),
                )
            }
        concept = None
        if payload.concept_id:
            concept = db.execute(
                select(CourseConcept).where(CourseConcept.course_id == course.id, CourseConcept.code == payload.concept_id)
            ).scalar_one_or_none()
        dimensions, extraction_method = await extractor.extract(
            message=payload.message,
            course_slug=payload.course_id,
            answer=state.get("answer"),
            intent=state.get("intent"),
        )
        profile_repo.apply_dimensions_to_course(
            user=user,
            course=course,
            dimensions=dimensions,
            source_type="conversation",
            source_id=state.get("conversation_id"),
            conversation_id=state.get("conversation_id"),
        )
        profile_repo.record_session_evidence(
            user=user,
            conversation_id=state.get("conversation_id"),
            course=course,
            message=payload.message,
            intent=state.get("intent"),
            answer=state.get("answer"),
        )
        LearningEventRecorder(db).record(
            course_id=course.id,
            user_id=user.id,
            concept_id=concept.id if concept else None,
            event_type="ai_interaction_closed_loop",
            source_type="conversation",
            source_id=state.get("conversation_id"),
            evidence={
                "intent": state.get("intent"),
                "citation_count": len(state.get("citations") or []),
                "model_status": (state.get("model_meta") or {}).get("status"),
                "profile_dimensions": [dim.dimension_key for dim in dimensions],
                "profile_extraction": extraction_method,
                "path_effect": "regenerate_path",
                "next_actions": ["generate_resource", "submit_assessment", "continue_path"],
                "no_source_remediation": "upload_material_or_notify_admin" if not (state.get("citations") or []) else None,
            },
        )
        db.commit()
        method_label = "LLM" if extraction_method == "llm" else "规则"
        profile_context = profile_repo.resolve_context(
            user_external_id=state["user_id"],
            course_id=payload.course_id,
            conversation_id=state.get("conversation_id"),
            message=payload.message,
            task_type=payload.intent_type,
        )
        return {
            "profile_context": profile_context,
            "trace": self._append_trace(
                state,
                "画像更新",
                "completed",
                f"已抽取 {len(dimensions)} 个画像维度（{method_label}）",
                duration_ms=self._elapsed_ms(started_at),
            )
        }

    def _node_path(self, state: AgentWorkflowState) -> AgentWorkflowState:
        started_at = time.perf_counter()
        payload = state["payload"]
        if is_general_learning(payload):
            return {
                "trace": self._append_trace(
                    state,
                    "路径调整",
                    "skipped",
                    "通用模式不刷新课程学习路径",
                    duration_ms=self._elapsed_ms(started_at),
                ),
            }
        LearningRepository(state["db"]).generate_path(payload.course_id or "", state["user_id"])
        return {
            "trace": self._append_trace(
                state,
                "路径调整",
                "completed",
                "已根据最新画像与掌握度刷新路径",
                duration_ms=self._elapsed_ms(started_at),
            ),
        }

    def _persist_conversation_turn(self, state: AgentWorkflowState) -> None:
        """持久化用户消息、助手回复、引用和执行轨迹。"""
        payload = state["payload"]
        user_id = state.get("user_id")
        conversation_id = state.get("conversation_id")
        if not user_id or not conversation_id:
            return

        repo = ConversationRepository(state["db"])
        user = repo.resolve_user(user_id)
        if is_general_learning(payload):
            conversation = repo.get_conversation_for_scope(conversation_id, None, user.id if user else None)
        else:
            course = repo.resolve_course(payload.course_id or "")
            if not course:
                return
            conversation = repo.get_conversation_for_scope(conversation_id, course.id, user.id if user else None)
        if not conversation:
            return

        default_titles = {"课程对话", "新会话", "通用学习对话"}
        if payload.message.strip() and conversation.title in default_titles:
            conversation.title = payload.message.strip()[:255]

        repo.append_message(
            conversation,
            "user",
            payload.message,
            {
                "concept_id": payload.concept_id,
                "path_node_id": payload.path_node_id,
                "intent": state.get("intent"),
            },
        )
        assistant_meta: dict[str, object] = {"model_meta": state.get("model_meta") or {}}
        if not state.get("safe", True) or (payload.require_citations and not (state.get("citations") or [])):
            refusal = state.get("retrieval_refusal_reason")
            assistant_meta["refusal_reason"] = (
                "low_confidence_guardrail" if refusal == "low_confidence" else "unsafe_or_no_citation"
            )
        assistant_message = repo.append_message(
            conversation,
            "assistant",
            state.get("answer", ""),
            assistant_meta,
        )
        repo.append_citations(assistant_message, state.get("citations") or [])
        repo.append_trace(conversation, assistant_message, state.get("trace") or [])
        repo.commit()
        state["conversation_id"] = str(conversation.id)

    async def run_chat(self, payload: ChatRequest, db: Session, user_id: str) -> ChatResponse:
        """执行一次完整对话工作流并返回 REST 响应模型。"""
        initial_state: AgentWorkflowState = {"payload": payload, "db": db, "user_id": user_id, "trace": []}
        if self.graph is not None:
            state = await self.graph.ainvoke(initial_state)
        else:
            state = await self._run_without_graph(initial_state)
        self._persist_conversation_turn(state)
        quality_payload = state.get("quality") or {}
        return ChatResponse(
            conversation_id=state.get("conversation_id") or payload.conversation_id or f"conv_{uuid4().hex[:12]}",
            answer=state.get("answer", ""),
            citations=state.get("citations") or [],
            agent_trace=state.get("trace") or [],
            suggested_actions=state.get("suggested_actions") or [],
            quality=ChatQuality(
                cite_check=quality_payload.get("cite_check", "skipped"),
                safety=quality_payload.get("safety", "passed"),
                citation_coverage=quality_payload.get("citation_coverage"),
            ),
            resource_task_id=state.get("resource_task_id"),
        )

    async def _run_without_graph(self, state: AgentWorkflowState) -> AgentWorkflowState:
        merged = {**state, **self._node_context(state)}
        merged = {**merged, **await self._node_route(merged)}
        merged = {**merged, **self._node_safety(merged)}
        # 按意图分支：general_chat 与 default_chat 跳过强制检索
        after_safety: str = self._route_to_next_after_safety(merged)
        if after_safety == "retrieve":
            merged = {**merged, **await self._node_retrieve(merged)}
        merged = {**merged, **await self._node_generate(merged)}
        # 按意图分支：general_chat 直接结束，不校验引用、不更新画像/路径
        after_generate: str = self._route_to_next_after_generate(merged)
        if after_generate == "cite_check":
            merged = {**merged, **self._node_cite_check(merged)}
            merged = {**merged, **await self._node_profile(merged)}
            merged = {**merged, **self._node_path(merged)}
            merged = {**merged, **self._node_orchestrate(merged)}
        return merged

    async def stream_chat(self, payload: ChatRequest, db: Session, user_id: str) -> AsyncIterator[dict[str, Any]]:
        """为 AI 自习室输出前端友好的 WebSocket 事件。"""
        if payload.intent_type in {"COURSE_RAG_QA", "KNOWLEDGE_QA"} and is_general_learning(payload):
            yield {"type": "error", "code": "course_required", "message": "请选择课程后使用课程资料问答"}
            return
        if payload.intent_type == "RESOURCE_GENERATION":
            async for event in self._stream_resource_generation(payload, db, user_id):
                yield event
            return
        if payload.intent_type in {"COURSE_RAG_QA", "KNOWLEDGE_QA"} and settings.RAG_BACKEND == "iflytek_chatdoc":
            async for event in self.stream_chatdoc_qa(payload, db, user_id):
                yield event
            return

        state: AgentWorkflowState = {"payload": payload, "db": db, "user_id": user_id, "trace": []}
        _start_time = time.time()
        _start_monotonic = time.monotonic()

        onboarding_service = OnboardingService(db)
        onboarding_history = list(payload.onboarding_history or [])
        cold_start = is_general_learning(payload) and (
            bool(onboarding_history)
            or onboarding_service.is_cold_start(user_id)
            or getattr(payload, "force_onboarding", False)
        )
        if cold_start and is_general_learning(payload):
            state["onboarding_mode"] = True
        else:
            state["onboarding_mode"] = False

        yield {"type": "agent_trace", "event": AgentTraceEvent(step="课程上下文", status="running", detail="解析课程、会话与知识点")}
        state = {**state, **self._node_context(state)}
        yield {"type": "session_started", "conversation_id": state["conversation_id"]}
        yield {"type": "agent_trace", "event": state["trace"][-1]}
        await asyncio.sleep(0.03)

        yield {"type": "agent_trace", "event": AgentTraceEvent(step="意图路由", status="running", detail="判断问答、资源生成或评估意图")}
        state = {**state, **await self._node_route(state)}
        yield {"type": "agent_trace", "event": state["trace"][-1]}
        await asyncio.sleep(0.03)

        yield {"type": "agent_trace", "event": AgentTraceEvent(step="安全审查", status="running", detail="检查隐私、作弊与高风险内容")}
        state = {**state, **self._node_safety(state)}
        yield {"type": "agent_trace", "event": state["trace"][-1]}
        await asyncio.sleep(0.03)

        # 工作流状态推送：完成公共前缀后的分支决策
        yield {
            "type": "workflow_update",
            "update": WorkflowStateUpdate(
                snapshot=WorkflowStateSnapshot(
                    current_node="safety",
                    completed_nodes=["load_context", "route", "safety"],
                    intent=state.get("intent", "default_chat"),
                    status="running",
                    started_at=_start_time,
                    elapsed_ms=int((time.monotonic() - _start_monotonic) * 1000),
                    route_decision=state.get("route_decision", "default_chat"),
                ),
                trace=list(state.get("trace") or []),
                previous_node="safety",
            ),
        }
        # 按意图分流：default_chat / general_chat 跳过强制检索
        after_safety: str = self._route_to_next_after_safety(state)
        if after_safety == "retrieve":
            yield {"type": "agent_trace", "event": AgentTraceEvent(step="课程检索", status="running", detail="限定当前课程知识库检索")}
            state = {**state, **await self._node_retrieve(state)}
            yield {"type": "agent_trace", "event": state["trace"][-1]}
            yield {"type": "citation_update", "citations": state.get("citations") or []}
            await asyncio.sleep(0.03)
        else:
            yield {"type": "agent_trace", "event": AgentTraceEvent(step="课程检索", status="skipped", detail=f"{state.get('route_decision', 'default_chat')} 意图无需强制检索")}

        yield {"type": "agent_trace", "event": AgentTraceEvent(step="回答生成", status="running", detail="通过模型网关调用课程对话模型")}
        onboarding_round = (
            onboarding_service.infer_next_round(onboarding_history) if state.get("onboarding_mode") else 1
        )
        if not state.get("safe", True) or (payload.require_citations and not (state.get("citations") or [])):
            state = {**state, **await self._node_generate(state)}
            yield {"type": "agent_trace", "event": state["trace"][-1]}
            for chunk in self._chunk_text(state.get("answer", "")):
                yield {"type": "text_delta", "delta": chunk}
                await asyncio.sleep(0.02)
        else:
            payload_for_stream = state["payload"]
            model_intent = "general_chat" if is_general_learning(payload_for_stream) else state.get("intent", "course_qa")
            onboarding_prompt_suffix = ""
            is_onboarding = bool(state.get("onboarding_mode"))
            if is_onboarding:
                current_dims = onboarding_service.build_current_dimensions(user_id)
                onboarding_prompt_suffix = onboarding_service.build_onboarding_system_prompt(
                    onboarding_round,
                    current_dims,
                    onboarding_history,
                )
                # chips 已由 system prompt 要求 LLM 在 JSON 中统一返回，
                # 不再追加 build_llm_chips_prompt，避免与 JSON schema 提示冲突
            messages = self._build_model_messages(
                payload=payload_for_stream,
                context=state["context"],
                citations=state.get("citations") or [],
                intent=model_intent,
                profile_context=state.get("profile_context"),
                onboarding_prompt_suffix=onboarding_prompt_suffix,
                onboarding_history=onboarding_history if is_onboarding else None,
            )
            answer_parts: list[str] = []
            model_done: dict[str, Any] = {}
            gateway = ModelGateway(db)
            course_slug = state["context"].course_id or None
            async for event in gateway.stream_chat(
                messages=messages,
                course_slug=course_slug,
                provider_code=gateway.resolve_course_chat_provider(course_slug),
                agent_name="回答生成",
                temperature=settings.MODEL_GATEWAY_TEMPERATURE,
                max_tokens=settings.MODEL_GATEWAY_MAX_TOKENS,
                allow_fallback=True,
            ):
                if event["type"] == "model_start":
                    yield {
                        "type": "agent_trace",
                        "event": AgentTraceEvent(
                            step="模型网关",
                            status="completed",
                            detail=f"{event['display_name']}/{event['model']} · key_source={event['key_source']}",
                        ),
                    }
                elif event["type"] == "text_delta":
                    answer_parts.append(event["delta"])
                    # 引导模式缓冲完整 answer 后解析 JSON，不直接透传 text_delta；
                    # 非引导模式保持原逻辑直接透传，前端实时渲染
                    if not is_onboarding:
                        yield {"type": "text_delta", "delta": event["delta"]}
                elif event["type"] == "model_done":
                    model_done = event
            raw_answer = "".join(answer_parts)

            if is_onboarding:
                # 解析结构化 JSON：user_visible + dimensions + chips
                user_visible, parsed_dims, parsed_chips = _parse_onboarding_structured_answer(raw_answer)
                # dimensions 直写全局画像（精确，跳过 extractor）
                if parsed_dims:
                    user = db.execute(select(User).where(User.external_id == user_id)).scalar_one_or_none()
                    if user:
                        extracted = [
                            ExtractedDimension(
                                dimension_key=d["key"],
                                dimension_name=DIMENSION_NAMES.get(d["key"], d["key"]),
                                score=int(d.get("confidence", 0.8) * 100),
                                label=d.get("label", "待观察"),
                                evidence=payload.message,
                                confidence=float(d.get("confidence", 0.8)),
                                method="llm_onboarding",
                            )
                            for d in parsed_dims
                        ]
                        LearningProfileRepository(db).apply_dimensions_to_global(
                            user=user,
                            dimensions=extracted,
                            source_type="onboarding_llm",
                            source_id=state.get("conversation_id"),
                            # 不传 force_confidence，使用 LLM 给定的 confidence
                        )
                        db.commit()
                # chips 设置给 onboarding_service（第 2 轮起），build_chips 会优先消费 _llm_chips
                if parsed_chips and onboarding_round >= 2:
                    onboarding_service._llm_chips = parsed_chips
                # user_visible 分块打字机 yield 给前端
                for chunk in self._chunk_text(user_visible):
                    yield {"type": "text_delta", "delta": chunk}
                    await asyncio.sleep(0.02)
                answer, output_safety = self._apply_output_safety(user_visible)
                state["answer"] = answer
                state["quality"] = output_safety
                state["model_meta"] = model_done
                # 标记已通过 LLM 结构化返回直写画像，_node_profile 跳过 extractor 避免重复抽取
                if parsed_dims:
                    state["onboarding_dimensions_written"] = True
            else:
                answer, output_safety = self._apply_output_safety(raw_answer)
                state["answer"] = answer
                state["quality"] = output_safety
                state["model_meta"] = model_done
            status = "completed" if not model_done.get("is_fallback") else "warning"
            detail = f"{model_done.get('display_name')}/{model_done.get('model')} · {model_done.get('status')} · {model_done.get('latency_ms')}ms"
            state["trace"] = self._append_trace(state, "回答生成", status, detail)
            yield {"type": "agent_trace", "event": state["trace"][-1]}

        # 按意图分支：general_chat 直接结束，不校验引用、不更新画像/路径
        after_generate: str = self._route_to_next_after_generate(state)
        quality_payload = state.get("quality") or {}
        onboarding_meta_payload: dict[str, Any] | None = None
        suggested_actions: list[Any] = []
        if after_generate == "cite_check":
            # 工作流状态推送：进入后半段（引用检查→画像→路径→编排）
            completed_before_cite = ["load_context", "route", "safety"]
            if state.get("route_decision") not in {"default_chat", "general_chat"}:
                completed_before_cite.append("retrieve")
            completed_before_cite.append("generate")
            yield {
                "type": "workflow_update",
                "update": WorkflowStateUpdate(
                    snapshot=WorkflowStateSnapshot(
                        current_node="cite_check",
                        completed_nodes=completed_before_cite,
                        intent=state.get("intent", "default_chat"),
                        status="running",
                        started_at=_start_time,
                        elapsed_ms=int((time.monotonic() - _start_monotonic) * 1000),
                        route_decision=state.get("route_decision", "default_chat"),
                    ),
                    trace=list(state.get("trace") or []),
                    previous_node="generate",
                ),
            }
            state = {**state, **self._node_cite_check(state)}
            yield {"type": "agent_trace", "event": state["trace"][-1]}
            quality_payload = state.get("quality") or {}
            yield {
                "type": "quality_update",
                "quality": {
                    "cite_check": quality_payload.get("cite_check", "skipped"),
                    "safety": quality_payload.get("safety", "passed"),
                    "citation_coverage": quality_payload.get("citation_coverage"),
                },
            }
            state = {**state, **await self._node_profile(state)}
            yield {"type": "agent_trace", "event": state["trace"][-1]}
            yield {"type": "profile_updated", "summary": "本轮对话已作为画像证据记录，后续可驱动路径补救。"}

            if state.get("onboarding_mode"):
                # chips 已在前置分支通过 _parse_onboarding_structured_answer 统一解析并注入
                # onboarding_service._llm_chips；此处不再做正则兜底，避免覆盖已设置的 chips
                # 或误截断 state["answer"]（已为 user_visible 纯文本）
                completed_round = onboarding_service.infer_completed_round(onboarding_history)
                meta = onboarding_service.assemble_metadata(
                    user_external_id=user_id,
                    round_num=completed_round,
                    user_message=payload.message,
                    history=onboarding_history,
                    answer_after_round=True,
                )
                state["answer"] = onboarding_service.onboarding_answer_for_round(
                    completed_round,
                    onboarding_history,
                    state.get("answer", ""),
                    answer_after_round=True,
                )
                onboarding_meta_payload = meta.model_dump(by_alias=True)
                state["onboarding_meta"] = onboarding_meta_payload
                yield {"type": "onboarding_update", "meta": {"onboarding": onboarding_meta_payload}}

            state = {**state, **self._node_path(state)}
            yield {"type": "agent_trace", "event": state["trace"][-1]}
            yield {"type": "path_updated", "status": "unchanged", "message": "当前节点保持学习中。"}
            state = {**state, **self._node_orchestrate(state)}
            yield {"type": "agent_trace", "event": state["trace"][-1]}
            suggested_actions = state.get("suggested_actions") or []
            if suggested_actions:
                yield {
                    "type": "suggested_actions",
                    "actions": [action.model_dump() for action in suggested_actions],
                }
        else:
            # general_chat 直接结束，不校验引用、不更新画像/路径
            yield {
                "type": "workflow_update",
                "update": WorkflowStateUpdate(
                    snapshot=WorkflowStateSnapshot(
                        current_node="generate",
                        completed_nodes=["load_context", "route", "safety", "generate"],
                        intent=state.get("intent", "general_chat"),
                        status="completed",
                        started_at=_start_time,
                        elapsed_ms=int((time.monotonic() - _start_monotonic) * 1000),
                        route_decision=state.get("route_decision", "general_chat"),
                    ),
                    trace=list(state.get("trace") or []),
                    previous_node="generate",
                ),
            }
        self._persist_conversation_turn(state)
        quality_payload = state.get("quality") or {}
        done_payload: dict[str, Any] = {
            "type": "done",
            "conversation_id": state["conversation_id"],
            "answer": state.get("answer", ""),
            "citations": state.get("citations") or [],
            "agent_trace": state.get("trace") or [],
            "model_meta": state.get("model_meta") or {},
            "suggested_actions": [action.model_dump() for action in suggested_actions],
            "quality": {
                "cite_check": quality_payload.get("cite_check", "skipped"),
                "safety": quality_payload.get("safety", "passed"),
                "citation_coverage": quality_payload.get("citation_coverage"),
            },
            "resource_task_id": state.get("resource_task_id"),
        }
        if onboarding_meta_payload is not None:
            done_payload["meta"] = {"onboarding": onboarding_meta_payload}
        yield done_payload

    async def stream_chatdoc_qa(self, payload: ChatRequest, db: Session, user_id: str) -> AsyncIterator[dict[str, Any]]:
        """公开的 ChatDoc 课程资料问答事件流入口，供编排层复用。"""

        async for event in self._stream_chatdoc_qa(payload, db, user_id):
            yield event

    async def _stream_chatdoc_qa(self, payload: ChatRequest, db: Session, user_id: str) -> AsyncIterator[dict[str, Any]]:
        """官方 ChatDoc 文档问答 WebSocket 代理，用于 COURSE_RAG_QA / KNOWLEDGE_QA。"""
        if is_general_learning(payload) or not payload.course_id:
            yield {"type": "error", "code": "course_required", "message": "请选择课程后使用课程资料问答"}
            return
        state: AgentWorkflowState = {"payload": payload, "db": db, "user_id": user_id, "trace": []}
        yield {"type": "agent_trace", "event": AgentTraceEvent(step="Router", status="running", detail="课程资料问答模式")}
        state = {**state, **self._node_context(state)}
        yield {"type": "session_started", "conversation_id": state["conversation_id"]}
        yield {"type": "agent_trace", "event": AgentTraceEvent(step="课程上下文", status="completed", detail=state["context"].course_title)}

        binding = resolve_course_chatdoc_binding(
            db,
            payload.course_id,
            concept_code=payload.concept_id,
        )
        if not binding or not binding.knowledge_ready or not binding.primary_file_id:
            reason = binding.blocking_reason if binding else "课程不存在"
            if reason and "凭证" in reason:
                message = "当前课程未配置云端 RAG / 文档问答服务，请管理员先到网关中心配置。"
            else:
                message = "当前课程资料还没有完成云端向量化，暂时不能使用课程资料问答。你可以切换为普通 AI 问答。"
            yield {"type": "error", "code": "knowledge_not_ready", "message": message or reason or "知识库未就绪"}
            return

        config_service = ChatdocConfigService(db)
        pipeline = config_service.pipeline_config(binding.integration_key)
        client = chatdoc_client_for_db(db, integration_key=binding.integration_key)

        yield {
            "type": "agent_trace",
            "event": AgentTraceEvent(
                step="Retrieve",
                status="running",
                detail="正在连接课程资料问答服务",
            ),
        }
        yield {
            "type": "agent_trace",
            "event": AgentTraceEvent(
                step="Generate",
                status="running",
                detail=f"等待云端 RAG 返回回答 · fileId={binding.primary_file_id}",
            ),
        }

        answer_parts: list[str] = []
        qa_errored = False
        qa_error_message: str | None = None
        course = db.execute(select(Course).where(Course.slug == payload.course_id)).scalar_one_or_none()
        user = db.execute(select(User).where(User.external_id == user_id)).scalar_one_or_none()
        profile_context = state.get("profile_context")
        qa_query = payload.message
        if profile_context:
            qa_query = (
                "请基于课程资料回答学生问题，并结合以下内部画像调整解释层次、例子和术语密度；"
                "不要复述画像字段，不要编造课程资料引用。\n"
                f"内部画像：{profile_context.format_for_prompt()}\n"
                f"学生问题：{payload.message}"
            )
        started_at = time.perf_counter()
        try:
            async for delta in stream_chatdoc_doc_qa(
                client,
                pipeline_config=pipeline,
                file_id=binding.primary_file_id,
                query=qa_query,
            ):
                answer_parts.append(delta)
                yield {"type": "text_delta", "delta": delta}
            ChatdocVendorQuotaService(db).record_doc_qa(integration_key=binding.integration_key)
            db.commit()
        except Exception as exc:
            qa_errored = True
            qa_error_message = str(exc)[:1000]
            logger.warning(
                "讯飞文档问答流式调用失败：conversation_id=%s course_id=%s file_id=%s trace_id=%s",
                state["conversation_id"],
                payload.course_id,
                binding.primary_file_id,
                get_trace_id(),
                exc_info=True,
            )

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        answer = "".join(answer_parts).strip()
        _record_chatdoc_call_log(
            db,
            course_id=course.id if course else None,
            user_id=user.id if user else None,
            latency_ms=latency_ms,
            status="failed" if qa_errored else "success",
            error_message=qa_error_message,
            query=payload.message,
            answer=answer,
            meta_json={
                "trace_id": get_trace_id(),
                "file_id": binding.primary_file_id,
                "course_slug": payload.course_id,
                "integration_key": binding.integration_key,
                "profile_context_used": bool(profile_context),
            },
        )

        if qa_errored and not answer:
            yield {"type": "error", "message": "讯飞文档问答异常，请稍后重试。"}
            return
        if not answer:
            answer = "当前课程资料中没有找到足够依据。你可以切换为普通 AI 问答，我将基于通用知识解释。"
        elif not answer.startswith("基于课程资料回答"):
            answer = f"基于课程资料回答\n\n{answer}"
        state["answer"] = answer
        state["citations"] = []
        state["intent"] = "course_rag_qa"
        state["trace"] = self._append_trace(state, "Generate", "completed", "已通过官方文档问答返回")
        state["trace"] = self._append_trace(state, "Verify", "completed", "等待引用或资料来源校验 · 官方文档问答路径由讯飞侧完成引用")
        state = {**state, **await self._node_profile(state)}
        yield {"type": "agent_trace", "event": state["trace"][-1]}
        yield {"type": "profile_updated", "summary": "课程资料问答已作为画像证据记录。"}

        try:
            related = ExtractedQaRepository(db).related_suggestions(payload.course_id, exclude_question=payload.message)
            if related:
                yield {
                    "type": "extracted_qa_suggestions",
                    "items": [{"id": item["id"], "question": item["question"]} for item in related],
                }
        except Exception:
            logger.debug(
                "读取萃取 QA 推荐失败，将跳过相关问题提示：conversation_id=%s course_id=%s trace_id=%s",
                state["conversation_id"],
                payload.course_id,
                get_trace_id(),
                exc_info=True,
            )

        try:
            self._persist_conversation_turn(state)
        except Exception:
            logger.warning(
                "持久化课程资料问答会话轮次失败：conversation_id=%s course_id=%s user_id=%s trace_id=%s",
                state["conversation_id"],
                payload.course_id,
                user_id,
                get_trace_id(),
                exc_info=True,
            )
        yield {
            "type": "done",
            "conversation_id": state["conversation_id"],
            "answer": answer,
            "citations": [],
            "agent_trace": state.get("trace") or [],
            "suggested_actions": [],
            "quality": {"cite_check": "skipped", "safety": "passed", "citation_coverage": None},
            "resource_task_id": None,
        }

    async def _stream_resource_generation(self, payload: ChatRequest, db: Session, user_id: str) -> AsyncIterator[dict[str, Any]]:
        """由 RESOURCE_GENERATION 意图显式触发的 LangGraph 资源生成路径。"""
        state: AgentWorkflowState = {"payload": payload, "db": db, "user_id": user_id, "trace": []}

        yield {
            "type": "agent_trace",
            "event": AgentTraceEvent(
                step="学习上下文",
                status="running",
                detail="资源生成任务绑定课程" if not is_general_learning(payload) else "通用资源生成任务",
            ),
        }
        state = {**state, **self._node_context(state)}
        yield {"type": "session_started", "conversation_id": state["conversation_id"]}
        yield {"type": "agent_trace", "event": state["trace"][-1]}

        state = {**state, **await self._node_route(state)}
        yield {"type": "agent_trace", "event": state["trace"][-1]}
        state = {**state, **self._node_safety(state)}
        yield {"type": "agent_trace", "event": state["trace"][-1]}

        if not state.get("safe", True):
            yield {"type": "error", "message": "资源生成请求未通过安全审查"}
            return

        concept_id = payload.concept_id or state.get("context").concept_id
        if not is_general_learning(payload) and not concept_id:
            yield {"type": "error", "message": "请先选择知识点后再生成资源"}
            return

        resource_type = self._infer_resource_type(payload.message, payload.preferred_resource_type)
        task_payload = ResourceGenerateRequest(
            scope="general" if is_general_learning(payload) else "course",
            course_id=payload.course_id,
            concept_id=None if is_general_learning(payload) else concept_id,
            path_node_id=payload.path_node_id,
            resource_type=resource_type,
            difficulty="medium",
            goal=payload.message[:500],
            topic=payload.message[:120] if is_general_learning(payload) else None,
            requirements=(
                "由浮动菜单触发的通用资源生成任务，不得伪造课程资料引用。"
                if is_general_learning(payload)
                else "由浮动菜单触发的资源生成任务，需包含课程引用与可执行练习。"
            ),
            need_course_evidence=not is_general_learning(payload),
        )
        task = ResourceRepository(db).create_generation_task(task_payload, user_id)
        resource_task_id = task.get("task_id")
        if resource_task_id:
            enqueue_resource_generation(resource_task_id)

        label = RESOURCE_TYPE_LABELS.get(resource_type, resource_type)
        answer = f"已创建「{label}」资源生成任务，请在资源工坊预览进度。"
        state["answer"] = answer
        state["resource_task_id"] = resource_task_id
        state["trace"] = self._append_trace(state, "资源编排", "completed", resource_task_id or "任务创建失败")
        self._persist_conversation_turn(state)

        yield {
            "type": "done",
            "conversation_id": state["conversation_id"],
            "answer": answer,
            "citations": [],
            "agent_trace": state.get("trace") or [],
            "suggested_actions": [],
            "quality": {"cite_check": "skipped", "safety": "passed", "citation_coverage": None},
            "resource_task_id": resource_task_id,
        }

    @staticmethod
    def _chunk_text(text: str, size: int = 18) -> list[str]:
        if not text:
            return []
        return [text[index : index + size] for index in range(0, len(text), size)]

    def _build_model_messages(
        self,
        payload: ChatRequest,
        context: CourseContext,
        citations: list[Citation],
        intent: str,
        profile_context: ProfileContext | None = None,
        onboarding_prompt_suffix: str = "",
        onboarding_history: list[OnboardingHistoryMessage] | None = None,
    ) -> list[dict[str, str]]:
        """组装发送给模型网关的系统消息和用户消息。"""
        citation_text = build_llm_context(citations)
        profile_text = profile_context.format_for_prompt() if profile_context else "暂无画像摘要。"
        profile_rule = (
            "\n内部画像上下文（只用于调整讲解深度、例子、术语密度和资源形式，禁止原样输出给学生）：\n"
            f"{profile_text}"
        )
        if onboarding_prompt_suffix:
            profile_rule += onboarding_prompt_suffix
        if intent == "general_resource_markdown" or (is_general_learning(payload) and intent == "general_chat"):
            system = (
                "你是通用 AI 学习助手，可以帮助学生解释概念、制定学习计划、生成资料和练习题。"
                "没有课程资料时不要伪造教材引用、页码或知识库来源。"
                "当用户请求讲义、题目、学习计划或学习资料时，请直接输出结构清晰的 Markdown（含标题、小节、要点或题目列表）。"
                f"{profile_rule}"
            )
            messages: list[dict[str, str]] = [{"role": "system", "content": system}]
            if onboarding_history:
                for item in onboarding_history:
                    messages.append({"role": item.role, "content": item.content})
            messages.append({"role": "user", "content": f"学生问题：{payload.message}"})
            return messages
        if is_general_learning(payload):
            system = (
                "你是通用 AI 学习助手，可以帮助学生解释概念、制定学习计划、生成资料和练习题。"
                "没有课程资料时不要伪造教材引用、页码或知识库来源。"
                "回答要面向学生，结构清晰，先给结论，再解释原因、例子和下一步学习建议。"
                f"{profile_rule}"
            )
            messages = [{"role": "system", "content": system}]
            if onboarding_history:
                for item in onboarding_history:
                    messages.append({"role": item.role, "content": item.content})
            messages.append({"role": "user", "content": f"学生问题：{payload.message}"})
            return messages
        if intent in {"course_rag_qa", "course_qa"}:
            system = (
                "你是高校课程级个性化学习平台中的 AI 学习助手。"
                "必须优先依据当前课程资料回答，禁止编造教材页码、论文、实验数据或引用。"
                "回答要面向学生，结构清晰，先给结论，再解释原因、例子和下一步学习建议。"
                "如果课程证据不足，要明确说明不足，不要强答。"
                "当引用类型是 PAGE_SUMMARY、FIGURE、TABLE、FORMULA 或带页面证据地址时，要说明这是页面视觉证据，并提示学生可打开原页核对。"
                f"\n当前课程：{context.course_title}"
                f"\n当前意图：课程资料问答"
                f"\n当前知识点：{context.concept_id or '未指定'}"
                f"{profile_rule}"
                f"\n课程引用材料：\n{citation_text}"
            )
            user = (
                f"学生问题：{payload.message}\n\n"
                "请基于上述课程引用材料作答，并在涉及课程事实时用“引用 1/2/3”的方式提示依据。"
            )
        else:
            system = (
                "你是课程学习助手，可以结合当前课程名称、当前知识点和学习画像进行解释；"
                "没有课程资料引用时也可以基于通用知识回答，但不要伪造页码、教材引用或文档来源。"
                "回答要面向学生，结构清晰，先给结论，再解释原因、例子和下一步学习建议。"
                f"\n当前课程：{context.course_title}"
                f"\n当前意图：普通学习对话"
                f"\n当前知识点：{context.concept_id or '未指定'}"
                f"{profile_rule}"
            )
            if citation_text.strip():
                system += f"\n可选课程引用材料：\n{citation_text}"
            user = f"学生问题：{payload.message}"
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def _record_guardrail_refusal(
        self,
        state: AgentWorkflowState,
        *,
        query: str,
        top_score: float,
        reason: str,
    ) -> None:
        """记录 RAG 低置信度拒答事件，用于后续审计和学习闭环。"""
        context = state.get("context")
        db = state.get("db")
        if not context or db is None:
            return
        course = db.execute(select(Course).where(Course.slug == context.course_id)).scalar_one_or_none()
        if not course:
            return
        user = None
        user_external = state.get("user_id")
        if user_external:
            user = db.execute(select(User).where(User.external_id == user_external)).scalar_one_or_none()
        LearningEventRecorder(db).record(
            course_id=course.id,
            user_id=user.id if user else None,
            event_type="rag_guardrail_refused",
            source_type="chat",
            evidence={
                "query": query[:500],
                "top_score": round(top_score, 4),
                "threshold": settings.RAG_RETRIEVAL_MIN_SCORE,
                "reason": reason,
                "trace_id": state.get("trace_id"),
            },
            flush=False,
        )

    def _compose_guarded_answer(
        self,
        payload: ChatRequest,
        context: CourseContext,
        citations: list[Citation],
        safe: bool,
        *,
        refusal_reason: str | None = None,
    ) -> str:
        """生成安全拦截、低置信度或缺少引用时的兼容兜底回复。"""
        if not safe:
            return "这个请求可能涉及不当学术行为或隐私安全风险，我不能直接协助。可以改为提供学习思路、知识点解释或练习建议。"

        if refusal_reason == "low_confidence":
            return (
                f"检索到的课程片段最高相关度未达到安全阈值（{settings.RAG_RETRIEVAL_MIN_SCORE:.0%}），"
                "为避免缺乏依据的幻觉回答，系统已主动拦截。请尝试更具体的问题，或联系管理员补充/审核课程资料。"
            )

        if payload.intent_type in {"COURSE_RAG_QA", "KNOWLEDGE_QA"}:
            return "当前课程资料中没有找到足够依据。你可以切换为普通 AI 问答，我将基于通用知识解释。"

        if not citations:
            return "当前课程知识库没有找到可靠依据。建议先上传对应讲义、实验指导或让管理员补充课程资料后再提问。"

        joined_snippets = "；".join(citation.snippet for citation in citations[:2])
        return (
            f"根据《{context.course_title}》课程知识库，当前问题可从概念定义、前置知识和应用场景三部分理解。"
            f"课程证据摘要：{joined_snippets}。"
        )


def _record_chatdoc_call_log(
    db: Session,
    *,
    course_id: str | None,
    user_id: str | None,
    latency_ms: int,
    status: str,
    error_message: str | None = None,
    query: str = "",
    answer: str = "",
    meta_json: dict[str, Any] | None = None,
) -> None:
    """把 ChatDoc 问答调用记录到 model_call_logs，供管理端查看。"""
    merged = dict(meta_json or {})
    if query:
        merged["query"] = query[:500]
    answer_preview = (answer or "").strip()[:300]
    if answer_preview:
        merged["answer_preview"] = answer_preview
    # 成功调用也在“错误摘要”列展示答案预览，便于后台快速排查效果。
    display_error = error_message or (answer_preview if status == "success" else None)
    try:
        db.add(ModelCallLog(
            course_id=course_id,
            user_id=user_id,
            provider_id=None,
            agent_name="讯飞文档问答",
            capability="doc_qa",
            model_name="iflytek-chatdoc",
            request_count=1,
            latency_ms=max(0, latency_ms),
            status=status,
            error_message=display_error,
            meta_json=merged,
        ))
        db.commit()
    except Exception:
        logger.warning(
            "写入 ChatDoc 文档问答调用日志失败：course_id=%s user_id=%s status=%s trace_id=%s",
            course_id,
            user_id,
            status,
            get_trace_id(),
            exc_info=True,
        )
        db.rollback()
