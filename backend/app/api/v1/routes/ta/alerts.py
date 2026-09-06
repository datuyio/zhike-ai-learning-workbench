"""助教端预警路由：列表/处理/干预/生成，含规则候选与模板文案纯函数。"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_ta
from ._shared import (
    ConceptMastery,
    CourseConcept,
    LearningEvent,
    Resource,
    TaAlertAction,
    TaAlertRecord,
    TaClass,
    TaGradingRecord,
    TaNotification,
    User,
    _ALERT_RATE_MAX_COUNT,
    _ALERT_RATE_WINDOW_SECONDS,
    _EPOCH_UTC,
    _MASTERY_WEAK_THRESHOLD,
    _apply_page,
    _class_mastery_rows,
    _class_student_ids,
    _relative_time,
    _render_template,
    _require_uuid,
    _user_internal_id,
    _weakness_severity,
    consume_fixed_window,
)

router = APIRouter(prefix="/ta", tags=["ta-portal"])


class InterventionRequest(BaseModel):
    """预警干预动作请求体。"""
    action_type: str = Field(description="notify/recommend_resources/book_tutoring/note")
    content: str | None = None
    resource_ids: list[str] | None = None
    tutoring_time: datetime | None = None


class ResolveAlertRequest(BaseModel):
    """处理预警请求体（resolution_note 可选）。"""
    resolution_note: str | None = None


# 预警生成模板与限流配置（借鉴 ai-smart NotificationService 的"模板+占位符+频率限制"范式）
_ALERT_TEMPLATES: dict[str, dict[str, str]] = {
    "mastery_gap": {
        "title": "{student_name} 掌握度预警：{concept}",
        "description": "{student_name} 在知识点《{concept}》的平均掌握度仅 {mastery}%，低于 {threshold}% 预警阈值，建议安排针对性练习。",
    },
    "inactive": {
        "title": "{student_name} 学习活跃度预警",
        "description": "{student_name} 已连续 {days} 天无学习记录，建议提醒学生恢复学习节奏。",
    },
    "score_drop": {
        "title": "{student_name} 成绩下滑预警",
        "description": "{student_name} 最近一次成绩 {last_score} 分，较上次 {prev_score} 分下降 {delta} 分，请关注。",
    },
    "late_submission": {
        "title": "{student_name} 迟交作业预警",
        "description": "{student_name} 存在 {count} 次迟交作业记录，最近一次为《{last_title}》（{last_at}），请关注提交纪律。",
    },
    "resource_idle": {
        "title": "{student_name} 资料学习停滞预警",
        "description": "{student_name} 已连续 {days} 天未查阅学习资料，建议提醒其恢复资料学习。",
    },
}


@router.get("/alerts")
async def list_alerts(
    resolved: bool | None = False,
    class_id: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> list[dict[str, Any]]:
    """获取预警列表。"""
    stmt = select(TaAlertRecord)
    if resolved is not None:
        stmt = stmt.where(TaAlertRecord.resolved == resolved)
    if class_id:
        class_id_uuid = _require_uuid(class_id, "班级不存在")
        stmt = stmt.where(TaAlertRecord.class_id == class_id_uuid)
    stmt = stmt.order_by(TaAlertRecord.created_at.desc())
    stmt = _apply_page(stmt, limit, offset)
    alerts = db.execute(stmt).scalars().all()
    return [
        {
            "id": a.id, "title": a.title, "alert_type": a.alert_type,
            "severity": a.severity, "student_id": a.student_id,
            "resolved": a.resolved,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    payload: ResolveAlertRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, str]:
    """处理预警；可附带 resolution_note（同时写入 note 干预动作）。"""
    alert_id_uuid = _require_uuid(alert_id, "预警不存在")
    alert = db.get(TaAlertRecord, alert_id_uuid)
    if not alert:
        raise HTTPException(status_code=404, detail="预警不存在")
    alert.resolved = True
    alert.resolved_at = datetime.now(timezone.utc)
    if payload and payload.resolution_note:
        user_id = _user_internal_id(db, current_user.id)
        db.add(TaAlertAction(
            alert_id=alert.id,
            created_by=user_id,
            action_type="note",
            content=payload.resolution_note,
            target_student_id=alert.student_id,
        ))
    db.commit()
    return {"message": "预警已处理"}


@router.post("/alerts/{alert_id}/intervene")
async def intervene_alert(
    alert_id: str,
    payload: InterventionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """预警干预：notify(生成提醒通知)/recommend_resources(检索推荐)/book_tutoring(预约)/note(备注)。

    每个动作写一条 ta_alert_actions；notify 同时生成 ta_notifications(alert_reminder) 定向该学生。
    """
    alert_id_uuid = _require_uuid(alert_id, "预警不存在")
    alert = db.get(TaAlertRecord, alert_id_uuid)
    if not alert:
        raise HTTPException(status_code=404, detail="预警不存在")
    user_id = _user_internal_id(db, current_user.id)
    if user_id is None:
        raise HTTPException(status_code=403, detail="当前用户不存在")
    try:
        dispatched = _dispatch_intervention(
            payload.action_type,
            alert.title,
            alert.description,
            payload.content,
            payload.resource_ids,
            payload.tutoring_time,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    notification_id = None
    if dispatched["notification"]:
        notif = TaNotification(
            student_id=alert.student_id,
            class_id=alert.class_id,
            title=dispatched["notification"]["title"],
            body=dispatched["notification"]["body"],
            notification_type="alert_reminder",
            source_type="alert",
            source_id=str(alert.id),
        )
        db.add(notif)
        db.flush()
        notification_id = notif.id

    resource_ids = dispatched["resource_ids"]
    if payload.action_type == "recommend_resources" and not resource_ids:
        resource_ids = _recommend_resource_ids(db, alert)

    action = TaAlertAction(
        alert_id=alert.id,
        created_by=user_id,
        action_type=dispatched["action_type"],
        content=dispatched["content"],
        target_student_id=alert.student_id,
        resource_ids=resource_ids,
        tutoring_time=dispatched["tutoring_time"],
        notification_id=notification_id,
    )
    db.add(action)
    db.commit()
    return {
        "id": str(action.id),
        "action_type": action.action_type,
        "notification_id": str(notification_id) if notification_id else None,
        "resource_ids": resource_ids or [],
        "message": "干预动作已记录",
    }


@router.get("/alerts/{alert_id}/actions")
async def list_alert_actions(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> list[dict[str, Any]]:
    """该预警的干预历史（时间正序）。"""
    alert_id_uuid = _require_uuid(alert_id, "预警不存在")
    actions = db.execute(
        select(TaAlertAction)
        .where(TaAlertAction.alert_id == alert_id_uuid)
        .order_by(TaAlertAction.created_at.asc())
    ).scalars().all()
    return [
        {
            "id": str(a.id),
            "action_type": a.action_type,
            "content": a.content,
            "resource_ids": a.resource_ids or [],
            "tutoring_time": a.tutoring_time.isoformat() if a.tutoring_time else None,
            "notification_id": str(a.notification_id) if a.notification_id else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in actions
    ]


def _build_alert_notification(alert_title: str, alert_description: str | None, content: str | None) -> dict[str, str]:
    """构造预警提醒通知标题/正文：优先干预文案，回退预警描述，再回退默认文案。"""
    title = f"学习提醒：{alert_title}"
    if content:
        body = content
    elif alert_description:
        body = alert_description
    else:
        body = "助教关注到你的学习情况，请及时查看。"
    return {"title": title, "body": body}


def _dispatch_intervention(
    action_type: str,
    alert_title: str,
    alert_description: str | None,
    content: str | None,
    resource_ids: list[str] | None,
    tutoring_time: datetime | None,
) -> dict[str, Any]:
    """校验并归一化预警干预动作；非法动作抛 ValueError（端点转 400）。

    返回 {action_type, content, resource_ids, tutoring_time, notification}，
    notification 仅在 notify 动作下为 {title, body}，其余为 None。
    """
    valid = {"notify", "recommend_resources", "book_tutoring", "note"}
    if action_type not in valid:
        raise ValueError(f"不支持的干预动作: {action_type}")
    notification = None
    if action_type == "notify":
        notification = _build_alert_notification(alert_title, alert_description, content)
    return {
        "action_type": action_type,
        "content": content,
        "resource_ids": resource_ids,
        "tutoring_time": tutoring_time,
        "notification": notification,
    }


def _recommend_resource_ids(db: Session, alert: TaAlertRecord) -> list[str]:
    """按预警学生的弱知识点（掌握度最低的 3 个）检索审核通过的资源，取前 5 条。"""
    mastery_rows = db.execute(
        select(ConceptMastery)
        .where(ConceptMastery.user_id == alert.student_id)
        .order_by(ConceptMastery.mastery.asc())
        .limit(3)
    ).scalars().all()
    concept_ids = [r.concept_id for r in mastery_rows if r.concept_id]
    if not concept_ids:
        return []
    resources = db.execute(
        select(Resource)
        .where(Resource.concept_id.in_(concept_ids), Resource.status == "published")
        .order_by(Resource.created_at.desc())
        .limit(5)
    ).scalars().all()
    return [str(r.id) for r in resources]


@router.post("/alerts/generate")
async def generate_alerts(
    class_id: str,
    rule: str = "mastery_gap",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """按规则为班级生成预警：模板化标题/描述 + 每人每类型窗口限流。

    规则：mastery_gap（掌握度低于阈值）、inactive（连续 N 天无学习）、score_drop（成绩下滑）、
    late_submission（迟交作业）、resource_idle（资料学习停滞）。
    """
    if rule not in _ALERT_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"不支持的预警规则: {rule}")
    class_id_uuid = _require_uuid(class_id, "班级不存在")
    cls = db.get(TaClass, class_id_uuid)
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    student_ids = _class_student_ids(db, class_id_uuid)
    if not student_ids:
        return {"generated": 0, "skipped_limited": 0, "alerts": []}

    users = db.execute(select(User).where(User.id.in_(student_ids))).scalars().all()
    name_by_id = {u.id: (u.display_name or str(u.id)) for u in users}
    # 掌握度数据仅在 mastery_gap 规则下需要，避免其余规则无谓查询
    mastery_rows: list[Any] = []
    title_by_id: dict[Any, str] = {}
    if rule == "mastery_gap":
        mastery_rows = _class_mastery_rows(db, cls, student_ids)
        concept_ids = {r.concept_id for r in mastery_rows}
        concepts = (
            db.execute(select(CourseConcept).where(CourseConcept.id.in_(concept_ids))).scalars().all()
            if concept_ids else []
        )
        title_by_id = {c.id: c.title for c in concepts}
    candidates = _find_alert_candidates(rule, db, student_ids, name_by_id, mastery_rows, title_by_id)

    generated: list[TaAlertRecord] = []
    skipped = 0
    for candidate in candidates:
        rate_key = f"rate:ta-alert:{candidate['student_id']}:{rule}"
        if not consume_fixed_window(rate_key, limit=_ALERT_RATE_MAX_COUNT, window_seconds=_ALERT_RATE_WINDOW_SECONDS):
            skipped += 1
            continue
        template = _ALERT_TEMPLATES[rule]
        alert = TaAlertRecord(
            student_id=candidate["student_id"],
            class_id=class_id_uuid,
            course_id=cls.course_id,
            alert_type=rule,
            severity=candidate["severity"],
            title=_render_template(template["title"], candidate),
            description=_render_template(template["description"], candidate),
        )
        db.add(alert)
        generated.append(alert)
    db.commit()
    return {
        "generated": len(generated),
        "skipped_limited": skipped,
        "alerts": [
            {"id": str(a.id), "title": a.title, "student_id": str(a.student_id), "severity": a.severity}
            for a in generated
        ],
    }


def _find_alert_candidates(
    rule: str,
    db: Session,
    student_ids: list[Any],
    name_by_id: dict[Any, str],
    mastery_rows: list[Any],
    title_by_id: dict[Any, str],
) -> list[dict[str, Any]]:
    """按规则计算预警候选人，返回含模板变量与严重程度的候选 dict 列表。"""
    if rule == "mastery_gap":
        return _mastery_gap_candidates(mastery_rows, name_by_id, title_by_id)
    if rule == "inactive":
        return _inactive_candidates(db, student_ids, name_by_id)
    if rule == "score_drop":
        return _score_drop_candidates(db, student_ids, name_by_id)
    if rule == "late_submission":
        return _late_submission_candidates(db, student_ids, name_by_id)
    if rule == "resource_idle":
        return _resource_idle_candidates(db, student_ids, name_by_id)
    return []


def _mastery_gap_candidates(
    mastery_rows: list[Any],
    name_by_id: dict[Any, str],
    title_by_id: dict[Any, str],
) -> list[dict[str, Any]]:
    """掌握度预警：每个学生取其最弱且低于阈值的知识点为候选。"""
    by_student: dict[Any, list[tuple[Any, float]]] = {}
    for row in mastery_rows:
        by_student.setdefault(row.user_id, []).append((row.concept_id, row.mastery))
    candidates: list[dict[str, Any]] = []
    for student_id, rows in by_student.items():
        concept_id, mastery = min(rows, key=lambda item: item[1])
        if mastery >= _MASTERY_WEAK_THRESHOLD:
            continue
        candidates.append({
            "student_id": student_id,
            "student_name": name_by_id.get(student_id, str(student_id)),
            "concept": title_by_id.get(concept_id, str(concept_id)),
            "mastery": int(mastery),
            "threshold": _MASTERY_WEAK_THRESHOLD,
            "severity": _weakness_severity(mastery),
        })
    return candidates


def _inactive_candidates(
    db: Session,
    student_ids: list[Any],
    name_by_id: dict[Any, str],
    days: int = 7,
) -> list[dict[str, Any]]:
    """活跃度预警：超过 days 天无学习事件或从未有学习记录的学生。"""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    candidates: list[dict[str, Any]] = []
    for student_id in student_ids:
        last = db.execute(
            select(LearningEvent.created_at)
            .where(LearningEvent.user_id == student_id)
            .order_by(LearningEvent.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if last is not None and last >= since:
            continue
        gap = (now - last).days if last is not None else 30
        candidates.append({
            "student_id": student_id,
            "student_name": name_by_id.get(student_id, str(student_id)),
            "days": gap,
            "severity": "high" if last is None or gap > 14 else "medium",
        })
    return candidates


def _score_drop_candidates(
    db: Session,
    student_ids: list[Any],
    name_by_id: dict[Any, str],
    drop_threshold: int = 10,
) -> list[dict[str, Any]]:
    """成绩下滑预警：最近两次已批改成绩中最近一次较前次下降超过阈值。"""
    candidates: list[dict[str, Any]] = []
    for student_id in student_ids:
        records = db.execute(
            select(TaGradingRecord)
            .where(
                TaGradingRecord.student_id == student_id,
                TaGradingRecord.status == "graded",
                TaGradingRecord.score.isnot(None),
            )
            .order_by(TaGradingRecord.updated_at.desc())
            .limit(2)
        ).scalars().all()
        if len(records) < 2:
            continue
        last, prev = records[0], records[1]
        delta = float(prev.score) - float(last.score)
        if delta < drop_threshold:
            continue
        candidates.append({
            "student_id": student_id,
            "student_name": name_by_id.get(student_id, str(student_id)),
            "last_score": int(float(last.score)),
            "prev_score": int(float(prev.score)),
            "delta": int(delta),
            "severity": "high" if delta >= 20 else "medium",
        })
    return candidates


def _pick_late_submission_candidates(
    by_student: dict[Any, list[Any]],
    name_by_id: dict[Any, str],
) -> list[dict[str, Any]]:
    """从 {student_id: [TaGradingRecord]} 中选择存在 is_late=True 记录的学生，取最近一次迟交信息。"""
    candidates: list[dict[str, Any]] = []
    for student_id, records in by_student.items():
        late_records = [r for r in records if r.is_late]
        if not late_records:
            continue
        latest = max(late_records, key=lambda r: r.created_at or _EPOCH_UTC)
        candidates.append({
            "student_id": student_id,
            "student_name": name_by_id.get(student_id, str(student_id)),
            "count": len(late_records),
            "last_title": latest.title,
            "last_at": _relative_time(latest.created_at),
            "severity": "high" if len(late_records) >= 3 else "medium",
        })
    return candidates


def _late_submission_candidates(
    db: Session,
    student_ids: list[Any],
    name_by_id: dict[Any, str],
) -> list[dict[str, Any]]:
    """迟交预警：该生存在 is_late=True 的批改记录。"""
    records = db.execute(
        select(TaGradingRecord)
        .where(
            TaGradingRecord.student_id.in_(student_ids),
            TaGradingRecord.is_late == True,
        )
    ).scalars().all()
    by_student: dict[Any, list[Any]] = {}
    for r in records:
        by_student.setdefault(r.student_id, []).append(r)
    return _pick_late_submission_candidates(by_student, name_by_id)


def _pick_resource_idle_candidates(
    stat_by_student: dict[Any, tuple[datetime | None, bool]],
    name_by_id: dict[Any, str],
    now: datetime,
    idle_days: int = 7,
) -> list[dict[str, Any]]:
    """stat_by_student: {student_id: (最近 resource_view 时间, 是否有历史)}。
    近 idle_days 天零资料查阅且历史曾查阅过 → 候选。"""
    since = now - timedelta(days=idle_days)
    candidates: list[dict[str, Any]] = []
    for student_id, (last_view, has_history) in stat_by_student.items():
        if not has_history:
            continue
        if last_view is not None and last_view >= since:
            continue
        gap = (now - last_view).days if last_view is not None else idle_days
        candidates.append({
            "student_id": student_id,
            "student_name": name_by_id.get(student_id, str(student_id)),
            "days": gap,
            "severity": "high" if gap > idle_days * 2 else "medium",
        })
    return candidates


def _resource_idle_candidates(
    db: Session,
    student_ids: list[Any],
    name_by_id: dict[Any, str],
    idle_days: int = 7,
) -> list[dict[str, Any]]:
    """资料停滞预警：近 idle_days 天零 resource_view 事件且历史曾查阅过资料。"""
    now = datetime.now(timezone.utc)
    stat_by_student: dict[Any, tuple[datetime | None, bool]] = {}
    for student_id in student_ids:
        last = db.execute(
            select(LearningEvent.created_at)
            .where(
                LearningEvent.user_id == student_id,
                LearningEvent.event_type == "resource_view",
            )
            .order_by(LearningEvent.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        # created_at 非空，last 非 None ⟺ 有查阅历史，无需额外 count 查询
        stat_by_student[student_id] = (last, last is not None)
    return _pick_resource_idle_candidates(stat_by_student, name_by_id, now, idle_days)
