"""工作台纯逻辑单元测试：最近待办合并。"""
from datetime import datetime, timezone

from app.api.v1.routes.ta import _merge_recent_tasks


def _task(task_type: str, sort_at: datetime) -> dict:
    return {
        "type": task_type, "id": "x", "title": "t", "meta": "m",
        "href": "/", "_sort_at": sort_at,
    }


def test_merge_recent_tasks_sorts_by_time_and_truncates() -> None:
    t_old = _task("grading", datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc))
    t_mid = _task("alert", datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc))
    t_new = _task("grading", datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc))
    result = _merge_recent_tasks([t_old, t_new], [t_mid], limit=2)
    assert len(result) == 2
    assert result[0]["type"] == "grading"   # 最新 t_new
    assert result[1]["type"] == "alert"     # 其次 t_mid
    for item in result:
        assert "_sort_at" not in item       # 内部排序键已移除


def test_merge_recent_tasks_stable_preserves_insert_order_on_ties() -> None:
    same = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    result = _merge_recent_tasks([_task("grading", same)], [_task("alert", same)], limit=6)
    assert [item["type"] for item in result] == ["grading", "alert"]


def test_merge_recent_tasks_empty() -> None:
    assert _merge_recent_tasks([], []) == []
