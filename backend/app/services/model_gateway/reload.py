from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


_VALID_VALKEY_SCHEMES = ("redis://", "rediss://", "unix://")


def _valkey_enabled() -> bool:
    """返回当前环境是否配置了合法的 Valkey 地址；未配置时使用进程内缓存。"""
    url = (settings.VALKEY_URL or "").strip()
    return bool(url) and url.startswith(_VALID_VALKEY_SCHEMES)


async def publish_model_gateway_reload(reason: str, payload: dict[str, Any] | None = None) -> None:
    """发布模型网关配置热重载事件。

    热重载用于跨进程或跨节点尽快刷新供应商配置；发布失败不会中断主流程，
    因为运行时仍会依赖缓存 TTL 兜底同步数据库变更。
    """
    if not _valkey_enabled():
        return
    try:
        client = redis.from_url(settings.VALKEY_URL, decode_responses=True)
        try:
            await client.publish(
                settings.MODEL_GATEWAY_RELOAD_CHANNEL,
                json.dumps({"reason": reason, "payload": payload or {}}, ensure_ascii=False),
            )
        finally:
            await client.aclose()
    except (RedisError, ValueError):
        payload_keys = sorted((payload or {}).keys())
        logger.warning(
            "发布模型网关热重载消息失败，将等待 TTL 兜底生效：channel=%s reason=%s payload_keys=%s",
            settings.MODEL_GATEWAY_RELOAD_CHANNEL,
            reason,
            payload_keys,
            exc_info=True,
        )
        return


async def model_gateway_reload_listener() -> None:
    """监听模型网关热重载频道，并在收到事件后失效供应商缓存。"""
    if not _valkey_enabled():
        return
    from app.services.model_gateway.router import ModelGateway

    client = redis.from_url(settings.VALKEY_URL, decode_responses=True)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(settings.MODEL_GATEWAY_RELOAD_CHANNEL)
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                ModelGateway.invalidate_provider_cache()
            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        raise
    except (RedisError, ValueError):
        logger.warning(
            "模型网关热重载监听退出，将依赖 TTL 兜底刷新配置：channel=%s",
            settings.MODEL_GATEWAY_RELOAD_CHANNEL,
            exc_info=True,
        )
        return
    finally:
        try:
            await pubsub.unsubscribe(settings.MODEL_GATEWAY_RELOAD_CHANNEL)
        except (RedisError, ValueError):
            logger.debug(
                "模型网关热重载取消订阅失败，继续清理连接：channel=%s",
                settings.MODEL_GATEWAY_RELOAD_CHANNEL,
                exc_info=True,
            )
        try:
            await pubsub.close()
        except (RedisError, ValueError):
            logger.debug(
                "模型网关热重载 PubSub 关闭失败，继续清理连接：channel=%s",
                settings.MODEL_GATEWAY_RELOAD_CHANNEL,
                exc_info=True,
            )
        try:
            await client.aclose()
        except (RedisError, ValueError):
            logger.debug(
                "模型网关热重载 Redis 客户端关闭失败：channel=%s",
                settings.MODEL_GATEWAY_RELOAD_CHANNEL,
                exc_info=True,
            )
