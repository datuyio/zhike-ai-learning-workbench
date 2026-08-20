from __future__ import annotations

import logging

import redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

RESOURCE_GENERATE_QUEUE = "resource.generate"


_VALID_REDIS_SCHEMES = ("redis://", "rediss://", "unix://")


def _redis_configured() -> bool:
    """判断是否配置了合法的 Redis 连接地址。

    本地演示环境可能没有 Redis/Valkey 服务，此时 VALKEY_URL 为空；
    若直接把空字符串交给 redis.from_url 会抛 ValueError，导致入队接口 500、
    worker 的数据库兜底认领逻辑永远走不到。因此这里先做配置校验。
    """
    url = (settings.VALKEY_URL or "").strip()
    return bool(url) and url.startswith(_VALID_REDIS_SCHEMES)


def _redis_client() -> redis.Redis | None:
    """创建资源生成队列使用的 Redis 客户端；未配置 Redis 时返回 None。"""
    if not _redis_configured():
        return None
    return redis.from_url(settings.VALKEY_URL, decode_responses=True)


def enqueue_resource_generation(task_id: str) -> bool:
    """将资源生成任务 ID 写入 Redis 队列。

    返回:
        入队成功返回 True；task_id 为空、未配置 Redis 或 Redis 写入失败时返回 False。
        未配置 Redis 时返回 False 不算错误：worker 会通过数据库兜底认领排队任务。
    """
    if not task_id:
        return False
    client = _redis_client()
    if client is None:
        logger.info(
            "未配置 VALKEY_URL，跳过 Redis 入队，将由 worker 数据库兜底认领：task_id=%s",
            task_id,
        )
        return False
    try:
        client.lpush(RESOURCE_GENERATE_QUEUE, task_id)
        return True
    except (RedisError, ValueError):
        logger.warning(
            "资源生成任务入队失败，将返回失败状态：queue=%s task_id=%s",
            RESOURCE_GENERATE_QUEUE,
            task_id,
            exc_info=True,
        )
        return False


def dequeue_resource_generation(timeout_seconds: int = 1) -> str | None:
    """从 Redis 队列阻塞式取出一个资源生成任务 ID。

    参数:
        timeout_seconds: 最长阻塞等待秒数，小于 1 时按 1 秒处理。

    返回:
        取到任务时返回 task_id；超时或 Redis 读取失败时返回 None。
    """
    client = _redis_client()
    if client is None:
        # 无 Redis 时直接返回 None，交由调用方走数据库兜底认领。
        return None
    try:
        result = client.brpop(RESOURCE_GENERATE_QUEUE, timeout=max(1, timeout_seconds))
    except (RedisError, ValueError):
        logger.warning(
            "资源生成任务出队失败，将返回空任务：queue=%s timeout_seconds=%s",
            RESOURCE_GENERATE_QUEUE,
            max(1, timeout_seconds),
            exc_info=True,
        )
        return None
    if not result:
        return None
    _, task_id = result
    return str(task_id)
