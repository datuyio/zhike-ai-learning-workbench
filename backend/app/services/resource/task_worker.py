from __future__ import annotations

import asyncio
import socket
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.tracing import reset_trace_id, set_trace_id
from app.models import ResourceGenerationTask
from app.services.shared.task_utils import lease_expired, utcnow
from app.services.resource.queue import dequeue_resource_generation
from app.services.resource.repository import process_resource_generation_task


ACTIVE_RESOURCE_STATUSES = {"planning", "retrieving", "generating", "verifying", "safety_checking", "running"}


class ResourceGenerationWorker:
    """资源生成后台 worker，负责认领队列任务并驱动生成流水线。"""

    def __init__(self, *, worker_id: str | None = None, poll_interval_seconds: float = 2.0) -> None:
        host = socket.gethostname() or "worker"
        self.worker_id = worker_id or f"resource:{host}:{uuid.uuid4().hex[:8]}"
        self.poll_interval_seconds = poll_interval_seconds

    def claim_task(self, db: Session, task_id: str) -> ResourceGenerationTask | None:
        """尝试认领指定资源生成任务。

        已被健康 worker 锁定的运行中任务不会被抢占；租约超时或排队任务会被当前
        worker 更新锁信息后继续处理。
        """
        task_uuid = uuid.UUID(str(task_id))
        task = db.get(ResourceGenerationTask, task_uuid)
        if not task or task.status not in {"queued", *ACTIVE_RESOURCE_STATUSES}:
            return None
        if task.status in ACTIVE_RESOURCE_STATUSES and not lease_expired(
            heartbeat_at=task.heartbeat_at,
            locked_at=task.locked_at,
            timeout_seconds=900,
        ):
            return None
        now = utcnow()
        result = db.execute(
            update(ResourceGenerationTask)
            .where(
                ResourceGenerationTask.id == task_uuid,
                ResourceGenerationTask.status.in_(["queued", *ACTIVE_RESOURCE_STATUSES]),
            )
            .values(
                status="planning",
                locked_at=now,
                heartbeat_at=now,
                worker_id=self.worker_id,
                attempt_count=(task.attempt_count or 0) + 1,
            )
        )
        if not result.rowcount:
            db.rollback()
            return None
        db.commit()
        db.refresh(task)
        return task

    def claim_queued_task_from_db(self, db: Session) -> str | None:
        """在 Redis 队列为空时，从数据库兜底认领最早可执行的任务。

        除排队任务外，也检查租约已过期的运行中任务，避免 worker 异常退出后
        任务永久滞留在 planning 等中间状态。
        """
        now = utcnow()
        tasks = db.execute(
            select(ResourceGenerationTask)
            .where(ResourceGenerationTask.status.in_(["queued", *ACTIVE_RESOURCE_STATUSES]))
            .order_by(ResourceGenerationTask.created_at.asc())
            .limit(20)
        ).scalars().all()
        for task in tasks:
            if task.next_retry_at and task.next_retry_at > now:
                continue
            if task.status in ACTIVE_RESOURCE_STATUSES and not lease_expired(
                heartbeat_at=task.heartbeat_at,
                locked_at=task.locked_at,
                timeout_seconds=900,
            ):
                continue
            claimed = self.claim_task(db, str(task.id))
            if claimed:
                return str(claimed.id)
        return None

    async def run_once(self) -> dict[str, str]:
        """执行一轮资源生成任务处理。

        返回:
            status 为 idle、skipped 或 processed 的状态字典，包含 worker_id 和可选 task_id。
        """
        task_id = await asyncio.to_thread(dequeue_resource_generation, 1)
        db = SessionLocal()
        try:
            claimed_from_db = False
            if not task_id:
                task_id = self.claim_queued_task_from_db(db)
                claimed_from_db = bool(task_id)
                if not task_id:
                    return {"status": "idle", "worker_id": self.worker_id}
            if claimed_from_db:
                # 数据库兜底路径已经完成认领，不能再次调用 claim_task，否则新租约会被
                # 当前 worker 自己的锁拒绝，任务会卡在 planning 且永远不会进入流水线。
                task = db.get(ResourceGenerationTask, uuid.UUID(str(task_id)))
            else:
                task = self.claim_task(db, task_id)
            if not task:
                return {"status": "skipped", "worker_id": self.worker_id, "task_id": task_id}
            trace_id = task.trace_id or f"resource_task_{task.id}"
            token = set_trace_id(trace_id)
            try:
                await process_resource_generation_task(str(task.id))
                return {"status": "processed", "worker_id": self.worker_id, "task_id": str(task.id)}
            finally:
                reset_trace_id(token)
        finally:
            db.close()

    async def run_forever(self) -> None:
        """持续运行 worker，并在空闲时按轮询间隔休眠。"""
        while True:
            result = await self.run_once()
            if result.get("status") == "idle":
                await asyncio.sleep(self.poll_interval_seconds)


def run_resource_generation_worker_sync(*, poll_interval_seconds: float = 2.0) -> None:
    """以同步入口启动资源生成 worker，供命令行或独立进程调用。"""
    asyncio.run(ResourceGenerationWorker(poll_interval_seconds=poll_interval_seconds).run_forever())
