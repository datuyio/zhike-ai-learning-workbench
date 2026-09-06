from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import Citation
from app.schemas.onboarding import OnboardingHistoryMessage

LearningScope = Literal["general", "course"]

ChatIntentType = Literal[
    "DEFAULT_CHAT",
    "COURSE_RAG_QA",
    "KNOWLEDGE_QA",
    "RESOURCE_GENERATION",
    "GENERAL_CHAT",
]


class ChatRequest(BaseModel):
    """旧版聊天接口请求，保留给 AgentWorkflow 和兼容入口使用。"""

    course_id: str | None = None
    learning_scope: LearningScope = "course"
    conversation_id: str | None = None
    message: str
    concept_id: str | None = None
    path_node_id: str | None = None
    response_mode: str = "stream"
    require_citations: bool = False
    auto_generate_resource: bool = False
    preferred_resource_type: str | None = None
    intent_type: ChatIntentType = "DEFAULT_CHAT"
    onboarding_history: list[OnboardingHistoryMessage] = Field(default_factory=list)
    # 用户在画像页主动触发「重塑学习画像」时置 true，后端跳过冷启动检测强制进入引导模式；
    # 仅在 is_general_learning 时生效，避免污染课程资料问答等受限意图。
    force_onboarding: bool = False

    @model_validator(mode="after")
    def validate_learning_scope(self) -> "ChatRequest":
        """校验学习范围、课程 ID 和意图类型之间的兼容性。"""

        if self.learning_scope == "course" and not self.course_id:
            raise ValueError("course_id is required when learning_scope is course")
        if self.learning_scope == "general":
            if self.intent_type in {"COURSE_RAG_QA", "KNOWLEDGE_QA"}:
                raise ValueError("course-bound intents are not allowed in general learning mode")
        return self


class SuggestedAction(BaseModel):
    """模型回答后建议用户继续执行的资源生成动作。"""

    action: str = "generate_resource"
    resource_type: str
    label: str
    reason: str


class ChatQuality(BaseModel):
    """聊天回答的引用、安全和覆盖度质量信号。"""

    cite_check: str = "skipped"
    safety: str = "passed"
    citation_coverage: str | None = None


class AgentTraceEvent(BaseModel):
    """AI 编排链路中的单步执行状态。

    支持层级调用链：parent_step 指向父节点名称，children 存放子节点列表。
    前端可根据 parent_step 还原树形结构。
    """

    step: str
    status: str
    detail: str | None = None
    duration_ms: int | None = None
    parent_step: str | None = None
    children: list[AgentTraceEvent] = Field(default_factory=list)


class WorkflowStateSnapshot(BaseModel):
    """工作流状态快照，用于前端可视化展示。"""

    current_node: str
    completed_nodes: list[str] = Field(default_factory=list)
    intent: str = "default_chat"
    status: str = "running"
    started_at: float = 0.0
    elapsed_ms: int = 0
    error: str | None = None
    route_decision: str = "default_chat"


class WorkflowStateUpdate(BaseModel):
    """WebSocket 推送的工作流状态更新事件。"""

    snapshot: WorkflowStateSnapshot
    trace: list[AgentTraceEvent] = Field(default_factory=list)
    previous_node: str | None = None


class ChatResponse(BaseModel):
    """旧版聊天接口响应，包含回答、引用、建议动作和资源任务信息。"""

    conversation_id: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    agent_trace: list[AgentTraceEvent] = Field(default_factory=list)
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)
    quality: ChatQuality | None = None
    resource_task_id: str | None = None


class ChatStopResponse(BaseModel):
    """停止流式聊天输出的响应。"""

    conversation_id: str
    status: Literal["stopped"] = "stopped"


AiMessageMode = Literal["default_chat", "course_rag_qa"]
AiActionType = Literal["chat", "resource_generation"]


class AiAvailability(BaseModel):
    """本次 AI 调用的可用性状态。"""

    ok: bool = True
    code: str | None = None
    message: str | None = None
    fallback_action: str | None = None


