from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class GatewayProviderConfig:
    """模型供应商运行时配置快照，包含调用、限流、回退和密钥来源信息。"""

    id: Any | None
    provider: str
    display_name: str
    provider_type: str
    base_url: str
    api_key: str | None
    key_source: str
    protocol: str
    chat_model: str
    embedding_model: str | None
    vision_model: str | None
    image_model: str | None
    embedding_dimension: int | None
    max_batch_size: int
    rate_limit_rps: int | None
    supports_stream: bool
    supports_json_mode: bool
    priority: int
    is_active: bool
    is_default: bool
    daily_limit: int | None = None
    cost_config: dict[str, Any] | None = None
    fallback_providers: tuple[str, ...] = ()
    fallback_mode: str = "ordered"
    skip_unhealthy: bool = True
    meta_json: dict[str, Any] | None = None


@dataclass(slots=True)
class ChatGenerationResult:
    """聊天模型调用结果，供普通响应和流式完成事件复用。"""

    answer: str
    provider: str
    display_name: str
    model: str
    status: str
    latency_ms: int
    is_fallback: bool = False
    error: str | None = None
    trace_id: str | None = None
    # 工具调用（function calling）结果：模型请求调用工具时返回的原始 tool_calls 列表；
    # 普通对话无工具调用时为空列表。
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
