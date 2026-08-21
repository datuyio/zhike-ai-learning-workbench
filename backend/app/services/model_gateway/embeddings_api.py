from __future__ import annotations

import base64
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.services.model_gateway.http_client import model_gateway_client_kwargs


def embeddings_url(base_url: str) -> str:
    """根据供应商根地址推导 OpenAI 兼容的 embeddings 接口地址。"""
    root = base_url.rstrip("/")
    if root.endswith("/embeddings"):
        return root
    if root.endswith("/chat/completions"):
        return root[: -len("/chat/completions")] + "/embeddings"
    return f"{root}/embeddings"


async def call_embedding_api(
    *,
    protocol: str,
    base_url: str,
    api_key: str | None,
    model: str,
    texts: Sequence[str],
    provider_meta: dict[str, Any] | None = None,
) -> list[list[float]]:
    """调用文本 embedding 接口并返回按输入顺序排列的向量列表。

    参数:
        protocol: 网关配置中的 embedding 协议标识。
        base_url: 供应商接口根地址或 embeddings 完整地址。
        api_key: 可选访问密钥。
        model: embedding 模型名称。
        texts: 待向量化文本序列。
        provider_meta: 供应商附加配置，当前保留给后续协议扩展。

    返回:
        与 texts 顺序对应的浮点向量列表。

    异常:
        RuntimeError: 协议已移除、供应商响应缺少向量或 HTTP 调用失败时抛出。
    """
    if protocol == "iflytek_embedding":
        raise RuntimeError(
            "ChatDoc 讯飞 LLM Embedding 协议已移除；课程 PDF 向量化请在网关中心配置知识向量化凭证（按模板 env_prefix 设置 .env），"
            "文档 https://chatdoc.xfyun.cn/docs#/"
        )
    if protocol == "dashscope_embedding":
        return await call_dashscope_embedding(base_url=base_url, api_key=api_key, model=model, texts=texts)
    return await call_openai_embedding(base_url=base_url, api_key=api_key, model=model, texts=texts)


async def call_multimodal_embedding_api(
    *,
    protocol: str,
    base_url: str,
    api_key: str | None,
    model: str,
    inputs: Sequence[dict[str, Any]],
) -> list[list[float]]:
    """调用多模态 embedding 接口。

    各供应商尚未形成完全统一的图片 embedding 协议。本适配器优先支持通用 JSON
    载荷；对于 OpenAI 兼容或 DashScope 文本供应商，则回退到纯文本 embedding，
    让页面摘要在未配置视觉 embedding 时仍可被检索。
    """
    if protocol in {"openai_compatible", "dashscope_embedding"}:
        texts = [str(item.get("text") or item.get("summary") or item.get("image_uri") or "") for item in inputs]
        return await call_embedding_api(protocol=protocol, base_url=base_url, api_key=api_key, model=model, texts=texts)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload_inputs: list[dict[str, Any]] = []
    for item in inputs:
        payload = {
            "text": item.get("text") or item.get("summary") or "",
            "image": item.get("image") or item.get("image_url") or item.get("image_uri"),
        }
        image_uri = payload.get("image")
        if isinstance(image_uri, str) and image_uri and not image_uri.startswith(("http://", "https://", "data:")):
            encoded = _image_data_uri(image_uri)
            if encoded:
                payload["image"] = encoded
        payload_inputs.append(payload)
    async with httpx.AsyncClient(**model_gateway_client_kwargs(base_url, settings.MODEL_GATEWAY_TIMEOUT_SECONDS)) as client:
        response = await client.post(embeddings_url(base_url), headers=headers, json={"model": model, "input": payload_inputs})
        response.raise_for_status()
        data = response.json()
    rows = sorted(data.get("data") or data.get("output", {}).get("embeddings", []), key=lambda row: row.get("index", row.get("text_index", 0)))
    vectors = [row.get("embedding", []) for row in rows]
    return _normalize_vectors(vectors)


async def call_openai_embedding(*, base_url: str, api_key: str | None, model: str, texts: Sequence[str]) -> list[list[float]]:
    """调用 OpenAI 兼容 embeddings 接口。"""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: dict[str, Any] = {"model": model, "input": list(texts)}
    async with httpx.AsyncClient(**model_gateway_client_kwargs(base_url, settings.MODEL_GATEWAY_TIMEOUT_SECONDS)) as client:
        response = await client.post(embeddings_url(base_url), headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    rows = sorted(data.get("data", []), key=lambda row: row.get("index", 0))
    vectors = [row.get("embedding", []) for row in rows]
    return _normalize_vectors(vectors)


async def call_dashscope_embedding(*, base_url: str, api_key: str | None, model: str, texts: Sequence[str]) -> list[list[float]]:
    """调用 DashScope 文本向量接口并归一化返回格式。"""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: dict[str, Any] = {
        "model": model,
        "input": {"texts": list(texts)},
        "parameters": {"text_type": "document"},
    }
    async with httpx.AsyncClient(**model_gateway_client_kwargs(base_url, settings.MODEL_GATEWAY_TIMEOUT_SECONDS)) as client:
        response = await client.post(base_url.rstrip("/"), headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    output = data.get("output", {})
    rows = output.get("embeddings", [])
    rows = sorted(rows, key=lambda row: row.get("text_index", row.get("index", 0)))
    vectors = [row.get("embedding", []) for row in rows]
    return _normalize_vectors(vectors)


def _normalize_vectors(vectors: Sequence[Any]) -> list[list[float]]:
    if not vectors or not all(isinstance(vec, list) and vec for vec in vectors):
        raise RuntimeError("embedding response has no vectors")
    return [[float(value) for value in vec] for vec in vectors]


def _image_data_uri(path: str) -> str | None:
    image_path = Path(path)
    if not image_path.exists() or not image_path.is_file():
        return None
    suffix = image_path.suffix.lower()
    media_type = "image/png" if suffix not in {".jpg", ".jpeg"} else "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"
