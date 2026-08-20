from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.core.security import encrypt_secret
from app.core.tracing import get_trace_id
from app.models import ModelProvider
from app.schemas.model_gateway import ModelProviderUpsert
from app.services.model_gateway.health_check_runner import run_provider_health_checks
from app.services.model_gateway.iflytek_compat import normalize_iflytek_spark_provider
from app.services.model_gateway.provider_config import provider_values_from_payload
from app.services.model_gateway.runtime_types import GatewayProviderConfig


logger = logging.getLogger(__name__)


class AuditWriter(Protocol):
    """模型网关管理操作审计写入回调。"""

    def __call__(
        self,
        actor_external_id: str | None,
        action: str,
        target: str,
        detail: dict[str, Any],
    ) -> None:
        """写入一条审计记录。"""


ProviderLoader = Callable[[str], ModelProvider | None]
ProviderRowsLoader = Callable[[str, bool], list[ModelProvider]]
ProviderConfigFactory = Callable[[ModelProvider], GatewayProviderConfig]
ProviderHealthUpdater = Callable[[ModelProvider, str, int | None, str | None], None]
ModelCallLogger = Callable[..., None]


class ModelGatewayProviderConnectionService:
    """封装模型供应商连接测试、草稿测试和批量健康检查门面。"""

    def __init__(
        self,
        db: Session,
        *,
        load_provider: ProviderLoader,
        load_provider_rows: ProviderRowsLoader,
        to_config: ProviderConfigFactory,
        audit: AuditWriter,
        log_call: ModelCallLogger,
        update_provider_health: ProviderHealthUpdater,
    ) -> None:
        """初始化供应商连接测试服务。

        参数:
            db: 当前请求范围内的数据库会话。
            load_provider: 按供应商编码读取数据库记录的回调。
            load_provider_rows: 按能力读取供应商列表的回调。
            to_config: 将供应商记录转换为运行时配置的回调。
            audit: 管理操作审计写入回调。
            log_call: 模型调用日志写入回调。
            update_provider_health: 供应商健康状态更新回调。
        """

        self.db = db
        self._load_provider = load_provider
        self._load_provider_rows = load_provider_rows
        self._to_config = to_config
        self._audit = audit
        self._log_call = log_call
        self._update_provider_health = update_provider_health

    async def test_connection(self, provider_id: str, actor_external_id: str | None = None) -> dict[str, Any]:
        """对已保存的模型供应商执行连通性测试。"""

        try:
            provider = self._load_provider(provider_id)
            if not provider:
                return self.provider_test_error(provider_id, "供应商不存在或未保存")

            result = await self.run_provider_health_checks(provider, persist=True)
            self._audit(
                actor_external_id,
                "model_provider.test",
                provider.provider,
                {"status": result["status"], "capabilities": [item["capability"] for item in result["checks"]]},
            )
            self.db.commit()
            return self.format_test_result(provider, result)
        except Exception as exc:  # pragma: no cover - 异常会转换为管理端连接测试结果。
            self.db.rollback()
            logger.warning(
                "模型供应商连接测试失败：provider_id=%s actor=%s trace_id=%s",
                provider_id,
                actor_external_id,
                get_trace_id(),
                exc_info=True,
            )
            return self.provider_test_error(provider_id, exc)

    async def test_connection_draft(
        self,
        payload: ModelProviderUpsert,
        actor_external_id: str | None = None,
    ) -> dict[str, Any]:
        """对尚未保存的供应商草稿配置执行连通性测试。"""

        provider_code = (payload.provider or "").strip() or "draft"
        try:
            provider = self.draft_provider(payload)
            result = await self.run_provider_health_checks(provider, persist=False)
            self._audit(
                actor_external_id,
                "model_provider.test_draft",
                provider.provider,
                {"status": result["status"], "capabilities": [item["capability"] for item in result["checks"]], "draft": True},
            )
            return self.format_test_result(provider, result)
        except Exception as exc:  # pragma: no cover - 异常会转换为管理端连接测试结果。
            logger.warning(
                "模型供应商草稿连接测试失败：provider_id=%s actor=%s trace_id=%s",
                provider_code,
                actor_external_id,
                get_trace_id(),
                exc_info=True,
            )
            return self.provider_test_error(provider_code, exc)

    async def check_all_providers(self, actor_external_id: str | None = None, audit: bool = True) -> dict[str, Any]:
        """批量检查所有启用供应商的健康状态。"""

        providers = self._load_provider_rows("all", True)
        items = []
        for provider in providers:
            items.append(await self.run_provider_health_checks(provider))
        passed = sum(1 for item in items if item["status"] == "passed")
        failed = sum(1 for item in items if item["status"] in {"failed", "unhealthy"})
        degraded = sum(1 for item in items if item["status"] == "degraded")
        if audit:
            self._audit(
                actor_external_id,
                "model_provider.check_all",
                "model_gateway",
                {"checked": len(items), "passed": passed, "failed": failed, "degraded": degraded, "trace_id": get_trace_id()},
            )
        self.db.commit()
        return {
            "status": "completed",
            "checked": len(items),
            "passed": passed,
            "failed": failed,
            "degraded": degraded,
            "items": items,
        }

    async def run_provider_health_checks(self, provider: ModelProvider, *, persist: bool = True) -> dict[str, Any]:
        """按供应商能力执行健康检查，并按需持久化调用日志和健康状态。"""

        config = self._to_config(provider)
        return await run_provider_health_checks(
            config=config,
            provider_chat_model=provider.chat_model,
            persist=persist,
            log_call=self._log_call,
            update_provider_health=lambda status, latency_ms, error: self._update_provider_health(
                provider,
                status,
                latency_ms,
                error,
            ),
        )

    @staticmethod
    def provider_test_error(provider_id: str, exc: Exception | str) -> dict[str, Any]:
        """把供应商连接测试异常转换为管理端可展示的失败结果。"""

        message = str(exc).strip() or "连接测试失败"
        code = (provider_id or "").strip() or "draft"
        return {
            "provider_id": code,
            "status": "failed",
            "chat_stream": False,
            "embedding": False,
            "image_generation": False,
            "json_mode": False,
            "latency_ms": None,
            "model": None,
            "embedding_dim": None,
            "message": message,
            "error": message,
        }

    @staticmethod
    def format_test_result(provider: ModelProvider, result: dict[str, Any]) -> dict[str, Any]:
        """将健康检查结果格式化为连接测试接口的响应结构。"""

        primary = result["checks"][0] if result["checks"] else {}
        last_error = result.get("last_error") or primary.get("error")
        return {
            "provider_id": provider.provider,
            "chat_stream": provider.supports_stream,
            "embedding": any(item.get("capability") == "embedding" and item.get("status") == "passed" for item in result["checks"]),
            "image_generation": any(item.get("capability") == "image_generation" and item.get("status") == "passed" for item in result["checks"]),
            "json_mode": provider.supports_json_mode,
            "status": result["status"],
            "latency_ms": result["avg_latency_ms"],
            "model": primary.get("model") or (provider.meta_json or {}).get("image_model") or provider.embedding_model or provider.chat_model,
            "embedding_dim": primary.get("embedding_dim") or provider.embedding_dimension,
            "message": last_error,
            "error": last_error,
        }

    def draft_provider(self, payload: ModelProviderUpsert) -> ModelProvider:
        """用未保存的表单 payload 构造临时供应商对象用于连接测试。"""

        existing = self._load_provider(payload.provider)
        values = provider_values_from_payload(payload)
        provider = ModelProvider(provider=payload.provider, display_name=payload.display_name)
        for field, value in values.items():
            setattr(provider, field, value)
        normalize_iflytek_spark_provider(provider)
        if existing:
            provider.id = existing.id
        if payload.clear_api_key:
            provider.api_key_encrypted = None
        elif payload.api_key:
            provider.api_key_encrypted = encrypt_secret(payload.api_key.strip())
        elif existing and existing.api_key_encrypted:
            provider.api_key_encrypted = existing.api_key_encrypted
        else:
            provider.api_key_encrypted = None
        return provider
