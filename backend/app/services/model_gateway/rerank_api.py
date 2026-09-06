from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from app.core.config import settings
from app.services.model_gateway.http_client import model_gateway_client_kwargs


def rerank_url(base_url: str) -> str:
    """根据供应商根地址推导 rerank 接口地址。"""
    root = base_url.rstrip("/")
    if root.endswith("/rerank"):
        return root
    if root.endswith("/chat/completions"):
        return root[: -len("/chat/completions")] + "/rerank"
    if root.endswith("/embeddings"):
        return root[: -len("/embeddings")] + "/rerank"
    return f"{root}/rerank"


async def call_rerank_api(
    *,
    protocol: str,
    base_url: str,
    api_key: str | None,
    model: str,
    query: str,
    documents: Sequence[str],
    top_n: int | None = None,
) -> list[float]:
    """调用重排序接口，返回每篇候选文档的相关性分数。

    参数:
        protocol: 网关配置中的 rerank 协议标识。
        base_url: 供应商接口根地址或 rerank 完整地址。
        api_key: 可选访问密钥。
        model: rerank 模型名称。
        query: 检索查询文本。
        documents: 候选文档文本序列。
        top_n: 可选返回数量限制，由供应商决定是否支持。

    返回:
        与 documents 顺序对应的相关性分数。

    异常:
        RuntimeError: 协议不支持或供应商响应缺少分数时抛出。
    """
    if protocol not in {"openai_compatible", "rerank", "dashscope_rerank"}:
        raise RuntimeError(f"unsupported rerank protocol: {protocol}")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: dict[str, Any] = {"model": model, "query": query, "documents": list(documents)}
    if top_n:
        payload["top_n"] = top_n
    async with httpx.AsyncClient(**model_gateway_client_kwargs(base_url, settings.MODEL_GATEWAY_TIMEOUT_SECONDS)) as client:
        response = await client.post(rerank_url(base_url), headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    scores = [0.0 for _ in documents]
    rows = data.get("results") or data.get("output", {}).get("results") or data.get("data") or []
    for fallback_index, row in enumerate(rows):
        index = int(row.get("index", row.get("document_index", fallback_index)))
        if 0 <= index < len(scores):
            scores[index] = float(row.get("relevance_score", row.get("score", row.get("similarity", 0.0))) or 0.0)
    if rows and any(scores):
        return scores
    values = data.get("scores")
    if isinstance(values, list) and len(values) == len(documents):
        return [float(value or 0.0) for value in values]
    raise RuntimeError("rerank response has no scores")
