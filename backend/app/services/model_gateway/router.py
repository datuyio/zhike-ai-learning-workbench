from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.core.tracing import get_trace_id
from app.models import ModelProvider
from app.schemas.model_gateway import ModelProviderUpsert
from app.services.model_gateway.audit_service import ModelGatewayAuditService
from app.services.model_gateway.budget_service import ModelGatewayBudgetService
from app.services.model_gateway.call_recorder import ModelGatewayCallRecorder
from app.services.model_gateway.chat_invocation_service import ChatInvocationService
from app.services.model_gateway.chat_routing_service import ModelGatewayChatRoutingService
from app.services.model_gateway.course_binding_service import ModelGatewayCourseBindingService
from app.services.model_gateway.health_service import ModelGatewayHealthService
from app.services.model_gateway.log_admin_service import ModelGatewayLogAdminService
from app.services.model_gateway.log_repository import ModelGatewayLogRepository
from app.services.model_gateway.provider_admin_service import ModelGatewayProviderAdminService
from app.services.model_gateway.provider_connection_service import ModelGatewayProviderConnectionService
from app.services.model_gateway.provider_registry_service import ModelGatewayProviderRegistryService
from app.services.model_gateway.reload import publish_model_gateway_reload
from app.services.model_gateway.user_override_service import UserModelOverrideService
from app.services.model_gateway.runtime_types import ChatGenerationResult, GatewayProviderConfig


