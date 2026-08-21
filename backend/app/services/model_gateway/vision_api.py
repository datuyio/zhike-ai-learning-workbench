from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.services.model_gateway.http_client import model_gateway_client_kwargs


def chat_completions_url(base_url: str) -> str:
    """根据供应商根地址推导 OpenAI 兼容的 chat completions 地址。"""
    root = base_url.rstrip("/")
    if root.endswith("/chat/completions"):
        return root
    if root.endswith("/embeddings"):
        return root[: -len("/embeddings")] + "/chat/completions"
    return f"{root}/chat/completions"


async def call_vision_api(
    *,
    protocol: str,
    base_url: str,
    api_key: str | None,
    model: str,
    prompt: str,
    image_uri: str | None,
) -> str:
    """调用视觉理解接口，返回模型生成的纯文本结果。

    参数:
        protocol: 网关配置中的视觉协议标识。
        base_url: 供应商接口根地址或 chat completions 完整地址。
        api_key: 可选访问密钥。
        model: 视觉模型名称。
        prompt: 发送给模型的文本提示。
        image_uri: 图片 URL、data URI 或本地文件路径。

    返回:
        模型响应中的文本内容，缺省时返回空字符串。

    异常:
        RuntimeError: 协议不支持或供应商响应缺少 choices 时抛出。
    """
    if protocol not in {"openai_compatible", "vision_openai_compatible", "vlm_openai_compatible"}:
        raise RuntimeError(f"unsupported vision protocol: {protocol}")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    image_url = _image_data_uri(image_uri) if image_uri else None
    if image_url:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": settings.MODEL_GATEWAY_MAX_TOKENS,
    }
    async with httpx.AsyncClient(**model_gateway_client_kwargs(base_url, settings.MODEL_GATEWAY_TIMEOUT_SECONDS)) as client:
        response = await client.post(chat_completions_url(base_url), headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("vision response has no choices")
    message = choices[0].get("message") or {}
    content_value = message.get("content")
    if isinstance(content_value, list):
        return "\n".join(str(part.get("text") or "") for part in content_value if isinstance(part, dict)).strip()
    return str(content_value or "").strip()


def _image_data_uri(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith(("http://", "https://", "data:")):
        return path
    image_path = Path(path)
    if not image_path.exists() or not image_path.is_file():
        return None
    suffix = image_path.suffix.lower()
    media_type = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"
