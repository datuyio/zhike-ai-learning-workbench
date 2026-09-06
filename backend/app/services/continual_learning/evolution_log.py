"""进化日志：记录系统持续学习行为的演变历史，形成可视化进化轨迹。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.continual_learning import ContinualEvolutionEvent


def record_evolution(
    db: Session,
    *,
    event_type: str,
    title: str,
    detail: str | None = None,
    metrics: dict[str, Any] | None = None,
    flush: bool = True,
) -> ContinualEvolutionEvent:
    """写入一条进化日志事件。

    参数:
        db: 数据库会话。
        event_type: 事件类型，如 feedback_calibration / risk_recalibrated /
            error_patterns_updated / negative_feedback。
        title: 事件标题，用于时间线展示。
        detail: 事件详细说明文案。
        metrics: 量化指标载荷，供前端绘制进化轨迹。
        flush: 是否立即 flush。
    """
    event = ContinualEvolutionEvent(
        event_type=event_type,
        title=title,
        detail=detail,
        metrics_json=metrics or {},
    )
    db.add(event)
    if flush:
        db.flush()
    return event


def list_evolution(db: Session, limit: int = 60) -> list[dict[str, Any]]:
    """按时间倒序返回进化日志，供前端时间线展示。"""
    rows = db.execute(
        select(ContinualEvolutionEvent)
        .order_by(ContinualEvolutionEvent.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "event_type": r.event_type,
            "title": r.title,
            "detail": r.detail,
            "metrics": r.metrics_json or {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
