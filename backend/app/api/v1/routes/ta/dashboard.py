"""助教端工作台首页统计路由。"""
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_ta
from ._shared import (
    LearningEvent,
    TaAlertRecord,
    TaClass,
    TaGradingRecord,
    User,
    _EPOCH_UTC,
    _relative_time,
    _user_internal_id,
)

router = APIRouter(prefix="/ta", tags=["ta-portal"])


def _merge_recent_tasks(
    grading_tasks: list[dict[str, Any]],
    alert_tasks: list[dict[str, Any]],
    limit: int = 6,
) -> list[dict[str, Any]]:
    """把待批改与预警两类待办按 _sort_at 倒序合并，截断 limit 条并移除内部排序键。"""
    merged = grading_tasks + alert_tasks
    merged.sort(key=lambda t: t["_sort_at"], reverse=True)
    recent = merged[:limit]
    for t in recent:
        t.pop("_sort_at", None)
    return recent


@router.get("/dashboard")
async def ta_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """助教工作台首页统计与最近待办列表。"""
    user_id = _user_internal_id(db, current_user.id)
    if user_id is None:
        return {"class_count": 0, "student_count": 0, "pending_grading": 0, "active_alerts": 0, "recent_tasks": [], "recent_alerts": [], "weekly_active_trend": []}
    classes_count = db.execute(
        select(TaClass).where(TaClass.ta_user_id == user_id, TaClass.is_active == True)
    ).scalars().all()
    class_ids = [c.id for c in classes_count]
    student_ids: list[Any] = []
    for c in classes_count:
        student_ids.extend(m.student_id for m in (c.students or []))
    total_students = 0
    for c in classes_count:
        total_students += len(c.students) if c.students else 0

    # 统计与待办均限定当前助教管理的班级，避免多助教数据串扰
    pending_count = db.execute(
        select(func.count()).select_from(TaGradingRecord).where(
            TaGradingRecord.status == "pending",
            TaGradingRecord.class_id.in_(class_ids),
        )
    ).scalar() or 0
    alert_count = db.execute(
        select(func.count()).select_from(TaAlertRecord).where(
            TaAlertRecord.resolved == False,
            TaAlertRecord.class_id.in_(class_ids),
        )
    ).scalar() or 0

    # 最近待办：待批改作业 + 未处理预警 各取 5 条，按时间倒序合并截断 6 条
    pending_records = db.execute(
        select(TaGradingRecord)
        .where(
            TaGradingRecord.status == "pending",
            TaGradingRecord.class_id.in_(class_ids),
        )
        .order_by(TaGradingRecord.created_at.desc())
        .limit(5)
    ).scalars().all()
    active_alerts = db.execute(
        select(TaAlertRecord)
        .where(
            TaAlertRecord.resolved == False,
            TaAlertRecord.class_id.in_(class_ids),
        )
        .order_by(TaAlertRecord.created_at.desc())
        .limit(5)
    ).scalars().all()
    severity_label = {"high": "高", "medium": "中", "low": "低"}
    grading_tasks: list[dict[str, Any]] = []
    for r in pending_records:
        class_label = ""
        if r.class_id:
            class_ref = db.get(TaClass, r.class_id)
            class_label = f"{class_ref.name} · " if class_ref and class_ref.is_active else ""
        grading_tasks.append({
            "type": "grading",
            "id": str(r.id),
            "title": f"待批改：{r.title}",
            "meta": f"{class_label}{_relative_time(r.created_at)}",
            "href": "/ta/grading",
            "_sort_at": r.created_at or _EPOCH_UTC,
        })
    alert_tasks: list[dict[str, Any]] = []
    for a in active_alerts:
        alert_tasks.append({
            "type": "alert",
            "id": str(a.id),
            "title": f"预警：{a.title}",
            "meta": f"{severity_label.get(a.severity, a.severity)} · {_relative_time(a.created_at)}",
            "href": "/ta/diagnosis",
            "_sort_at": a.created_at or _EPOCH_UTC,
        })
    recent_tasks = _merge_recent_tasks(grading_tasks, alert_tasks)

    # 近 7 天每日活跃学生数（按日 distinct 学习事件，显式 UTC 分桶，避免 DB session 时区耦合）
    weekly_since = datetime.now(timezone.utc) - timedelta(days=6)
    active_rows = db.execute(
        select(
            func.date(func.timezone(literal_column("'UTC'"), LearningEvent.created_at)).label("day"),
            func.count(func.distinct(LearningEvent.user_id)).label("cnt"),
        )
        .where(
            LearningEvent.user_id.in_(student_ids) if student_ids else LearningEvent.user_id == None,
            LearningEvent.created_at >= weekly_since,
        )
        .group_by(func.date(func.timezone(literal_column("'UTC'"), LearningEvent.created_at)))
    ).all()
    active_by_day = {row.day.isoformat(): row.cnt for row in active_rows}
    today = datetime.now(timezone.utc).date()
    weekly_active_trend = []
    for offset in range(6, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        weekly_active_trend.append({"date": day, "active_students": active_by_day.get(day, 0)})

    return {
        "class_count": len(classes_count),
        "student_count": total_students,
        "pending_grading": pending_count,
        "active_alerts": alert_count,
        "recent_tasks": recent_tasks,
        "recent_alerts": [
            {
                "id": str(a.id),
                "title": a.title,
                "severity": a.severity,
                "student_id": str(a.student_id),
                "resolved": a.resolved,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in active_alerts
        ],
        "weekly_active_trend": weekly_active_trend,
    }
