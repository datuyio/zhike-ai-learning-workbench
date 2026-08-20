from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

import redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RateLimitExceeded(Exception):
    """表示请求触发了业务限流策略。

    属性:
        scope: 触发限流的业务范围。
        retry_after_seconds: 建议客户端等待后重试的秒数。
    """

    scope: str
    retry_after_seconds: int

    def __str__(self) -> str:
        return f"{self.scope} rate limit exceeded; retry after {self.retry_after_seconds}s"


def _redis_client() -> redis.Redis:
    """创建用于限流计数的 Redis 客户端。"""
    return redis.from_url(settings.VALKEY_URL, decode_responses=True)


def _normalize_scope_part(value: str | None) -> str:
    """规范化限流键中的用户或课程片段。"""
    return (value or "global").strip().replace(" ", "_")[:120]


def _consume_fixed_window(key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
    """返回是否允许请求以及需要等待的秒数。"""
    if limit <= 0:
        return True, 0
    if not settings.VALKEY_URL.strip():
        # Redis 未配置时跳过限流，保证本地无 Redis 的演示环境仍能正常对话。
        return True, 0
    try:
        client = _redis_client()
        count = int(client.incr(key))
        if count == 1:
            client.expire(key, window_seconds)
        ttl = int(client.ttl(key))
        if ttl < 0:
            client.expire(key, window_seconds)
            ttl = window_seconds
        if count <= limit:
            return True, 0
        return False, max(1, ttl)
    except (RedisError, ValueError):
        key_parts = key.split(":")
        key_scope = ":".join(key_parts[:2]) if len(key_parts) >= 2 else "rate"
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        logger.warning(
            "限流检查失败，将放行请求：scope=%s key_hash=%s limit=%s window_seconds=%s",
            key_scope,
            key_hash,
            limit,
            window_seconds,
            exc_info=True,
        )
        return True, 0


def check_chat_rate_limit(user_id: str, course_id: str) -> None:
    """检查指定用户在课程对话中的分钟级限流。

    参数:
        user_id: 当前请求用户标识。
        course_id: 当前课程标识。

    异常:
        RateLimitExceeded: 当请求次数超过配置的分钟级上限时抛出。
    """
    key = f"rate:chat:{_normalize_scope_part(user_id)}:{_normalize_scope_part(course_id)}"
    allowed, retry_after = _consume_fixed_window(
        key,
        limit=settings.CHAT_RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
    )
    if not allowed:
        raise RateLimitExceeded("chat", retry_after)


def check_resource_rate_limit(user_id: str, course_id: str) -> None:
    """检查指定用户在课程资源生成中的日级限流。

    参数:
        user_id: 当前请求用户标识。
        course_id: 当前课程标识。

    异常:
        RateLimitExceeded: 当资源生成次数超过配置的日级上限时抛出。
    """
    key = f"rate:resource:{_normalize_scope_part(user_id)}:{_normalize_scope_part(course_id)}"
    allowed, retry_after = _consume_fixed_window(
        key,
        limit=settings.RESOURCE_TASK_DAILY_LIMIT,
        window_seconds=86_400,
    )
    if not allowed:
        raise RateLimitExceeded("resource.generate", retry_after)
