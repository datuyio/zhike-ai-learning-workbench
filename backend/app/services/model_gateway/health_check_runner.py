from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol, TypeAlias

from app.core.tracing import get_trace_id
from app.services.model_gateway import health_checks
from app.services.model_gateway.chat_client import request_chat_once
from app.services.model_gateway.embeddings_api import call_embedding_api


logger = logging.getLogger(__name__)

_HEALTH_CHECK_CHAT_USER = "hi"
_HEALTH_CHECK_CHAT_MAX_TOKENS = 1
_HEALTH_CHECK_EMBEDDING_TEXT = "hi"


class HealthCheckRuntimeConfig(Protocol):
    """健康检查执行器需要的完整运行时供应商配置字段。"""

    provider: str
    display_name: str
    provider_type: str
    protocol: str
    base_url: str
    api_key: str | None
    chat_model: str | None
    embedding_model: str | None
    vision_model: str | None
    image_model: str | None
    supports_json_mode: bool
    embedding_dimension: int | None
    meta_json: dict[str, Any] | None


LogCall: TypeAlias = Callable[..., None]
UpdateProviderHealth: TypeAlias = Callable[[str, int, str | None], None]


async def run_provider_health_checks(
    *,
    config: HealthCheckRuntimeConfig,
    provider_chat_model: str | None,
    persist: bool,
    log_call: LogCall,
    update_provider_health: UpdateProviderHealth,
) -> dict[str, Any]:
    """按供应商能力执行健康检查，并通过回调持久化日志和健康状态。

    参数:
        config: 供应商运行时配置，通常由模型网关从数据库记录转换而来。
        provider_chat_model: 数据库中的聊天模型值，用于兼容 both 类型供应商的旧规则。
        persist: 是否写入调用日志和供应商健康状态。
        log_call: 写入单项调用日志的回调；仅在 persist 为 True 时调用。
        update_provider_health: 写入供应商整体健康状态的回调；仅在 persist 为 True 时调用。

    返回:
        管理端连接测试接口使用的健康检查结果。
    """
    capabilities = health_checks.resolve_health_check_capabilities(config, provider_chat_model=provider_chat_model)

    if not capabilities:
        if persist:
            update_provider_health("unhealthy", 0, health_checks.NO_TESTABLE_CAPABILITY_ERROR)
        return health_checks.build_no_capability_health_result(config.provider, config.display_name)

    checks: list[dict[str, Any]] = []
    for capability in capabilities:
        start = time.perf_counter()
        try:
            if capability == "embedding":
                await _check_embedding_capability(
                    config=config,
                    checks=checks,
                    log_call=log_call,
                    persist=persist,
                    start=start,
                )
                continue
            if capability in {"vision", "rerank", "image_generation"}:
                _check_lightweight_capability(
                    config=config,
                    capability=capability,
                    checks=checks,
                    log_call=log_call,
                    persist=persist,
                    start=start,
                )
                continue
            await _check_chat_capability(
                config=config,
                checks=checks,
                log_call=log_call,
                persist=persist,
                start=start,
            )
        except Exception as exc:  # pragma: no cover - 真实供应商返回细节会随环境变化。
            logger.warning(
                "模型网关健康检查能力失败：provider=%s capability=%s model=%s trace_id=%s",
                config.provider,
                capability,
                health_checks.health_check_model_name(config, capability),
                get_trace_id(),
                exc_info=True,
            )
            _record_failed_capability_check(
                config=config,
                capability=capability,
                error=str(exc),
                checks=checks,
                log_call=log_call,
                persist=persist,
                start=start,
            )

    summary = health_checks.summarize_health_checks(checks)
    if persist:
        update_provider_health(summary.health_status, summary.avg_latency_ms, summary.last_error)
    return health_checks.build_provider_health_result(
        provider_id=config.provider,
        display_name=config.display_name,
        checks=checks,
        summary=summary,
    )


