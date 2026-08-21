from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModelProviderUpsert(BaseModel):
    """模型供应商创建或更新请求。"""

    provider: str = Field(..., description="供应商编码，例如 dashscope_embedding")
    display_name: str
    provider_type: str = "both"
    base_url: str | None = None
    protocol: str = "openai_compatible"
    api_key: str | None = None
    clear_api_key: bool = False
    chat_model: str | None = None
    embedding_model: str | None = None
    image_model: str | None = None
    embedding_dimension: int | None = None
    max_batch_size: int = Field(default=10, ge=1, le=128)
    rate_limit_rps: int | None = Field(default=None, ge=1, le=1000)
    vision_model: str | None = None
    supports_stream: bool = True
    supports_tool_call: bool = False
    supports_json_mode: bool = True
    health_status: str = "standby"
    priority: int = 100
    is_active: bool = True
    is_default: bool = False
    daily_limit: int | None = None
    cost_config_json: dict[str, Any] = Field(default_factory=dict)
    meta_json: dict[str, Any] = Field(default_factory=dict)


class ModelProviderHealthItem(BaseModel):
    """模型供应商健康状态列表项。"""

    provider: str
    display_name: str
    provider_type: str = "both"
    status: str
    priority: int
    is_active: bool = True
    is_default: bool = False
    chat_model: str | None = None
    embedding_model: str | None = None
    image_model: str | None = None
    embedding_dimension: int | None = None
    max_batch_size: int = 10
    rate_limit_rps: int | None = None
    supports_stream: bool = False
    supports_tool_call: bool = False
    supports_json_mode: bool = False
    key_configured: bool = False
    key_source: str = "missing"
    key_masked: str | None = None
    base_url: str | None = None
    protocol: str = "openai_compatible"
    last_checked_at: str | None = None
    last_error: str | None = None
    avg_latency_ms: int | None = None
    consecutive_failures: int = 0
    daily_limit: int | None = None
    cost_config_json: dict[str, Any] = Field(default_factory=dict)
    meta_json: dict[str, Any] = Field(default_factory=dict)


class ModelProviderHealthResponse(BaseModel):
    """模型供应商健康状态列表响应。"""

    items: list[ModelProviderHealthItem]


class ProviderTestResponse(BaseModel):
    """模型供应商连接测试响应。"""

    provider_id: str
    status: str
    chat_stream: bool = False
    embedding: bool = False
    image_generation: bool = False
    json_mode: bool = False
    latency_ms: int | None = None
    model: str | None = None
    embedding_dim: int | None = None
    message: str | None = None
    error: str | None = None


class UserModelOverrideRead(BaseModel):
    """学生端个人模型覆盖配置的读取响应。"""

    provider: str | None = None
    base_url: str | None = None
    chat_model: str | None = None
    embedding_model: str | None = None
    enabled: bool = False
    key_configured: bool = False


