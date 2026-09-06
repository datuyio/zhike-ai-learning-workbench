"""遗忘风险预测：基于艾宾浩斯遗忘曲线的学生复习干预预测模型。

核心思想：记忆保持率 R = e^(-t/S)，其中 t 为距上次强化的天数，S 为记忆
稳定性。稳定性由掌握度、复习次数与近期学习活跃度共同决定——掌握度越高、
复习越充分、近期越活跃，遗忘越慢。系统据此为每个学生×知识点计算遗忘
风险，聚合到学生维度后向教师输出主动干预建议。
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import CourseConcept
from app.models.learning import ConceptMastery, LearningEvent
from app.models.ta_class import TaClass
from app.models.ta_class_student import TaClassStudent
from app.models.user import User

# 风险等级阈值：综合风险分达到该值即视为高/中遗忘风险
_HIGH_RISK_THRESHOLD = 65
_MEDIUM_RISK_THRESHOLD = 40
# 掌握度低于该值的知识点即使刚学过也视为需要巩固
_WEAK_MASTERY_THRESHOLD = 60
# 近期活跃度统计窗口（天）
_ACTIVITY_WINDOW_DAYS = 14


def _now() -> datetime:
    """返回当前 UTC 时间，便于测试时统一时区基准。"""
    return datetime.now(timezone.utc)


def _stability_days(mastery: float, review_count: int, activity_bonus: float) -> float:
    """记忆稳定性 S（天）：掌握度、复习次数与活跃度越高，遗忘速度越慢。"""
    return 1.5 + 0.12 * mastery + 0.5 * min(review_count, 8) + activity_bonus


def _retention(elapsed_days: float, stability: float) -> float:
    """艾宾浩斯保持率 R = e^(-t/S)，取值 (0, 1]。"""
    if stability <= 0:
        return 0.0
    return math.exp(-max(elapsed_days, 0.0) / stability)


def _risk_level(risk: float) -> str:
    """综合风险分映射为 high/medium/low 三级。"""
    if risk >= _HIGH_RISK_THRESHOLD:
        return "high"
    if risk >= _MEDIUM_RISK_THRESHOLD:
        return "medium"
    return "low"


def _review_suggestion(risk: float, elapsed_days: float, stability: float, concept_title: str) -> str:
    """根据保持率半衰期生成面向教师的复习干预建议文案。"""
    half_life = stability * math.log(2)
    if risk >= _HIGH_RISK_THRESHOLD:
        return f"「{concept_title}」遗忘风险高，建议 3 天内安排针对性复习或随堂小测。"
    if risk >= _MEDIUM_RISK_THRESHOLD:
        remain = max(0.0, half_life - elapsed_days)
        return f"「{concept_title}」进入遗忘爬坡期，建议约 {max(1, math.ceil(remain))} 天内安排一次巩固练习。"
    return f"「{concept_title}」记忆保持良好，可按正常教学节奏推进。"


def compute_forgetting_risk(db: Session, class_id: uuid.UUID) -> dict[str, Any]:
    """计算班级全体学生的遗忘风险，返回按风险降序排列的预测结果。

    参数:
        db: 数据库会话。
        class_id: 班级内部 UUID。

    返回:
        包含 class_id、generated_at、统计计数与学生风险明细的字典；
        学生明细含综合风险分、风险等级、最近活跃时间与 TOP 风险知识点。
    """
    now = _now()
    cls = db.get(TaClass, class_id)
    if cls is None:
        return {"class_id": str(class_id), "generated_at": now.isoformat(), "students": [],
                "high_count": 0, "medium_count": 0, "total_count": 0}

    student_ids = [
        m.student_id
        for m in db.execute(select(TaClassStudent).where(TaClassStudent.class_id == class_id)).scalars()
    ]
    if not student_ids:
        return {"class_id": str(class_id), "generated_at": now.isoformat(), "students": [],
                "high_count": 0, "medium_count": 0, "total_count": 0}

    names = {
        u.id: (u.display_name or str(u.id))
        for u in db.execute(select(User).where(User.id.in_(student_ids))).scalars()
    }

    # 掌握度记录：学生 × 知识点维度的遗忘预测基础
    mastery_stmt = select(ConceptMastery).where(ConceptMastery.user_id.in_(student_ids))
    if cls.course_id:
        mastery_stmt = mastery_stmt.where(ConceptMastery.course_id == cls.course_id)
    mastery_rows = db.execute(mastery_stmt).scalars().all()

    concept_ids = {r.concept_id for r in mastery_rows}
    titles = {
        c.id: c.title
        for c in db.execute(select(CourseConcept).where(CourseConcept.id.in_(concept_ids))).scalars()
    } if concept_ids else {}

    # 学习事件：用于复习次数、最近强化时间与近期活跃度
    window_start = now - timedelta(days=_ACTIVITY_WINDOW_DAYS)
    event_stmt = select(LearningEvent).where(
        LearningEvent.user_id.in_(student_ids),
        LearningEvent.created_at >= window_start - timedelta(days=_ACTIVITY_WINDOW_DAYS),
    )
    if cls.course_id:
        event_stmt = event_stmt.where(LearningEvent.course_id == cls.course_id)
    events = db.execute(event_stmt).scalars().all()

    last_event_by_user: dict[Any, datetime] = {}
    recent_count_by_user: dict[Any, int] = {}
    concept_event_count: dict[tuple[Any, Any], int] = {}
    concept_last_event: dict[tuple[Any, Any], datetime] = {}
    for ev in events:
        if ev.user_id is None:
            continue
        created = ev.created_at or now
        if created > last_event_by_user.get(ev.user_id, datetime.min.replace(tzinfo=timezone.utc)):
            last_event_by_user[ev.user_id] = created
        if created >= window_start:
            recent_count_by_user[ev.user_id] = recent_count_by_user.get(ev.user_id, 0) + 1
        if ev.concept_id is not None:
            key = (ev.user_id, ev.concept_id)
            concept_event_count[key] = concept_event_count.get(key, 0) + 1
            if created > concept_last_event.get(key, datetime.min.replace(tzinfo=timezone.utc)):
                concept_last_event[key] = created

    students: list[dict[str, Any]] = []
    for sid in student_ids:
        rows = [r for r in mastery_rows if r.user_id == sid]
        if not rows:
            continue
        # 近期活跃度奖励：窗口内事件越密集，稳定性越高（封顶 2 天）
        activity_bonus = min(recent_count_by_user.get(sid, 0) / _ACTIVITY_WINDOW_DAYS, 1.0) * 2.0
        concept_risks: list[dict[str, Any]] = []
        for row in rows:
            mastery = float(row.mastery or 0)
            key = (sid, row.concept_id)
            review_count = concept_event_count.get(key, 0)
            reinforced_at = max(
                row.updated_at or now,
                concept_last_event.get(key, datetime.min.replace(tzinfo=timezone.utc)),
            )
            elapsed_days = max((now - reinforced_at).total_seconds() / 86400.0, 0.0)
            stability = _stability_days(mastery, review_count, activity_bonus)
            retention = _retention(elapsed_days, stability)
            forgetting_risk = (1.0 - retention) * 100.0
            # 综合风险 = 遗忘概率为主、薄弱掌握度为辅；低掌握度知识点下限保护
            risk = 0.65 * forgetting_risk + 0.35 * (100.0 - mastery)
            if mastery < _WEAK_MASTERY_THRESHOLD:
                risk = max(risk, 100.0 - mastery)
            risk = round(min(max(risk, 0.0), 100.0))
            concept_risks.append({
                "concept_id": str(row.concept_id),
                "concept": titles.get(row.concept_id, "未知知识点"),
                "mastery": int(mastery),
                "days_since_practice": round(elapsed_days, 1),
                "retention": round(retention * 100),
                "risk": risk,
                "level": _risk_level(risk),
                "suggestion": _review_suggestion(risk, elapsed_days, stability, titles.get(row.concept_id, "该知识点")),
            })
        if not concept_risks:
            continue
        concept_risks.sort(key=lambda item: item["risk"], reverse=True)
        top = concept_risks[:3]
        # 学生综合风险：TOP3 风险知识点加权平均（最高风险权重更大）
        weights = [0.5, 0.3, 0.2]
        student_risk = round(sum(item["risk"] * w for item, w in zip(top, weights)))
        students.append({
            "student_id": str(sid),
            "student_name": names.get(sid, "未知"),
            "risk_score": student_risk,
            "level": _risk_level(student_risk),
            "last_active_at": last_event_by_user.get(sid).isoformat() if last_event_by_user.get(sid) else None,
            "recent_event_count": recent_count_by_user.get(sid, 0),
            "top_risk_concepts": top,
            "suggestion": top[0]["suggestion"] if top else "",
        })

    students.sort(key=lambda item: item["risk_score"], reverse=True)
    return {
        "class_id": str(class_id),
        "generated_at": now.isoformat(),
        "total_count": len(students),
        "high_count": sum(1 for s in students if s["level"] == "high"),
        "medium_count": sum(1 for s in students if s["level"] == "medium"),
        "students": students,
    }
