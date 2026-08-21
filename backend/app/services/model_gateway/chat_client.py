from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.services.model_gateway.chat_response_parser import extract_chat_answer, extract_sse_delta
from app.services.model_gateway.http_client import model_gateway_client_kwargs


class ChatProviderError(RuntimeError):
    """聊天供应商请求、协议或响应解析失败。"""


class ChatProviderConfigLike(Protocol):
    """聊天模型 HTTP 调用需要的供应商运行时配置字段。"""

    base_url: str
    api_key: str | None
    chat_model: str
    supports_json_mode: bool


def chat_completions_url(base_url: str) -> str:
    """把供应商 Base URL 规范化为聊天补全接口地址。"""
    root = base_url.rstrip("/")
    if root.endswith("/chat/completions"):
        return root
    return f"{root}/chat/completions"


def bearer_auth_header(api_key: str) -> str:
    """生成 Bearer 鉴权头，兼容已粘贴完整 Bearer Token 的情况。"""
    token = api_key.strip()
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"


def build_chat_request_payload(
    *,
    config: ChatProviderConfigLike,
    messages: Sequence[dict[str, str]],
    temperature: float,
    max_tokens: int,
    json_mode: bool,
    stream: bool,
) -> dict[str, Any]:
    """构造 OpenAI 兼容聊天请求体，集中维护模型调用协议字段。"""
    payload: dict[str, Any] = {
        "model": config.chat_model,
        "messages": list(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if json_mode and config.supports_json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


def chat_request_headers(config: ChatProviderConfigLike) -> dict[str, str]:
    """构造聊天请求头，缺少 API Key 时只保留 JSON 内容类型。"""
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = bearer_auth_header(config.api_key)
    return headers


def parse_chat_usage_tokens(usage: Any) -> dict[str, int]:
    """解析供应商 usage 字段中的输入和输出 token 数。

    参数:
        usage: 供应商响应中的 usage 对象；缺失时调用方应传入空字典。

    返回:
        规范化后的 token_input 和 token_output。

    异常:
        ChatProviderError: usage 不是对象或 token 字段无法转换为整数。
    """
    if not isinstance(usage, dict):
        raise ChatProviderError("聊天供应商 usage 字段不是对象")
    try:
        return {
            "token_input": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
            "token_output": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        }
    except (TypeError, ValueError) as exc:
        raise ChatProviderError("聊天供应商 usage token 字段无法解析") from exc


async def request_chat_once(
    *,
    config: ChatProviderConfigLike,
    messages: Sequence[dict[str, str]],
    temperature: float,
    max_tokens: int,
    json_mode: bool,
    stream: bool,
) -> tuple[str, dict[str, int]]:
    """向兼容 OpenAI 协议的聊天接口发起一次请求并返回答案和用量。"""
    payload = build_chat_request_payload(
        config=config,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
        stream=stream,
    )
    try:
        async with httpx.AsyncClient(**model_gateway_client_kwargs(config.base_url, settings.MODEL_GATEWAY_TIMEOUT_SECONDS)) as client:
            response = await client.post(chat_completions_url(config.base_url), headers=chat_request_headers(config), json=payload)
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError as exc:
                raise ChatProviderError("聊天供应商返回的 JSON 无法解析") from exc
    except httpx.ConnectError as exc:
        raise ChatProviderError(
            "聊天供应商连接失败：无法建立网络连接。请检查 Base URL、本机代理或防火墙配置。"
        ) from exc
    except httpx.HTTPError as exc:
        raise ChatProviderError(f"聊天供应商 HTTP 调用失败：{exc}") from exc
    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    return extract_chat_answer(data), parse_chat_usage_tokens(usage)


async def stream_chat_deltas(
    *,
    config: ChatProviderConfigLike,
    messages: Sequence[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[str]:
    """发起流式聊天请求，并逐条产出 SSE 文本增量。"""
    payload = build_chat_request_payload(
        config=config,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=False,
        stream=True,
    )
    try:
        async with httpx.AsyncClient(**model_gateway_client_kwargs(config.base_url, settings.MODEL_GATEWAY_TIMEOUT_SECONDS)) as client:
            async with client.stream("POST", chat_completions_url(config.base_url), headers=chat_request_headers(config), json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    delta = extract_sse_delta(line)
                    if delta:
                        yield delta
    except httpx.ConnectError as exc:
        raise ChatProviderError(
            "聊天供应商连接失败：无法建立网络连接。请检查 Base URL、本机代理或防火墙配置。"
        ) from exc
    except httpx.HTTPError as exc:
        raise ChatProviderError(f"聊天供应商流式 HTTP 调用失败：{exc}") from exc
