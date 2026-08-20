"""资源生成队列、worker 与相关 Valkey 降级逻辑的回归测试。"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.resource import task_worker
from app.services.resource.queue import dequeue_resource_generation, enqueue_resource_generation
from app.services.resource.queue import settings as queue_settings
from app.services.model_gateway.reload import _valkey_enabled
from app.services.model_gateway.reload import settings as reload_settings


def test_enqueue_without_redis_returns_false(monkeypatch) -> None:
    """未配置 Redis 时入队应安全返回 False，而不是抛出 ValueError。"""
    monkeypatch.setattr(queue_settings, "VALKEY_URL", "")
    assert enqueue_resource_generation(str(uuid.uuid4())) is False


def test_dequeue_without_redis_returns_none(monkeypatch) -> None:
    """未配置 Redis 时出队应安全返回 None，由 worker 走数据库兜底。"""
    monkeypatch.setattr(queue_settings, "VALKEY_URL", "")
    assert dequeue_resource_generation(timeout_seconds=1) is None


def test_invalid_valkey_url_does_not_raise(monkeypatch) -> None:
    """非法连接串也不能在创建客户端阶段破坏任务创建接口。"""
    monkeypatch.setattr(queue_settings, "VALKEY_URL", "not-a-redis-url")
    assert enqueue_resource_generation(str(uuid.uuid4())) is False
    assert dequeue_resource_generation(timeout_seconds=1) is None


def test_database_fallback_does_not_claim_task_twice(monkeypatch) -> None:
    """数据库兜底认领后直接处理任务，避免二次认领导致任务卡在 planning。"""
    worker = task_worker.ResourceGenerationWorker(worker_id="test-worker")
    task_id = uuid.uuid4()
    task = SimpleNamespace(id=task_id, trace_id=None)
    db = MagicMock()
    db.get.return_value = task
    session_local = MagicMock(return_value=db)

    monkeypatch.setattr(task_worker, "SessionLocal", session_local)
    monkeypatch.setattr(task_worker, "dequeue_resource_generation", lambda *_: None)
    monkeypatch.setattr(worker, "claim_queued_task_from_db", lambda _db: str(task_id))
    claim_task = MagicMock()
    monkeypatch.setattr(worker, "claim_task", claim_task)
    process_task = AsyncMock()
    monkeypatch.setattr(task_worker, "process_resource_generation_task", process_task)

    result = asyncio.run(worker.run_once())

    assert result == {
        "status": "processed",
        "worker_id": "test-worker",
        "task_id": str(task_id),
    }
    claim_task.assert_not_called()
    process_task.assert_awaited_once_with(str(task_id))
    db.close.assert_called_once_with()

def test_model_gateway_reload_ignores_invalid_valkey_url(monkeypatch) -> None:
    """非法 Valkey 地址时模型网关应安全退回进程内缓存。"""
    monkeypatch.setattr(reload_settings, "VALKEY_URL", "not-a-redis-url")
    assert _valkey_enabled() is False