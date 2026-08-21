from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

from app.core.tracing import get_trace_id
from app.services.model_gateway.chat_client import ChatProviderError, request_chat_once, stream_chat_deltas
from app.services.model_gateway.chat_fallback import build_local_chat_fallback_result, chunk_text
from app.services.model_gateway.errors import ChatProviderConfigError, ModelGatewayBudgetLimitError
from app.services.model_gateway.chat_route_plan import build_chat_attempt_meta, build_chat_route_plan
from app.services.model_gateway.runtime_types import ChatGenerationResult, GatewayProviderConfig


logger = logging.getLogger(__name__)

ProviderCandidateLoader = Callable[[str | None], list[GatewayProviderConfig]]
EnvDefaultConfigFactory = Callable[[], GatewayProviderConfig]
CooldownChecker = Callable[[GatewayProviderConfig], bool]
ProviderLoader = Callable[[str], Any | None]
ChatConfigValidator = Callable[[GatewayProviderConfig], None]
BudgetChecker = Callable[[GatewayProviderConfig, str | None], None]
BudgetErrorChecker = Callable[[str], bool]
BudgetErrorFormatter = Callable[[str], str]
ProviderHealthUpdater = Callable[[Any, str, int, str | None], None]
ChatCallLogger = Callable[..., None]