class ModelGateway:
    """基于数据库配置的模型网关，管理对话和 embedding 供应商。"""

    _ENV_KEY_CANDIDATES: dict[str, tuple[str, ...]] = {
        "deepseek": ("DEEPSEEK_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "iflytek_spark": ("IFLYTEK_SPARK_API_KEY", "SPARK_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "dashscope": ("DASHSCOPE_API_KEY", "QWEN_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "dashscope_embedding": ("DASHSCOPE_API_KEY", "QWEN_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "qwen": ("DASHSCOPE_API_KEY", "QWEN_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "zhipu_glm": ("ZHIPU_API_KEY", "GLM_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "kimi": ("KIMI_API_KEY", "MOONSHOT_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "moonshot": ("MOONSHOT_API_KEY", "KIMI_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "baichuan": ("BAICHUAN_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "volcengine": ("ARK_API_KEY", "DOUBAO_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "doubao": ("ARK_API_KEY", "DOUBAO_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "hunyuan": ("HUNYUAN_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "siliconflow": ("SILICONFLOW_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "ollama": ("OLLAMA_API_KEY",),
        "openai_image": ("OPENAI_API_KEY", "IMAGE_GENERATION_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "openai_images": ("OPENAI_API_KEY", "IMAGE_GENERATION_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "fal": ("FAL_KEY", "FAL_API_KEY", "IMAGE_GENERATION_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "fal_ai": ("FAL_KEY", "FAL_API_KEY", "IMAGE_GENERATION_API_KEY", "MODEL_GATEWAY_API_KEY"),
    }
    _provider_cache: tuple[float, list[GatewayProviderConfig]] | None = None

    def __init__(self, db: Session) -> None:
        """初始化模型网关及其预算、课程绑定、健康状态和日志仓储服务。"""
        self.db = db
        self._budget_service = ModelGatewayBudgetService(db)
        self._course_binding_service = ModelGatewayCourseBindingService(db)
        self._health_service = ModelGatewayHealthService(db)
        self._log_repository = ModelGatewayLogRepository(db)
        self._audit_service = ModelGatewayAuditService(db)
        self._log_admin_service = ModelGatewayLogAdminService(
            db,
            log_repository=self._log_repository,
            audit=self._audit_service.write,
        )
        self._provider_registry = ModelGatewayProviderRegistryService(
            db,
            env_key_candidates=self._ENV_KEY_CANDIDATES,
        )
        self._call_recorder = ModelGatewayCallRecorder(
            budget_service=self._budget_service,
            log_repository=self._log_repository,
        )
        self._chat_routing_service = ModelGatewayChatRoutingService(
            configs_for_capability=self._provider_registry.configs_for_capability,
            select_provider_config=self._provider_registry.select_provider_config,
            is_provider_unhealthy_for_routing=self._health_service.is_provider_unhealthy_for_routing,
        )
        self._provider_admin_service = ModelGatewayProviderAdminService(
            db,
            course_binding_service=self._course_binding_service,
            load_provider=self._provider_registry.provider_by_code,
            ensure_health_row=self._health_service.ensure_health_row,
            audit=self._audit_service.write,
            invalidate_provider_cache=self.invalidate_provider_cache,
            publish_reload_event=publish_model_gateway_reload,
        )
        self._provider_connection_service = ModelGatewayProviderConnectionService(
            db,
            load_provider=self._provider_registry.provider_by_code,
            load_provider_rows=self._provider_registry.provider_rows,
            to_config=self._provider_registry.to_config,
            audit=self._audit_service.write,
            log_call=self._call_recorder.record_call,
            update_provider_health=self._health_service.update_provider_health,
        )
        self._chat_invocation_service = ChatInvocationService(
            load_candidates=self._chat_routing_service.chat_provider_chain,
            env_default_config=self._provider_registry.env_default_config,
            is_config_in_cooldown=self._health_service.is_config_in_cooldown,
            load_provider=self._provider_registry.provider_by_code,
            validate_chat_config=self._chat_routing_service.validate_chat_config,
            ensure_budget_available=self._budget_service.ensure_budget_available,
            is_budget_limit_error=self._chat_routing_service.is_budget_limit_error,
            format_budget_error=self._chat_routing_service.format_budget_error,
            log_call=self._call_recorder.record_call,
            update_provider_health=self._health_service.update_provider_health,
        )

    @classmethod
    def invalidate_provider_cache(cls: type["ModelGateway"]) -> None:
        """清空模型供应商运行时缓存，确保后续请求读取最新配置。"""
        cls._provider_cache = None
        ModelGatewayProviderRegistryService.invalidate_cache()

    def list_providers(self, capability: str = "all") -> dict[str, Any]:
        """按能力类型列出模型供应商及其健康状态。"""
        return self._provider_registry.list_providers(capability)

    def health_summary(self) -> dict[str, Any]:
        """返回所有模型供应商的健康状态摘要。"""
        return self.list_providers("all")

    def trace_detail(self, trace_id: str) -> dict[str, Any]:
        """查询单个 trace 的跨日志明细。"""
        return self._log_admin_service.trace_detail(trace_id)

    async def upsert_provider(self, payload: ModelProviderUpsert, actor_external_id: str | None = None) -> dict[str, Any]:
        """创建或更新模型供应商配置，并发布网关重载通知。"""
        return await self._provider_admin_service.upsert_provider(payload, actor_external_id)

    async def set_default_provider(self, provider_code: str, actor_external_id: str | None = None) -> dict[str, Any]:
        """将指定模型供应商设为同类型默认供应商。"""
        return await self._provider_admin_service.set_default_provider(provider_code, actor_external_id)

    async def delete_provider(self, provider_code: str, actor_external_id: str | None = None) -> dict[str, Any]:
        """删除模型供应商，并清理相关调用日志、用户覆盖和课程绑定。"""
        return await self._provider_admin_service.delete_provider(provider_code, actor_external_id)

    async def publish_reload(self, actor_external_id: str | None = None) -> dict[str, Any]:
        """手动发布模型网关重载通知。"""
        return await self._provider_admin_service.publish_reload(actor_external_id)

    def call_logs(
        self,
        capability: str = "all",
        provider: str | None = None,
        status: str | None = None,
        course_id: str | None = None,
        days: int = 7,
        start_at: str | None = None,
        end_at: str | None = None,
        model_name: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """查询模型调用日志列表。"""
        return self._log_admin_service.call_logs(
            capability=capability,
            provider=provider,
            status=status,
            course_id=course_id,
            days=days,
            start_at=start_at,
            end_at=end_at,
            model_name=model_name,
            trace_id=trace_id,
            limit=limit,
        )

    async def clear_call_logs(
        self,
        *,
        capability: str = "all",
        provider: str | None = None,
        status: str | None = None,
        course_id: str | None = None,
        days: int = 7,
        start_at: str | None = None,
        end_at: str | None = None,
        model_name: str | None = None,
        trace_id: str | None = None,
        actor_external_id: str | None = None,
    ) -> dict[str, Any]:
        """清理模型调用日志，并记录管理员审计。"""
        return await self._log_admin_service.clear_call_logs(
            capability=capability,
            provider=provider,
            status=status,
            course_id=course_id,
            days=days,
            start_at=start_at,
            end_at=end_at,
            model_name=model_name,
            trace_id=trace_id,
            actor_external_id=actor_external_id,
        )

    async def test_connection(self, provider_id: str, actor_external_id: str | None = None) -> dict[str, Any]:
        """对已保存的模型供应商执行连通性测试。"""
        return await self._provider_connection_service.test_connection(provider_id, actor_external_id)

    async def test_connection_draft(self, payload: ModelProviderUpsert, actor_external_id: str | None = None) -> dict[str, Any]:
        """对尚未保存的供应商草稿配置执行连通性测试。"""
        return await self._provider_connection_service.test_connection_draft(payload, actor_external_id)

    def _provider_test_error(self, provider_id: str, exc: Exception | str) -> dict[str, Any]:
        """兼容旧私有入口，实际格式化交给供应商连接测试服务。"""
        return self._provider_connection_service.provider_test_error(provider_id, exc)

    def _format_test_result(self, provider: ModelProvider, result: dict[str, Any]) -> dict[str, Any]:
        """兼容旧私有入口，实际格式化交给供应商连接测试服务。"""
        return self._provider_connection_service.format_test_result(provider, result)

    def _draft_provider(self, payload: ModelProviderUpsert) -> ModelProvider:
        """兼容旧私有入口，实际构造交给供应商连接测试服务。"""
        return self._provider_connection_service.draft_provider(payload)

    async def check_all_providers(self, actor_external_id: str | None = None, audit: bool = True) -> dict[str, Any]:
        """批量检查所有启用供应商的健康状态。"""
        return await self._provider_connection_service.check_all_providers(actor_external_id, audit=audit)

    async def complete_chat(
        self,
        messages: Sequence[dict[str, str]],
        course_slug: str | None,
        provider_code: str | None = None,
        user_override: GatewayProviderConfig | None = None,
        agent_name: str = "Answer generation",
        temperature: float = 0.2,
        max_tokens: int = 1200,
        allow_fallback: bool = True,
        json_mode: bool = False,
    ) -> ChatGenerationResult:
        """执行一次非流式聊天模型调用，并按配置处理降级和日志记录。"""
        return await self._chat_invocation_service.complete_chat(
            messages,
            course_slug,
            provider_code=provider_code,
            user_override=user_override,
            agent_name=agent_name,
            temperature=temperature,
            max_tokens=max_tokens,
            allow_fallback=allow_fallback,
            json_mode=json_mode,
        )

    async def stream_chat(
        self,
        messages: Sequence[dict[str, str]],
        course_slug: str | None,
        provider_code: str | None = None,
        user_override: GatewayProviderConfig | None = None,
        agent_name: str = "Answer generation",
        temperature: float = 0.2,
        max_tokens: int = 1200,
        allow_fallback: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        """执行流式聊天模型调用，逐块产出模型事件并记录调用状态。"""
        async for event in self._chat_invocation_service.stream_chat(
            messages,
            course_slug,
            provider_code=provider_code,
            user_override=user_override,
            agent_name=agent_name,
            temperature=temperature,
            max_tokens=max_tokens,
            allow_fallback=allow_fallback,
        ):
            yield event

    def user_chat_override(self, user_external_id: str | None) -> GatewayProviderConfig | None:
        """读取当前用户已启用的个人模型覆盖配置。"""
        if not user_external_id:
            return None
        return UserModelOverrideService(self.db).as_gateway_config(user_external_id)

    def embedding_provider_configs(self, provider_code: str | None = None) -> list[GatewayProviderConfig]:
        """获取 embedding 能力可用的供应商配置。"""
        if provider_code:
            config = self._select_provider_config("embedding", provider_code)
            return [config] if config else []
        return self._configs_for_capability("embedding")

    def provider_configs(self, capability: str, provider_code: str | None = None) -> list[GatewayProviderConfig]:
        """按能力类型获取可用供应商配置。"""
        if provider_code:
            config = self._select_provider_config(capability, provider_code)
            return [config] if config else []
        return self._configs_for_capability(capability)

    def multimodal_embedding_provider_configs(self, provider_code: str | None = None) -> list[GatewayProviderConfig]:
        """获取多模态 embedding 能力可用的供应商配置。"""
        return self.provider_configs("multimodal_embedding", provider_code)

    def rerank_provider_configs(self, provider_code: str | None = None) -> list[GatewayProviderConfig]:
        """获取 rerank 能力可用的供应商配置。"""
        return self.provider_configs("rerank", provider_code)

    def vision_provider_configs(self, capability: str = "vlm", provider_code: str | None = None) -> list[GatewayProviderConfig]:
        """获取视觉类能力可用的供应商配置。"""
        return self.provider_configs(capability, provider_code)

    def log_embedding_call(
        self,
        *,
        config: GatewayProviderConfig,
        latency_ms: int,
        status: str,
        request_count: int,
        batch_count: int,
        embedding_dim: int | None,
        course_slug: str | None = None,
        error: str | None = None,
    ) -> None:
        """记录 embedding 调用日志，并同步供应商健康状态。"""
        self._log_call(
            course_slug=course_slug,
            config=config,
            agent_name="Embedding",
            latency_ms=latency_ms,
            status=status,
            error=error,
            capability="embedding",
            request_count=request_count,
            batch_count=batch_count,
            embedding_dim=embedding_dim,
        )
        provider = self._provider_by_code(config.provider) if config.id else None
        if provider:
            self._update_provider_health(provider, "healthy" if status == "success" else "degraded", latency_ms, error)

    def log_capability_call(
        self,
        *,
        config: GatewayProviderConfig,
        capability: str,
        agent_name: str,
        latency_ms: int,
        status: str,
        course_slug: str | None = None,
        error: str | None = None,
        request_count: int = 1,
        batch_count: int = 1,
        token_input: int = 0,
        token_output: int = 0,
        embedding_dim: int | None = None,
        meta_json: dict[str, Any] | None = None,
    ) -> None:
        """记录指定模型能力的调用日志，并同步供应商健康状态。"""
        self._log_call(
            course_slug=course_slug,
            config=config,
            agent_name=agent_name,
            latency_ms=latency_ms,
            status=status,
            error=error,
            capability=capability,
            request_count=request_count,
            batch_count=batch_count,
            token_input=token_input,
            token_output=token_output,
            embedding_dim=embedding_dim,
            meta_json=meta_json,
        )
        provider = self._provider_by_code(config.provider) if config.id else None
        if provider:
            self._update_provider_health(provider, "healthy" if status == "success" else "degraded", latency_ms, error)

    async def _run_provider_health_checks(self, provider: ModelProvider, *, persist: bool = True) -> dict[str, Any]:
        """兼容旧私有入口，实际健康检查交给供应商连接测试服务。"""
        return await self._provider_connection_service.run_provider_health_checks(provider, persist=persist)

    def _chat_provider_chain(self, provider_code: str | None = None) -> list[GatewayProviderConfig]:
        """根据显式供应商、默认优先级和回退配置生成聊天路由链。"""
        return self._chat_routing_service.chat_provider_chain(provider_code)

    def has_configured_chat_provider(self, provider_code: str | None = None) -> bool:
        """判断是否存在已配置密钥且可用于用户侧调用的 ChatProvider。"""
        return self._chat_routing_service.has_configured_chat_provider(provider_code)

    def _fallback_chain_for(self, source: GatewayProviderConfig, available: list[GatewayProviderConfig]) -> list[GatewayProviderConfig]:
        """根据来源供应商的回退列表构造可用的后备供应商链。"""
        return self._chat_routing_service.fallback_chain_for(source, available)

    def _validate_chat_config(self, config: GatewayProviderConfig) -> None:
        """校验聊天模型调用所需的协议和凭证配置。"""
        self._chat_routing_service.validate_chat_config(config)

    def resolve_course_chat_provider(self, course_slug: str | None) -> str | None:
        """解析课程绑定的聊天供应商编码。"""
        return self._course_binding_service.resolve_chat_provider(course_slug)

    def _is_budget_limit_error(self, error: str) -> bool:
        """判断模型调用异常是否由课程或供应商日额度耗尽导致。"""
        return self._chat_routing_service.is_budget_limit_error(error)

    def _format_budget_error(self, error: str) -> str:
        """把内部额度异常转换为用户可读的中文错误信息。"""
        return self._chat_routing_service.format_budget_error(error)

    def _ensure_budget_available(self, config: GatewayProviderConfig, course_slug: str | None) -> None:
        """在模型调用前校验供应商和课程维度的日额度。"""
        self._budget_service.ensure_budget_available(config, course_slug)

    def _course_daily_token_limit(self, course_slug: str | None) -> int | None:
        """查询指定课程的每日 Token 配额。"""
        return self._budget_service.course_daily_token_limit(course_slug)

    def _daily_cost_limit(self, config: GatewayProviderConfig, course_slug: str | None) -> float | None:
        """查询指定供应商和课程组合的每日费用配额。"""
        return self._budget_service.daily_cost_limit(config, course_slug)

    def _daily_token_usage(self, provider_id: Any | None = None, course_slug: str | None = None) -> int:
        """查询供应商或课程维度当天已使用的 Token 数。"""
        return self._budget_service.daily_token_usage(provider_id=provider_id, course_slug=course_slug)

    def _daily_estimated_cost(self, provider_id: Any | None = None, course_slug: str | None = None) -> float:
        """查询供应商或课程维度当天已估算的调用费用。"""
        return self._budget_service.daily_estimated_cost(provider_id=provider_id, course_slug=course_slug)

    def _estimate_call_cost(
        self,
        *,
        config: GatewayProviderConfig,
        capability: str,
        token_input: int,
        token_output: int,
        request_count: int,
    ) -> dict[str, Any]:
        """按供应商计费配置估算单次模型调用成本。"""
        return self._budget_service.estimate_call_cost(
            config=config,
            capability=capability,
            token_input=token_input,
            token_output=token_output,
            request_count=request_count,
        )

    def _is_config_in_cooldown(self, config: GatewayProviderConfig) -> bool:
        """判断供应商配置是否仍处于失败冷却窗口。"""
        return self._health_service.is_config_in_cooldown(config)

    def _is_provider_unhealthy_for_routing(self, config: GatewayProviderConfig) -> bool:
        """判断供应商是否因不健康状态需要从路由链路中跳过。"""
        return self._health_service.is_provider_unhealthy_for_routing(config)

    def _provider_rows(self, capability: str = "all", active_only: bool = True) -> list[ModelProvider]:
        """兼容旧私有入口，实际查询交给运行时供应商注册服务。"""
        return self._provider_registry.provider_rows(capability=capability, active_only=active_only)

    def _provider_by_code(self, provider_code: str) -> ModelProvider | None:
        """兼容旧私有入口，实际查询交给运行时供应商注册服务。"""
        return self._provider_registry.provider_by_code(provider_code)

    def _configs_for_capability(self, capability: str) -> list[GatewayProviderConfig]:
        """兼容旧私有入口，实际筛选交给运行时供应商注册服务。"""
        return self._provider_registry.configs_for_capability(capability)

    def _select_provider_config(self, capability: str, provider_code: str | None = None) -> GatewayProviderConfig | None:
        """兼容旧私有入口，实际选择交给运行时供应商注册服务。"""
        return self._provider_registry.select_provider_config(capability, provider_code)

    def _to_config(self, provider: ModelProvider) -> GatewayProviderConfig:
        """兼容旧私有入口，实际转换交给运行时供应商注册服务。"""
        return self._provider_registry.to_config(provider)

    def _env_default_config(self) -> GatewayProviderConfig:
        """兼容旧私有入口，实际构造交给运行时供应商注册服务。"""
        return self._provider_registry.env_default_config()

    def _api_key_source(self, provider: ModelProvider) -> tuple[str | None, str]:
        """兼容旧私有入口，实际解析交给运行时供应商注册服务。"""
        return self._provider_registry.api_key_source(provider)

    def _has_api_key(self, provider: ModelProvider) -> bool:
        """兼容旧私有入口，实际判定交给运行时供应商注册服务。"""
        return self._provider_registry.has_api_key(provider)

    def _provider_item(self, provider: ModelProvider, health: Any | None) -> dict[str, Any]:
        """兼容旧私有入口，实际格式化交给运行时供应商注册服务。"""
        return self._provider_registry.provider_item(provider, health)

    def _ensure_health_row(self, provider: ModelProvider) -> None:
        """确保供应商至少存在一条健康状态记录。"""
        self._health_service.ensure_health_row(provider)

    def _log_call(
        self,
        course_slug: str | None,
        config: GatewayProviderConfig,
        agent_name: str,
        latency_ms: int,
        status: str,
        error: str | None = None,
        *,
        capability: str,
        request_count: int = 1,
        batch_count: int = 1,
        embedding_dim: int | None = None,
        token_input: int = 0,
        token_output: int = 0,
        meta_json: dict[str, Any] | None = None,
    ) -> None:
        """兼容旧调用入口，实际写日志由日志仓储负责。"""
        self._call_recorder.record_call(
            course_slug=course_slug,
            config=config,
            agent_name=agent_name,
            latency_ms=latency_ms,
            status=status,
            error=error,
            capability=capability,
            request_count=request_count,
            batch_count=batch_count,
            embedding_dim=embedding_dim,
            token_input=token_input,
            token_output=token_output,
            meta_json=meta_json,
        )

    def _update_provider_health(self, provider: ModelProvider, status: str, latency_ms: int, error: str | None) -> None:
        """更新供应商健康状态，并在连续失败达到阈值时标记为 down。"""
        self._health_service.update_provider_health(provider, status, latency_ms, error)

    def _audit(self, actor_external_id: str | None, action: str, target_id: str, detail: dict[str, Any]) -> None:
        """写入模型网关管理员操作审计日志。"""
        self._audit_service.write(actor_external_id, action, target_id, detail)

    def usage_stats(
        self,
        days: int = 30,
        start_at: str | None = None,
        end_at: str | None = None,
        capability: str = "all",
    ) -> dict[str, Any]:
        """为用量统计看板聚合各供应商的调用数据。"""
        return self._log_admin_service.usage_stats(
            days=days,
            start_at=start_at,
            end_at=end_at,
            capability=capability,
        )

    @staticmethod
    def _audit_payload(payload: ModelProviderUpsert) -> dict[str, Any]:
        """生成审计日志使用的供应商配置摘要，并避免记录明文密钥。"""
        return ModelGatewayProviderAdminService.audit_payload(payload)

    @staticmethod
    def _safe_uuid_text(value: str) -> str:
        """把输入值安全转换为 UUID 字符串，非法值返回零 UUID。"""
        try:
            import uuid

            return str(uuid.UUID(str(value)))
        except (TypeError, ValueError):
            return "00000000-0000-0000-0000-000000000000"

    @staticmethod
    def masked_api_key_hint(provider_code: str) -> str:
        """返回供应商环境变量 API Key 的脱敏提示。"""
        return ModelGatewayProviderRegistryService.masked_api_key_hint_for_provider(
            provider_code,
            ModelGateway._ENV_KEY_CANDIDATES,
        )