class UserModelOverrideUpsert(BaseModel):
    """学生端个人模型覆盖配置的创建或更新请求。"""

    provider: str = Field(..., min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    clear_api_key: bool = False
    chat_model: str = Field(..., min_length=1, max_length=120)
    embedding_model: str | None = Field(default=None, max_length=120)
    enabled: bool = False


class UserModelOverrideDeleteResponse(BaseModel):
    """学生端个人模型覆盖配置的删除响应。"""

    status: str


class CourseModelConfigPayload(BaseModel):
    """课程级模型供应商绑定配置。"""

    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    text_embedding_provider: str | None = None
    text_embedding_model: str | None = None
    text_embedding_dimension: int | None = None
    multimodal_embedding_provider: str | None = None
    multimodal_embedding_model: str | None = None
    multimodal_embedding_dimension: int | None = None
    rerank_provider: str | None = None
    rerank_model: str | None = None
    vlm_provider: str | None = None
    ocr_provider: str | None = None
    image_provider: str | None = None
    chat_provider: str | None = None
    cloud_rag_provider: str | None = None
    cloud_rag_provider_id: str | None = None
    remote_knowledge_base_id: str | None = None
    default_answer_mode: str | None = None
    allow_rag_fallback_to_chat: bool | None = None
    require_citation_for_course_answer: bool | None = None
    default_use_course_evidence_for_resource: bool | None = None
    ai_binding_enabled: bool | None = None
    use_global_embedding: bool | None = None
    daily_token_limit: int | None = None
    daily_cost_limit: float | None = None


class CourseModelConfigResponse(BaseModel):
    """课程级模型供应商绑定响应。"""

    model_config = ConfigDict(extra="allow")

    course_id: str
    status: str | None = None
    message: str | None = None
    chat_provider: str | None = None
    chat_provider_name: str | None = None
    chat_model: str | None = None
    image_provider: str | None = None
    image_provider_name: str | None = None
    image_model: str | None = None
    cloud_rag_provider: str | None = None
    cloud_rag_provider_id: str | None = None
    cloud_rag_provider_name: str | None = None
    remote_knowledge_base_id: str | None = None
    default_answer_mode: str | None = None
    allow_rag_fallback_to_chat: bool | None = None
    require_citation_for_course_answer: bool | None = None
    default_use_course_evidence_for_resource: bool | None = None
    ai_binding_enabled: bool | None = None
    use_global_embedding: bool | None = None
    embedding_provider: str | None = None
    embedding_provider_name: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    text_embedding_provider: str | None = None
    text_embedding_model: str | None = None
    text_embedding_dimension: int | None = None
    multimodal_embedding_provider: str | None = None
    multimodal_embedding_model: str | None = None
    multimodal_embedding_dimension: int | None = None
    rerank_provider: str | None = None
    rerank_model: str | None = None
    vlm_provider: str | None = None
    ocr_provider: str | None = None
    daily_token_limit: int | None = None
    daily_cost_limit: float | None = None


class ModelCallLogResponse(BaseModel):
    """模型调用日志列表响应。"""

    items: list[dict[str, Any]]
    summary: dict[str, Any]


class ModelCallLogClearResponse(BaseModel):
    """模型调用日志清理响应。"""

    status: str
    deleted: int


class ModelGatewayTraceDetail(BaseModel):
    """模型网关 trace 明细响应。"""

    trace_id: str
    model_calls: list[dict[str, Any]] = Field(default_factory=list)
    rag_queries: list[dict[str, Any]] = Field(default_factory=list)
    admin_audits: list[dict[str, Any]] = Field(default_factory=list)


class ModelProviderIconItem(BaseModel):
    """模型供应商图标列表项。"""

    filename: str
    url: str | None = None
    deletable: bool | None = None


class ModelProviderIconList(BaseModel):
    """模型供应商图标列表响应。"""

    items: list[ModelProviderIconItem]


class ModelProviderIconMutationResponse(BaseModel):
    """模型供应商图标写操作响应。"""

    filename: str
    url: str | None = None
    status: str | None = None


class ModelProviderMutationResponse(BaseModel):
    """模型供应商写操作通用响应。"""

    status: str
    provider: str | None = None
    display_name: str | None = None
    is_default: bool | None = None


class ModelProviderDeleteResponse(ModelProviderMutationResponse):
    """模型供应商删除响应。"""

    deleted_call_logs: int = 0
    deleted_user_overrides: int = 0
    cleared_course_bindings: int = 0


class ModelProviderReloadResponse(BaseModel):
    """模型网关重载响应。"""

    status: str
    channel: str


class ProviderHealthCheckItem(BaseModel):
    """单项供应商健康检查结果。"""

    capability: str
    status: str
    latency_ms: int = 0
    model: str | None = None
    embedding_dim: int | None = None
    message: str | None = None
    error: str | None = None


class ProviderHealthCheckResult(BaseModel):
    """单个供应商健康检查汇总。"""

    provider_id: str
    display_name: str
    status: str
    avg_latency_ms: int = 0
    last_error: str | None = None
    checks: list[ProviderHealthCheckItem] = Field(default_factory=list)


class ProviderCheckAllResponse(BaseModel):
    """批量检查所有模型供应商的响应。"""

    status: str
    checked: int
    passed: int
    failed: int
    degraded: int
    items: list[ProviderHealthCheckResult] = Field(default_factory=list)


class ProviderUsageSummary(BaseModel):
    """模型供应商用量统计摘要。"""

    total_calls: int = 0
    failed_calls: int = 0
    failure_rate: float = 0
    token_input: int = 0
    token_output: int = 0
    estimated_cost: float = 0


class ProviderUsageItem(BaseModel):
    """单个模型供应商用量统计。"""

    provider: str
    display_name: str
    total_calls: int = 0
    failed_calls: int = 0
    failure_rate: float = 0
    avg_latency_ms: int = 0
    token_input: int = 0
    token_output: int = 0
    request_count: int = 0
    estimated_cost: float = 0


class ProviderUsageTrendItem(BaseModel):
    """模型供应商按日期聚合的用量趋势。"""

    date: str
    calls: int = 0
    token_input: int = 0
    token_output: int = 0
    estimated_cost: float = 0


class ProviderUsageStatsResponse(BaseModel):
    """模型供应商用量统计响应。"""

    summary: ProviderUsageSummary
    items: list[ProviderUsageItem] = Field(default_factory=list)
    cost_trends: list[ProviderUsageTrendItem] = Field(default_factory=list)


class ModelProviderTemplateItem(BaseModel):
    """模型供应商预设模板列表项。"""

    key: str
    label: str
    payload: ModelProviderUpsert


class ModelProviderTemplateList(BaseModel):
    """模型供应商预设模板列表响应。"""

    items: list[ModelProviderTemplateItem]