class ChatInvocationService:
    """负责聊天模型调用、回退、日志和健康状态更新的执行编排。"""

    def __init__(
        self,
        *,
        load_candidates: ProviderCandidateLoader,
        env_default_config: EnvDefaultConfigFactory,
        is_config_in_cooldown: CooldownChecker,
        load_provider: ProviderLoader,
        validate_chat_config: ChatConfigValidator,
        ensure_budget_available: BudgetChecker,
        is_budget_limit_error: BudgetErrorChecker,
        format_budget_error: BudgetErrorFormatter,
        log_call: ChatCallLogger,
        update_provider_health: ProviderHealthUpdater,
    ) -> None:
        """注入网关门面提供的供应商、预算、日志和健康状态边界能力。"""

        self._load_candidates = load_candidates
        self._env_default_config = env_default_config
        self._is_config_in_cooldown = is_config_in_cooldown
        self._load_provider = load_provider
        self._validate_chat_config = validate_chat_config
        self._ensure_budget_available = ensure_budget_available
        self._is_budget_limit_error = is_budget_limit_error
        self._format_budget_error = format_budget_error
        self._log_call = log_call
        self._update_provider_health = update_provider_health

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

        route_plan = self._build_route_plan(provider_code, allow_fallback=allow_fallback, user_override=user_override)
        failed_attempts: list[dict[str, str]] = []
        skipped_attempts: list[dict[str, str]] = []
        overall_start = time.perf_counter()

        for index, config in enumerate(route_plan.candidates):
            if self._is_config_in_cooldown(config):
                skipped_attempts.append({"provider": config.provider, "reason": "cooldown"})
                continue

            provider = self._provider_for_config(config)
            start = time.perf_counter()
            try:
                self._validate_chat_config(config)
                self._ensure_budget_available(config, course_slug)
            except (ChatProviderConfigError, ModelGatewayBudgetLimitError) as exc:
                logger.warning(
                    "模型网关 Chat 候选供应商不可用：provider=%s course_slug=%s agent=%s attempt=%s fallback_to_next=%s trace_id=%s",
                    config.provider,
                    course_slug,
                    agent_name,
                    index + 1,
                    allow_fallback,
                    get_trace_id(),
                    exc_info=True,
                )
                self._handle_attempt_error(
                    exc,
                    config=config,
                    provider=provider,
                    course_slug=course_slug,
                    agent_name=agent_name,
                    attempt_index=index + 1,
                    allow_fallback=allow_fallback,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                    failed_attempts=failed_attempts,
                )
                continue

            try:
                answer, usage = await request_chat_once(
                    config=config,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    stream=False,
                )
            except ChatProviderError as exc:
                logger.warning(
                    "模型网关 Chat 调用失败：provider=%s course_slug=%s agent=%s attempt=%s fallback_to_next=%s trace_id=%s",
                    config.provider,
                    course_slug,
                    agent_name,
                    index + 1,
                    allow_fallback,
                    get_trace_id(),
                    exc_info=True,
                )
                self._handle_attempt_error(
                    exc,
                    config=config,
                    provider=provider,
                    course_slug=course_slug,
                    agent_name=agent_name,
                    attempt_index=index + 1,
                    allow_fallback=allow_fallback,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                    failed_attempts=failed_attempts,
                )
                continue

            latency_ms = int((time.perf_counter() - start) * 1000)
            self._record_success(
                course_slug=course_slug,
                config=config,
                provider=provider,
                agent_name=agent_name,
                latency_ms=latency_ms,
                token_input=usage.get("token_input", 0),
                token_output=usage.get("token_output", 0),
                meta_json=build_chat_attempt_meta(
                    attempt_index=index + 1,
                    failed_attempts=failed_attempts,
                    skipped_attempts=skipped_attempts,
                ),
            )
            return ChatGenerationResult(
                answer,
                config.provider,
                config.display_name,
                config.chat_model,
                "success",
                latency_ms,
                trace_id=get_trace_id(),
            )

        return self._local_chat_fallback_result(
            messages=messages,
            config=route_plan.fallback_base,
            course_slug=course_slug,
            agent_name=agent_name,
            latency_ms=int((time.perf_counter() - overall_start) * 1000),
            failed_attempts=failed_attempts,
            skipped_attempts=skipped_attempts,
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

        route_plan = self._build_route_plan(provider_code, allow_fallback=allow_fallback, user_override=user_override)
        failed_attempts: list[dict[str, str]] = []
        skipped_attempts: list[dict[str, str]] = []
        overall_start = time.perf_counter()

        for index, config in enumerate(route_plan.candidates):
            if self._is_config_in_cooldown(config):
                skipped_attempts.append({"provider": config.provider, "reason": "cooldown"})
                continue

            provider = self._provider_for_config(config)
            start = time.perf_counter()
            yield {
                "type": "model_start",
                "provider": config.provider,
                "display_name": config.display_name,
                "model": config.chat_model,
                "key_source": config.key_source,
            }

            try:
                self._validate_chat_config(config)
                self._ensure_budget_available(config, course_slug)
            except (ChatProviderConfigError, ModelGatewayBudgetLimitError) as exc:
                logger.warning(
                    "模型网关流式 Chat 候选供应商不可用：provider=%s course_slug=%s agent=%s attempt=%s fallback_to_next=%s trace_id=%s",
                    config.provider,
                    course_slug,
                    agent_name,
                    index + 1,
                    allow_fallback,
                    get_trace_id(),
                    exc_info=True,
                )
                self._handle_attempt_error(
                    exc,
                    config=config,
                    provider=provider,
                    course_slug=course_slug,
                    agent_name=agent_name,
                    attempt_index=index + 1,
                    allow_fallback=allow_fallback,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                    failed_attempts=failed_attempts,
                    stream_mode="sse" if config.supports_stream else "chunked_non_stream",
                )
                continue

            if not config.supports_stream:
                try:
                    async for event in self._stream_non_streaming_chat(
                        config=config,
                        provider=provider,
                        messages=messages,
                        course_slug=course_slug,
                        agent_name=agent_name,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        start=start,
                        attempt_index=index + 1,
                        failed_attempts=failed_attempts,
                        skipped_attempts=skipped_attempts,
                    ):
                        yield event
                except ChatProviderError as exc:
                    logger.warning(
                        "模型网关流式 Chat 调用失败：provider=%s course_slug=%s agent=%s attempt=%s fallback_to_next=%s trace_id=%s",
                        config.provider,
                        course_slug,
                        agent_name,
                        index + 1,
                        allow_fallback,
                        get_trace_id(),
                        exc_info=True,
                    )
                    self._handle_attempt_error(
                        exc,
                        config=config,
                        provider=provider,
                        course_slug=course_slug,
                        agent_name=agent_name,
                        attempt_index=index + 1,
                        allow_fallback=allow_fallback,
                        latency_ms=int((time.perf_counter() - start) * 1000),
                        failed_attempts=failed_attempts,
                        stream_mode="chunked_non_stream",
                    )
                    continue
                return

            try:
                async for event in self._stream_sse_chat(
                    config=config,
                    provider=provider,
                    messages=messages,
                    course_slug=course_slug,
                    agent_name=agent_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    start=start,
                    attempt_index=index + 1,
                    failed_attempts=failed_attempts,
                    skipped_attempts=skipped_attempts,
                ):
                    yield event
            except ChatProviderError as exc:
                logger.warning(
                    "模型网关流式 Chat 调用失败：provider=%s course_slug=%s agent=%s attempt=%s fallback_to_next=%s trace_id=%s",
                    config.provider,
                    course_slug,
                    agent_name,
                    index + 1,
                    allow_fallback,
                    get_trace_id(),
                    exc_info=True,
                )
                self._handle_attempt_error(
                    exc,
                    config=config,
                    provider=provider,
                    course_slug=course_slug,
                    agent_name=agent_name,
                    attempt_index=index + 1,
                    allow_fallback=allow_fallback,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                    failed_attempts=failed_attempts,
                    stream_mode="sse",
                )
                continue
            return

        result = self._local_chat_fallback_result(
            messages=messages,
            config=route_plan.fallback_base,
            course_slug=course_slug,
            agent_name=agent_name,
            latency_ms=int((time.perf_counter() - overall_start) * 1000),
            failed_attempts=failed_attempts,
            skipped_attempts=skipped_attempts,
        )
        for chunk in chunk_text(result.answer):
            yield {"type": "text_delta", "delta": chunk}
            await asyncio.sleep(0)
        yield self._model_done_event(result)

    def _build_route_plan(
        self,
        provider_code: str | None,
        *,
        allow_fallback: bool,
        user_override: GatewayProviderConfig | None = None,
    ) -> Any:
        """生成当前聊天请求的供应商候选计划。"""

        candidates = self._load_candidates(provider_code)
        if user_override is not None:
            candidates = [user_override, *candidates]
        return build_chat_route_plan(
            candidates,
            env_default_config=self._env_default_config,
            allow_fallback=allow_fallback,
        )

    def _provider_for_config(self, config: GatewayProviderConfig) -> Any | None:
        """按配置中的数据库 ID 判断是否需要加载可持久化健康状态的供应商。"""

        return self._load_provider(config.provider) if config.id else None

    def _record_success(
        self,
        *,
        course_slug: str | None,
        config: GatewayProviderConfig,
        provider: Any | None,
        agent_name: str,
        latency_ms: int,
        token_input: int = 0,
        token_output: int = 0,
        meta_json: dict[str, Any] | None = None,
    ) -> None:
        """记录成功聊天调用，并同步供应商健康状态。"""

        self._log_call(
            course_slug=course_slug,
            config=config,
            agent_name=agent_name,
            latency_ms=latency_ms,
            status="success",
            capability="chat",
            token_input=token_input,
            token_output=token_output,
            meta_json=meta_json,
        )
        if provider:
            self._update_provider_health(provider, "healthy", latency_ms, None)

    def _handle_attempt_error(
        self,
        exc: Exception,
        *,
        config: GatewayProviderConfig,
        provider: Any | None,
        course_slug: str | None,
        agent_name: str,
        attempt_index: int,
        allow_fallback: bool,
        latency_ms: int,
        failed_attempts: list[dict[str, str]],
        stream_mode: str | None = None,
    ) -> None:
        """处理单个候选供应商失败，记录日志并按需终止回退链。"""

        error = str(exc)
        if isinstance(exc, ModelGatewayBudgetLimitError) or self._is_budget_limit_error(error):
            raise ModelGatewayBudgetLimitError(self._format_budget_error(error)) from exc
        failed_attempts.append({"provider": config.provider, "error": error[:300]})
        self._log_call(
            course_slug=course_slug,
            config=config,
            agent_name=agent_name,
            latency_ms=latency_ms,
            status="failed",
            error=error,
            capability="chat",
            meta_json=build_chat_attempt_meta(
                attempt_index=attempt_index,
                fallback_to_next=allow_fallback,
                stream_mode=stream_mode,
            ),
        )
        if provider:
            self._update_provider_health(provider, "degraded", latency_ms, error)
        if not allow_fallback:
            raise RuntimeError(error) from exc

    async def _stream_non_streaming_chat(
        self,
        *,
        config: GatewayProviderConfig,
        provider: Any | None,
        messages: Sequence[dict[str, str]],
        course_slug: str | None,
        agent_name: str,
        temperature: float,
        max_tokens: int,
        start: float,
        attempt_index: int,
        failed_attempts: list[dict[str, str]],
        skipped_attempts: list[dict[str, str]],
    ) -> AsyncIterator[dict[str, Any]]:
        """把非流式供应商响应拆成文本增量，复用前端流式协议。"""

        answer, usage = await request_chat_once(
            config=config,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=False,
            stream=False,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        self._record_success(
            course_slug=course_slug,
            config=config,
            provider=provider,
            agent_name=agent_name,
            latency_ms=latency_ms,
            token_input=usage.get("token_input", 0),
            token_output=usage.get("token_output", 0),
            meta_json=build_chat_attempt_meta(
                attempt_index=attempt_index,
                failed_attempts=failed_attempts,
                skipped_attempts=skipped_attempts,
                stream_mode="chunked_non_stream",
            ),
        )
        result = ChatGenerationResult(
            answer,
            config.provider,
            config.display_name,
            config.chat_model,
            "success",
            latency_ms,
            trace_id=get_trace_id(),
        )
        for chunk in chunk_text(result.answer):
            yield {"type": "text_delta", "delta": chunk}
            await asyncio.sleep(0)
        yield self._model_done_event(result)

    async def _stream_sse_chat(
        self,
        *,
        config: GatewayProviderConfig,
        provider: Any | None,
        messages: Sequence[dict[str, str]],
        course_slug: str | None,
        agent_name: str,
        temperature: float,
        max_tokens: int,
        start: float,
        attempt_index: int,
        failed_attempts: list[dict[str, str]],
        skipped_attempts: list[dict[str, str]],
    ) -> AsyncIterator[dict[str, Any]]:
        """调用支持 SSE 的供应商并逐块产出模型增量。"""

        collected: list[str] = []
        async for delta in stream_chat_deltas(
            config=config,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            collected.append(delta)
            yield {"type": "text_delta", "delta": delta}
        latency_ms = int((time.perf_counter() - start) * 1000)
        answer = "".join(collected)
        self._record_success(
            course_slug=course_slug,
            config=config,
            provider=provider,
            agent_name=agent_name,
            latency_ms=latency_ms,
            meta_json=build_chat_attempt_meta(
                attempt_index=attempt_index,
                failed_attempts=failed_attempts,
                skipped_attempts=skipped_attempts,
                stream_mode="sse",
            ),
        )
        yield {
            "type": "model_done",
            "answer": answer,
            "provider": config.provider,
            "display_name": config.display_name,
            "model": config.chat_model,
            "status": "success",
            "latency_ms": latency_ms,
            "is_fallback": False,
            "error": None,
            "trace_id": get_trace_id(),
        }

    def _local_chat_fallback_result(
        self,
        *,
        messages: Sequence[dict[str, str]],
        config: GatewayProviderConfig,
        course_slug: str | None,
        agent_name: str,
        latency_ms: int,
        failed_attempts: list[dict[str, str]],
        skipped_attempts: list[dict[str, str]],
    ) -> ChatGenerationResult:
        """在所有远端候选失败或跳过后生成本地降级聊天结果。"""

        error = failed_attempts[-1]["error"] if failed_attempts else "all providers skipped by cooldown"
        self._log_call(
            course_slug=course_slug,
            config=config,
            agent_name=agent_name,
            latency_ms=latency_ms,
            status="fallback",
            error=error,
            capability="chat",
            meta_json={"failed_providers": failed_attempts, "skipped_providers": skipped_attempts},
        )
        return build_local_chat_fallback_result(messages=messages, config=config, latency_ms=latency_ms, error=error)

    @staticmethod
    def _model_done_event(result: ChatGenerationResult) -> dict[str, Any]:
        """把 slots dataclass 结果显式转换为前端流式完成事件。"""

        return {
            "type": "model_done",
            "answer": result.answer,
            "provider": result.provider,
            "display_name": result.display_name,
            "model": result.model,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "is_fallback": result.is_fallback,
            "error": result.error,
            "trace_id": result.trace_id,
        }
