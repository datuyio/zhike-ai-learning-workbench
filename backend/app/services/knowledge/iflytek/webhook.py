"""带 Valkey 幂等控制的 ChatDoc GET 回调处理器。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Document
from app.services.knowledge.iflytek.cloud_status import map_chatdoc_status
from app.services.knowledge.iflytek.status_labels import normalize_chatdoc_file_status
from app.services.knowledge.iflytek.native_chunk_sync import mark_native_chunks_vectorized, maybe_auto_sync_native_chunks
from app.services.knowledge.iflytek.status_sync import apply_chatdoc_file_status, schedule_chatdoc_status_sync

logger = logging.getLogger(__name__)

_WEBHOOK_DEDUP_PREFIX = "chatdoc:webhook:"
_WEBHOOK_DEDUP_TTL_SECONDS = 86_400


def _redis_client() -> redis.Redis | None:
    """创建用于 webhook 幂等去重的 Valkey 客户端。

    未配置合法 VALKEY_URL 时返回 None，调用方会按首次事件放行，避免空配置
    在 redis.from_url 阶段直接抛 ValueError 阻断回调。
    """
    url = (settings.VALKEY_URL or "").strip()
    if not url or not url.startswith(("redis://", "rediss://", "unix://")):
        return None
    return redis.from_url(settings.VALKEY_URL, decode_responses=True)


def _dedup_key(file_id: str, file_status: str) -> str:
    """生成 webhook 事件幂等去重键。

    参数:
        file_id: ChatDoc 文件 ID。
        file_status: 归一化后的 ChatDoc 文件状态。

    返回:
        可写入 Valkey 的去重键。

    副作用/失败模式:
        纯字符串拼接，无副作用。
    """
    return f"{_WEBHOOK_DEDUP_PREFIX}{file_id}:{file_status}"


def register_webhook_event(file_id: str, file_status: str) -> bool:
    """登记 ChatDoc webhook 事件并判断是否首次出现。

    参数:
        file_id: ChatDoc 文件 ID。
        file_status: 归一化后的 ChatDoc 文件状态。

    返回:
        首次登记成功时返回 True，命中重复事件时返回 False。

    副作用/失败模式:
        会向 Valkey 写入带过期时间的去重键。Valkey 不可用时记录告警并返回 True，避免回调处理被幂等
        存储故障阻断。
    """
    client = _redis_client()
    if client is None:
        return True
    try:
        return bool(client.set(_dedup_key(file_id, file_status), "1", nx=True, ex=_WEBHOOK_DEDUP_TTL_SECONDS))
    except redis.RedisError as exc:
        logger.warning("ChatDoc webhook dedup unavailable: %s", exc)
        return True


def find_document_by_iflytek_file_id(db: Session, file_id: str) -> Document | None:
    """按 ChatDoc 文件 ID 查找未删除的本地文档。

    参数:
        db: 当前数据库会话。
        file_id: ChatDoc 文件 ID。

    返回:
        匹配的 Document 实体；找不到时返回 None。

    副作用/失败模式:
        只读取数据库并遍历文档元数据；数据库查询失败会抛出 SQLAlchemy 相关异常。
    """
    rows = db.execute(
        select(Document).where(
            Document.deleted_at.is_(None),
            Document.parse_status != "deleted",
        )
    ).scalars().all()
    for document in rows:
        meta_file_id = str((document.meta_json or {}).get("iflytek_file_id") or "").strip()
        if meta_file_id == file_id:
            return document
    return None


async def handle_chatdoc_status_webhook(
    db: Session,
    *,
    file_id: str,
    file_status: str,
) -> dict:
    """处理 ChatDoc 文件状态 GET 回调。

    参数:
        db: 当前数据库会话。
        file_id: ChatDoc 文件 ID。
        file_status: ChatDoc 回调携带的原始文件状态。

    返回:
        描述处理结果的字典，可能是 ignored、duplicate、not_found 或 accepted。

    副作用/失败模式:
        会归一化状态、写入 Valkey 去重键、更新文档状态和元数据，必要时自动同步原生切片、标记切片向量化、
        提交数据库事务，并在仍需轮询时调度状态同步任务。数据库或状态同步异常会继续向上传递。
    """
    normalized_status = normalize_chatdoc_file_status(file_status)
    if not file_id or not normalized_status:
        return {"status": "ignored", "reason": "missing_file_id_or_status"}

    if not register_webhook_event(file_id, normalized_status):
        return {"status": "duplicate", "file_id": file_id, "file_status": normalized_status}

    document = find_document_by_iflytek_file_id(db, file_id)
    if not document:
        return {"status": "not_found", "file_id": file_id, "file_status": normalized_status}

    apply_chatdoc_file_status(
        document,
        normalized_status,
        payload={"fileId": file_id, "fileStatus": normalized_status, "source": "webhook"},
    )
    db.flush()

    if normalized_status in {"splited", "split", "vectored", "vectorized"}:
        await maybe_auto_sync_native_chunks(
            db,
            document,
            file_id,
            file_status=normalized_status,
        )
    if normalized_status in {"vectored", "vectorized"} or document.vector_status == "ready":
        mark_native_chunks_vectorized(db, document)

    db.commit()

    _, vector_status, _ = map_chatdoc_status(normalized_status)
    if vector_status == "processing":
        schedule_chatdoc_status_sync(str(document.id))
    elif vector_status not in {"ready", "failed"} and normalized_status not in {"splited", ""}:
        schedule_chatdoc_status_sync(str(document.id))

    return {
        "status": "accepted",
        "document_id": str(document.id),
        "file_id": file_id,
        "file_status": normalized_status,
        "vector_status": document.vector_status,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
