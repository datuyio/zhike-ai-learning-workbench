from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from app.core.config import settings


_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def model_gateway_http_proxy(base_url: str) -> str | None:
    """解析模型网关出站代理，并自动放行本机供应商地址。"""
    proxy = settings.MODEL_GATEWAY_PROXY_URL or None
    if not proxy:
        return None
    hostname = urlsplit(base_url).hostname or ""
    return None if hostname in _LOCAL_HOSTS else proxy


def model_gateway_client_kwargs(base_url: str, timeout: float) -> dict[str, Any]:
    """构造模型网关 HTTP 客户端所需的通用超时与代理参数。"""
    return {
        "timeout": timeout,
        "proxy": model_gateway_http_proxy(base_url),
    }