class AiMessageRequest(BaseModel):
    """统一 AI 编排入口请求，兼容旧 ChatRequest 字段和前端 camelCase 字段。"""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str | None = None
    course_id: str | None = None
    learning_scope: LearningScope | None = None
    conversation_id: str | None = None
    path_node_id: str | None = None
    concept_id: str | None = None
    message: str
    mode: AiMessageMode = "default_chat"
    action_type: AiActionType = "chat"
    resource_type: str | None = None
    need_course_evidence: bool | None = None
    uploaded_doc_id: str | None = None
    client_context: dict = Field(default_factory=dict)
    response_mode: str = "stream"
    require_citations: bool | None = None
    auto_generate_resource: bool = False
    preferred_resource_type: str | None = None
    intent_type: ChatIntentType | None = None
    onboarding_history: list[OnboardingHistoryMessage] = Field(default_factory=list)
    # 用户主动重塑画像时置 true，透传至 ChatRequest 供 workflow 跳过冷启动检测。
    force_onboarding: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: object) -> object:
        """归一化前端 camelCase 和旧 ChatRequest 字段。"""
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        alias_map = {
            "courseId": "course_id",
            "conversationId": "conversation_id",
            "pathNodeId": "path_node_id",
            "conceptId": "concept_id",
            "actionType": "action_type",
            "resourceType": "resource_type",
            "needCourseEvidence": "need_course_evidence",
            "uploadedDocId": "uploaded_doc_id",
            "clientContext": "client_context",
            "responseMode": "response_mode",
            "requireCitations": "require_citations",
            "intentType": "intent_type",
            "onboardingHistory": "onboarding_history",
            "forceOnboarding": "force_onboarding",
        }
        for source, target in alias_map.items():
            if source in normalized and target not in normalized:
                normalized[target] = normalized[source]

        intent = normalized.get("intent_type")
        if intent in {"COURSE_RAG_QA", "KNOWLEDGE_QA"} and "mode" not in normalized:
            normalized["mode"] = "course_rag_qa"
        if intent == "RESOURCE_GENERATION" and "action_type" not in normalized:
            normalized["action_type"] = "resource_generation"
        if normalized.get("mode") == "course_rag_qa" and "require_citations" not in normalized:
            normalized["require_citations"] = True
        return normalized

    @model_validator(mode="after")
    def validate_scope(self) -> "AiMessageRequest":
        """校验课程资料问答必须绑定课程。"""
        if not self.learning_scope:
            self.learning_scope = "course" if self.course_id else "general"
        if self.learning_scope == "general":
            self.course_id = None
        if self.action_type == "resource_generation" and not self.resource_type and self.preferred_resource_type:
            self.resource_type = self.preferred_resource_type
        return self

    def to_chat_request(self) -> ChatRequest:
        """转换为兼容旧 AgentWorkflow 的 ChatRequest。"""
        intent_type: ChatIntentType
        if self.action_type == "resource_generation":
            intent_type = "RESOURCE_GENERATION"
        elif self.mode == "course_rag_qa":
            intent_type = "COURSE_RAG_QA"
        elif self.learning_scope == "general":
            intent_type = "GENERAL_CHAT"
        else:
            intent_type = "DEFAULT_CHAT"
        return ChatRequest(
            course_id=self.course_id,
            learning_scope=self.learning_scope or ("course" if self.course_id else "general"),
            conversation_id=self.conversation_id,
            message=self.message,
            concept_id=self.concept_id,
            path_node_id=self.path_node_id,
            response_mode=self.response_mode,
            require_citations=bool(self.require_citations if self.require_citations is not None else self.mode == "course_rag_qa"),
            auto_generate_resource=self.auto_generate_resource,
            preferred_resource_type=self.resource_type or self.preferred_resource_type,
            intent_type=intent_type,
            onboarding_history=list(self.onboarding_history),
            force_onboarding=self.force_onboarding,
        )


class AiMessageResponse(ChatResponse):
    """统一 AI 编排入口响应。"""

    route: str = "default_chat"
    availability: AiAvailability | None = None


class IntentRouterFeedbackRequest(BaseModel):
    """意图路由反馈，用于持续优化评测集和灰度策略。"""

    trace_id: str | None = None
    conversation_id: str | None = None
    message: str
    predicted_intent: str
    expected_intent: str | None = None
    is_correct: bool
    comment: str | None = None


class IntentRouterFeedbackResponse(BaseModel):
    """意图路由反馈记录结果。"""

    status: Literal["recorded"] = "recorded"