async def _check_embedding_capability(
    *,
    config: HealthCheckRuntimeConfig,
    checks: list[dict[str, Any]],
    log_call: LogCall,
    persist: bool,
    start: float,
) -> None:
    """执行 embedding 真实连通性检查，并记录成功结果。"""
    if not config.api_key and config.provider != "ollama":
        raise RuntimeError("缺少 API Key")
    vectors = await call_embedding_api(
        protocol=config.protocol,
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.embedding_model or "",
        texts=[_HEALTH_CHECK_EMBEDDING_TEXT],
        provider_meta=config.meta_json,
    )
    actual_dim = len(vectors[0]) if vectors else 0
    expected_dim = config.embedding_dimension
    if expected_dim and actual_dim != expected_dim:
        raise RuntimeError(f"embedding dimension mismatch: expected {expected_dim}, got {actual_dim}")
    latency_ms = int((time.perf_counter() - start) * 1000)
    if persist:
        log_call(
            course_slug=None,
            config=config,
            agent_name="Embedding connection test",
            latency_ms=latency_ms,
            status="success",
            capability="embedding",
            request_count=1,
            batch_count=1,
            embedding_dim=actual_dim,
            meta_json={"health_check": True},
        )
    checks.append(
        health_checks.build_passed_health_check(
            "embedding",
            latency_ms=latency_ms,
            model=config.embedding_model,
            embedding_dim=actual_dim,
            message="Embedding 连接测试通过。",
        )
    )


def _check_lightweight_capability(
    *,
    config: HealthCheckRuntimeConfig,
    capability: str,
    checks: list[dict[str, Any]],
    log_call: LogCall,
    persist: bool,
    start: float,
) -> None:
    """执行无需远程推理的轻量能力检查，并记录成功结果。"""
    if capability == "image_generation":
        if not config.api_key:
            raise RuntimeError("缺少 API Key")
        if not config.image_model:
            raise RuntimeError("缺少图片生成模型")
    latency_ms = int((time.perf_counter() - start) * 1000)
    if persist:
        log_call(
            course_slug=None,
            config=config,
            agent_name=health_checks.health_check_success_agent_name(capability),
            latency_ms=latency_ms,
            status="success",
            capability=capability,
            request_count=1,
            batch_count=1,
            meta_json={"health_check": True, "lightweight": True},
        )
    checks.append(
        health_checks.build_passed_health_check(
            capability,
            latency_ms=latency_ms,
            model=health_checks.health_check_model_name(config, capability),
            message=health_checks.lightweight_health_check_message(capability),
        )
    )


async def _check_chat_capability(
    *,
    config: HealthCheckRuntimeConfig,
    checks: list[dict[str, Any]],
    log_call: LogCall,
    persist: bool,
    start: float,
) -> None:
    """执行聊天模型真实连通性检查，并记录成功结果。"""
    if config.protocol != "openai_compatible":
        raise RuntimeError(f"不支持的协议：{config.protocol}")
    if not config.chat_model:
        raise RuntimeError("缺少 Chat 模型")
    if not config.api_key and config.provider != "ollama":
        raise RuntimeError("缺少 API Key")
    answer, usage = await request_chat_once(
        config=config,
        messages=[{"role": "user", "content": _HEALTH_CHECK_CHAT_USER}],
        temperature=0.1,
        max_tokens=_HEALTH_CHECK_CHAT_MAX_TOKENS,
        json_mode=False,
        stream=False,
    )
    latency_ms = int((time.perf_counter() - start) * 1000)
    if persist:
        log_call(
            course_slug=None,
            config=config,
            agent_name="Model gateway health check",
            latency_ms=latency_ms,
            status="success",
            capability="chat",
            token_input=usage.get("token_input", 0),
            token_output=usage.get("token_output", 0),
            meta_json={"health_check": True},
        )
    checks.append(
        health_checks.build_passed_health_check(
            "chat",
            latency_ms=latency_ms,
            model=config.chat_model,
            message=answer[:120],
        )
    )


def _record_failed_capability_check(
    *,
    config: HealthCheckRuntimeConfig,
    capability: str,
    error: str,
    checks: list[dict[str, Any]],
    log_call: LogCall,
    persist: bool,
    start: float,
) -> None:
    """记录单项健康检查失败结果。"""
    latency_ms = int((time.perf_counter() - start) * 1000)
    if persist:
        log_call(
            course_slug=None,
            config=config,
            agent_name=health_checks.health_check_failure_agent_name(capability),
            latency_ms=latency_ms,
            status="failed",
            error=error,
            capability=capability,
            request_count=1,
            batch_count=1,
            embedding_dim=config.embedding_dimension if capability == "embedding" else None,
            meta_json={"health_check": True},
        )
    checks.append(
        health_checks.build_failed_health_check(
            capability,
            latency_ms=latency_ms,
            model=health_checks.health_check_model_name(config, capability),
            embedding_dim=config.embedding_dimension if capability == "embedding" else None,
            error=error,
        )
    )
