"""助教端 AI 结果缓存：对确定性输入做短 TTL 缓存，避免相同请求重复调用云端 LLM。

仅适合「输入确定 → 输出确定」的生成类结果（教案生成、AI 批改、诊断建议）。
缓存键基于完整 prompt（messages）的 SHA-256，任何影响输出的因素变化都会命中不同键。
Redis（valkey）不可用时降级为不缓存（fail-open），绝不阻断主流程。
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# 生成类结果短缓存 30 分钟：平衡省成本与数据新鲜度。
# 如需按场景差异化或运维可调，可迁移到 settings 配置项。
_AI_CACHE_TTL_SECONDS = 1800


def build_cache_key(scope: str, messages: list[dict[str, Any]]) -> str:
    """按 scope + 完整 prompt 生成确定性缓存键。"""
    canonical = json.dumps(messages, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"ta-ai-cache:{scope}:{digest}"


async def get_cached_ai(scope: str, messages: list[dict[str, Any]]) -> str | None:
    """读取缓存，命中返回结果字符串，未命中或异常返回 None。"""
    try:
        async with redis.from_url(settings.VALKEY_URL, decode_responses=True) as client:
            return await client.get(build_cache_key(scope, messages))
    except Exception as exc:  # 缓存属于可降级能力，任何异常都不阻断主流程
        logger.warning(
            "AI 结果缓存读取失败，跳过缓存：scope=%s error=%s",
            scope, str(exc)[:120],
        )
        return None


async def set_cached_ai(
    scope: str,
    messages: list[dict[str, Any]],
    value: str,
    ttl: int = _AI_CACHE_TTL_SECONDS,
) -> None:
    """写入缓存；失败仅记录日志，不影响主流程。"""
    try:
        async with redis.from_url(settings.VALKEY_URL, decode_responses=True) as client:
            await client.set(build_cache_key(scope, messages), value, ex=ttl)
    except Exception as exc:
        logger.warning(
            "AI 结果缓存写入失败，跳过缓存：scope=%s error=%s",
            scope, str(exc)[:120],
        )
