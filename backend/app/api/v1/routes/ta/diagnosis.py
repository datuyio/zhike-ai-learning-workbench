"""助教端学情诊断路由：班级概览/对比/趋势/热力图/进度/薄弱点/建议，学生画像与雷达。"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_ta
from app.services.model_gateway.errors import ModelGatewayBudgetLimitError
from app.services.ta.ai_cache import get_cached_ai, set_cached_ai
from app.services.resource.quiz_contract import load_quiz_json_object
from ._shared import (
    Assessment,
    ConceptMastery,
    CourseConcept,
    LearningEvent,
    TaAlertRecord,
    TaClass,
    TaClassStudent,
    TaGradingRecord,
    User,
    _MASTERY_WEAK_THRESHOLD,
    _RADAR_ACTIVITY_CAP,
    _RADAR_RESOURCE_CAP,
    _class_mastery_rows,
    _class_student_ids,
    _course_slug,
    _require_uuid,
    _user_internal_id,
    _weakness_severity,
    get_trace_id,
    logger,
)

router = APIRouter(prefix="/ta", tags=["ta-portal"])


def _avg_mastery_per_student(rows: list[Any]) -> dict[Any, int]:
    """按学生聚合 concept_mastery 平均掌握度，返回 {user_id: 四舍五入整数}。"""
    sums: dict[Any, list[float]] = {}
    for row in rows:
        sums.setdefault(row.user_id, []).append(row.mastery)
    return {
        student_id: round(sum(values) / len(values))
        for student_id, values in sums.items()
    }


def _build_compare_rows(
    class_metrics_list: list[dict[str, Any]],
    sort_by: str = "avg_mastery",
    top_n: int = 20,
) -> list[dict[str, Any]]:
    """班级对比行聚合：归一化均分、按指定指标降序、截断 top_n。"""
    rows: list[dict[str, Any]] = []
    for m in class_metrics_list:
        rows.append({
            "class_id": str(m["class_id"]),
            "name": m["name"],
            "avg_score": round(m["avg_score"], 1),
            "avg_mastery": m["avg_mastery"],
            "weak_points": m["weak_points"],
            "active_students": m["active_students"],
            "student_count": m["student_count"],
        })
    rows.sort(key=lambda r: r[sort_by], reverse=True)
    return rows[:top_n]


def _build_trend_series(
    days: int,
    score_by_day: dict[str, tuple[float, int]],
    event_by_day: dict[str, int],
    today: date | None = None,
) -> list[dict[str, Any]]:
    """按 days 天窗口补全逐日序列：score 为该日得分率均值（无数据 None），event_count 为该日事件数（默认 0）。"""
    today = today or datetime.now(timezone.utc).date()
    series: list[dict[str, Any]] = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        score_sum, count = score_by_day.get(day, (0.0, 0))
        series.append({
            "date": day,
            "score": round(score_sum / count, 1) if count else None,
            "event_count": event_by_day.get(day, 0),
        })
    return series


def _compute_heatmap_matrix(rows: list[tuple[Any, Any, float]]) -> dict[str, Any]:
    """(student_id, concept_id, mastery) 原始行 → 规范化 students × concepts 掌握度矩阵，缺值补 0。"""
    students = sorted({str(r[0]) for r in rows})
    concepts = sorted({str(r[1]) for r in rows})
    value_by_cell = {(str(r[0]), str(r[1])): r[2] for r in rows}
    return {
        "students": students,
        "concepts": concepts,
        "matrix": [
            [value_by_cell.get((sid, cid), 0) for cid in concepts]
            for sid in students
        ],
    }


def _suggested_practice(weak_rate: float) -> int:
    """薄弱率越高建议练习量越大，钳制在 [3, 10] 次区间。"""
    return max(3, min(10, round(weak_rate * 12)))


def _aggregate_weak_points(
    mastery_rows: list[tuple[Any, float]],
    title_by_id: dict[Any, str],
    threshold: int = _MASTERY_WEAK_THRESHOLD,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """班级薄弱知识点聚合：按知识点算平均掌握度、低掌握学生数与强度分级。

    mastery_rows 为 (concept_id, mastery) 原始对；weak_rate = 1 - 平均掌握度 / 100。
    返回按 weak_rate 降序、截断 top_n 条的结果，附 severity 与建议练习量。
    """
    agg: dict[Any, list[float]] = {}
    for concept_id, mastery in mastery_rows:
        agg.setdefault(concept_id, []).append(mastery)
    result: list[dict[str, Any]] = []
    for concept_id, mastery_list in agg.items():
        avg = sum(mastery_list) / len(mastery_list)
        weak_count = sum(1 for m in mastery_list if m < threshold)
        weak_rate = round(1 - avg / 100, 2)
        result.append({
            "concept_id": str(concept_id),
            "concept": title_by_id.get(concept_id, str(concept_id)),
            "weak_rate": weak_rate,
            "student_count": weak_count,
            "severity": _weakness_severity(avg),
            "suggested_practice": _suggested_practice(weak_rate),
        })
    result.sort(key=lambda item: item["weak_rate"], reverse=True)
    return result[:top_n]


def _aggregate_class_metrics(
    mastery_rows: list[tuple[Any, float]],
    student_count: int,
) -> dict[str, Any]:
    """从 concept_mastery 真实数据聚合班级可验证指标（统计先行，供 LLM 润色与规则降级复用）。"""
    if not mastery_rows:
        return {
            "student_count": student_count, "concepts_total": 0, "avg_mastery": 0,
            "weak_concepts": 0, "weak_rate": 0.0, "mastered_ratio": 0.0,
        }
    avg_by_concept: dict[Any, list[float]] = {}
    for concept_id, mastery in mastery_rows:
        avg_by_concept.setdefault(concept_id, []).append(mastery)
    concept_avgs = {cid: sum(v) / len(v) for cid, v in avg_by_concept.items()}
    avg_mastery = sum(concept_avgs.values()) / len(concept_avgs)
    weak_count = sum(1 for value in concept_avgs.values() if value < _MASTERY_WEAK_THRESHOLD)
    mastered_count = sum(1 for value in concept_avgs.values() if value >= _MASTERY_WEAK_THRESHOLD)
    return {
        "student_count": student_count,
        "concepts_total": len(concept_avgs),
        "avg_mastery": round(avg_mastery),
        "weak_concepts": weak_count,
        "weak_rate": round(1 - avg_mastery / 100, 2),
        "mastered_ratio": round(mastered_count / len(concept_avgs), 2) if concept_avgs else 0.0,
    }


def _top_weak_concepts(
    mastery_rows: list[tuple[Any, float]],
    title_by_id: dict[Any, str],
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """聚合最弱的 top_n 知识点（含标题与平均掌握度），作为诊断建议的优先级参考。"""
    if not mastery_rows:
        return []
    avg_by_concept: dict[Any, list[float]] = {}
    for concept_id, mastery in mastery_rows:
        avg_by_concept.setdefault(concept_id, []).append(mastery)
    ranked = sorted(
        (
            {
                "concept_id": str(concept_id),
                "concept": title_by_id.get(concept_id, str(concept_id)),
                "avg_mastery": round(sum(values) / len(values)),
            }
            for concept_id, values in avg_by_concept.items()
        ),
        key=lambda item: item["avg_mastery"],
    )
    return ranked[:top_n]


def _diagnosis_messages(
    metrics: dict[str, Any],
    priority_concepts: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """构造班级诊断建议 prompt，只把可验证指标交给 LLM 撰写文案。"""
    priority_text = "\n".join(
        f"- {item['concept']}（平均掌握度 {item['avg_mastery']}%）" for item in priority_concepts
    ) or "无"
    return [
        {"role": "system", "content": "你是课程助教，擅长基于量化指标撰写班级学情诊断建议。只输出 JSON 对象，不要 Markdown 或解释。"},
        {"role": "user", "content": (
            f"班级掌握度指标：\n"
            f"- 学生数 {metrics['student_count']}\n"
            f"- 知识点总数 {metrics['concepts_total']}\n"
            f"- 平均掌握度 {metrics['avg_mastery']}%\n"
            f"- 薄弱知识点数（<{_MASTERY_WEAK_THRESHOLD}%）{metrics['weak_concepts']}\n"
            f"- 整体薄弱率 {metrics['weak_rate']}\n\n"
            f"需要优先关注的知识点：\n{priority_text}\n\n"
            '请输出 JSON：{"summary": "一段班级学情总结（1-3 句）", "suggestions": ["建议1", "建议2", "建议3"]}'
        )},
    ]


# 模板占位文案：模型若照抄示例而未生成真实内容，解析时视为失败并交由规则降级
_TEMPLATE_SUMMARY_MARKER = "一段班级学情总结"
_TEMPLATE_SUGGESTION_RE = re.compile(r"^建议\s*\d+$")


def _parse_diagnosis_text(raw: str) -> dict[str, Any] | None:
    """从 LLM 输出解析班级诊断建议 JSON（summary/suggestions），失败返回 None 供降级。

    除校验字段类型外，还过滤模型照抄模板占位文案（如「建议1」「一段班级学情总结」）的情况，
    避免把未生成的占位内容当作有效建议展示给教师。
    """
    candidates: list[Any] = []
    try:
        candidates.append(json.loads((raw or "").strip()))
    except Exception:
        pass
    candidates.append(load_quiz_json_object(raw))
    for data in candidates:
        if not isinstance(data, dict):
            continue
        summary = data.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            continue
        summary = summary.strip()
        # 总结仍为模板占位文案时，说明模型未真正生成内容，走规则降级
        if _TEMPLATE_SUMMARY_MARKER in summary:
            continue
        suggestions_raw = data.get("suggestions", [])
        suggestions: list[str] = []
        if isinstance(suggestions_raw, list):
            for item in suggestions_raw:
                if not isinstance(item, str):
                    continue
                text = item.strip()
                # 过滤空串与照抄模板的占位建议（建议1/建议2/建议3）
                if not text or _TEMPLATE_SUGGESTION_RE.fullmatch(text):
                    continue
                suggestions.append(text)
        return {"summary": summary, "suggestions": suggestions}
    return None


def _diagnosis_fallback(
    metrics: dict[str, Any],
    priority_concepts: list[dict[str, Any]],
) -> dict[str, Any]:
    """无 LLM 时的规则化诊断文案，保证链路可用。"""
    if not metrics["concepts_total"]:
        return {"summary": "该班级暂无掌握度数据，暂无法生成诊断建议。", "suggestions": []}
    priority_names = "、".join(item["concept"] for item in priority_concepts[:3]) or "暂无"
    summary = (
        f"班级共 {metrics['student_count']} 名学生，覆盖 {metrics['concepts_total']} 个知识点，"
        f"平均掌握度约 {metrics['avg_mastery']}%，其中 {metrics['weak_concepts']} 个知识点低于 "
        f"{_MASTERY_WEAK_THRESHOLD}% 阈值。"
    )
    suggestions = [
        f"优先巩固知识点：{priority_names}。",
        "对低于阈值的知识点安排针对性练习与课堂回顾。",
        "关注长期无学习记录的学生，及时提醒并跟进。",
    ]
    return {"summary": summary, "suggestions": suggestions}


def _build_student_radar_dimensions(
    *,
    assessment_scores: list[float],    # 测验分（0-100）
    mastery_values: list[float],       # 概念掌握度（0-100），测验缺失时兜底
    homework_ratios: list[float],      # 已批作业得分率（0-1）
    resource_view_count: int,          # 窗口内 resource_view 事件数
    total_event_count: int,            # 窗口内全部学习事件数
    active_days: int,                  # 窗口内活跃天数
    period_days: int,                  # 窗口天数
    resource_cap: int = _RADAR_RESOURCE_CAP,
    activity_cap: int = _RADAR_ACTIVITY_CAP,
) -> list[dict[str, Any]]:
    """计算学生雷达五维评分（0-100 整数），返回 [{key,label,score,source}]。

    测验表现：测验分平均优先，缺失回退概念掌握度平均；作业质量：已批得分率平均。
    资料查阅/学习活跃度/学习持续性 由学习事件统计，按封顶归一化。
    维度全部无数据时返回 source="no_data"、score=0。
    """
    dimensions: list[dict[str, Any]] = []

    # 测验表现
    if assessment_scores:
        quiz_score = round(sum(assessment_scores) / len(assessment_scores))
        quiz_source = "assessment"
    elif mastery_values:
        quiz_score = round(sum(mastery_values) / len(mastery_values))
        quiz_source = "mastery_fallback"
    else:
        quiz_score = 0
        quiz_source = "no_data"
    dimensions.append({"key": "quiz", "label": "测验表现", "score": quiz_score, "source": quiz_source})

    # 作业质量
    if homework_ratios:
        clamped = [max(0.0, min(r, 1.0)) for r in homework_ratios]
        homework_score = round(sum(clamped) / len(clamped) * 100)
        homework_source = "grading"
    else:
        homework_score = 0
        homework_source = "no_data"
    dimensions.append({"key": "homework", "label": "作业质量", "score": homework_score, "source": homework_source})

    # 事件类三轴：资料查阅 / 学习活跃度 / 学习持续性
    if total_event_count > 0:
        resource_score = round(min(resource_view_count / resource_cap, 1.0) * 100)
        activity_score = round(min(total_event_count / activity_cap, 1.0) * 100)
        consistency_score = round(min(active_days / period_days, 1.0) * 100) if period_days > 0 else 0
        event_source = "events"
    else:
        resource_score = activity_score = consistency_score = 0
        event_source = "no_data"
    dimensions.append({"key": "resource", "label": "资料查阅", "score": resource_score, "source": event_source})
    dimensions.append({"key": "activity", "label": "学习活跃度", "score": activity_score, "source": event_source})
    dimensions.append({"key": "consistency", "label": "学习持续性", "score": consistency_score, "source": event_source})

    return dimensions


@router.get("/diagnosis/class/{class_id}")
async def class_diagnosis(
    class_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """班级学情概览：学生列表带姓名与平均掌握度。"""
    class_id_uuid = _require_uuid(class_id, "班级不存在")
    cls = db.get(TaClass, class_id_uuid)
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    members = db.execute(
        select(TaClassStudent).where(TaClassStudent.class_id == class_id_uuid)
    ).scalars().all()
    student_ids = [m.student_id for m in members]
    students: list[dict[str, Any]] = []
    if student_ids:
        mastery_rows = _class_mastery_rows(db, cls, student_ids)
        avg_by_student = _avg_mastery_per_student(mastery_rows)
        users = db.execute(select(User).where(User.id.in_(student_ids))).scalars().all()
        name_by_id = {u.id: (u.display_name or str(u.id)) for u in users}
        for sid in student_ids:
            students.append({
                "student_id": str(sid),
                "name": name_by_id.get(sid, "未知"),
                "avg_mastery": avg_by_student.get(sid, 0),
            })
    return {"class_id": str(class_id_uuid), "student_count": len(student_ids), "students": students}


@router.get("/diagnosis/classes/compare")
async def classes_compare(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> list[dict[str, Any]]:
    """班级横向对比：均分/平均掌握度/薄弱点数/活跃学生数，按平均掌握度降序。"""
    user_id = _user_internal_id(db, current_user.id)
    if user_id is None:
        return []
    classes = db.execute(
        select(TaClass).where(TaClass.ta_user_id == user_id, TaClass.is_active == True)
    ).scalars().all()
    metrics_list: list[dict[str, Any]] = []
    since = datetime.now(timezone.utc) - timedelta(days=7)
    for cls in classes:
        student_ids = _class_student_ids(db, cls.id)
        base = {
            "class_id": cls.id, "name": cls.name,
            "avg_score": 0.0, "avg_mastery": 0, "weak_points": 0,
            "active_students": 0, "student_count": len(student_ids),
        }
        if not student_ids:
            metrics_list.append(base)
            continue
        mastery_rows = _class_mastery_rows(db, cls, student_ids)
        metrics = _aggregate_class_metrics(
            [(r.concept_id, r.mastery) for r in mastery_rows], len(student_ids)
        )
        grade_rows = db.execute(
            select(TaGradingRecord).where(
                TaGradingRecord.class_id == cls.id,
                TaGradingRecord.status == "graded",
                TaGradingRecord.score.isnot(None),
            )
        ).scalars().all()
        avg_score = sum(float(r.score) for r in grade_rows) / len(grade_rows) if grade_rows else 0.0
        active = db.execute(
            select(LearningEvent.user_id)
            .where(
                LearningEvent.user_id.in_(student_ids),
                LearningEvent.created_at >= since,
            )
            .distinct()
        ).scalars().all()
        base.update({
            "avg_score": avg_score,
            "avg_mastery": metrics["avg_mastery"],
            "weak_points": metrics["weak_concepts"],
            "active_students": len(active),
        })
        metrics_list.append(base)
    return _build_compare_rows(metrics_list)


@router.get("/diagnosis/student/{student_id}/trend")
async def student_trend(
    student_id: str,
    days: int = Query(default=30, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """学生纵向趋势：近 days 天逐日得分率（测验分 + 已批作业分）与活跃事件数。"""
    student_id_uuid = _require_uuid(student_id, "学生不存在")
    since = datetime.now(timezone.utc) - timedelta(days=days)
    assessment_scores = db.execute(
        select(Assessment.created_at, Assessment.score)
        .where(Assessment.user_id == student_id_uuid, Assessment.created_at >= since)
    ).all()
    grading_rows = db.execute(
        select(TaGradingRecord.created_at, TaGradingRecord.score, TaGradingRecord.total_score)
        .where(
            TaGradingRecord.student_id == student_id_uuid,
            TaGradingRecord.status == "graded",
            TaGradingRecord.score.isnot(None),
            TaGradingRecord.created_at >= since,
        )
    ).all()
    ratios_by_day: dict[str, list[float]] = {}
    for created_at, score in assessment_scores:
        day = created_at.astimezone(timezone.utc).date().isoformat()
        ratios_by_day.setdefault(day, []).append(float(score) / 100.0)
    for created_at, score, total in grading_rows:
        day = created_at.astimezone(timezone.utc).date().isoformat()
        max_score = float(total) if total else 100.0
        ratios_by_day.setdefault(day, []).append(float(score) / max_score)
    score_by_day = {
        day: (sum(values), len(values))
        for day, values in ratios_by_day.items()
    }
    event_rows = db.execute(
        select(LearningEvent.created_at)
        .where(LearningEvent.user_id == student_id_uuid, LearningEvent.created_at >= since)
    ).scalars().all()
    event_by_day: dict[str, int] = {}
    for created_at in event_rows:
        day = created_at.astimezone(timezone.utc).date().isoformat()
        event_by_day[day] = event_by_day.get(day, 0) + 1
    return {
        "student_id": str(student_id_uuid),
        "period_days": days,
        "trend": _build_trend_series(days, score_by_day, event_by_day),
    }


@router.get("/diagnosis/class/{class_id}/heatmap")
async def class_heatmap(
    class_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """全班 × 知识点掌握度矩阵（缺值补 0，供前端热力图）。"""
    class_id_uuid = _require_uuid(class_id, "班级不存在")
    cls = db.get(TaClass, class_id_uuid)
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    student_ids = _class_student_ids(db, class_id_uuid)
    if not student_ids:
        return {"students": [], "concepts": [], "matrix": []}
    mastery_rows = _class_mastery_rows(db, cls, student_ids)
    return _compute_heatmap_matrix([(r.user_id, r.concept_id, r.mastery) for r in mastery_rows])


@router.get("/diagnosis/class/{class_id}/progress")
async def class_progress(
    class_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """班级整体学习进度：平均掌握度、知识点覆盖与近 7 天活跃学生数。"""
    class_id_uuid = _require_uuid(class_id, "班级不存在")
    cls = db.get(TaClass, class_id_uuid)
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    student_ids = _class_student_ids(db, class_id_uuid)
    if not student_ids:
        return {
            "class_id": str(class_id_uuid), "student_count": 0,
            "avg_mastery": 0,
            "concept_progress": {"concepts_total": 0, "concepts_mastered": 0},
            "active_students": 0,
        }

    mastery_rows = _class_mastery_rows(db, cls, student_ids)
    avg_mastery = round(sum(r.mastery for r in mastery_rows) / len(mastery_rows)) if mastery_rows else 0
    concept_ids = {r.concept_id for r in mastery_rows}
    mastered_ids = {r.concept_id for r in mastery_rows if r.mastery >= _MASTERY_WEAK_THRESHOLD}

    since = datetime.now(timezone.utc) - timedelta(days=7)
    active_students = db.execute(
        select(LearningEvent.user_id)
        .where(
            LearningEvent.user_id.in_(student_ids),
            LearningEvent.created_at >= since,
        )
        .distinct()
    ).scalars().all()

    return {
        "class_id": str(class_id_uuid),
        "student_count": len(student_ids),
        "avg_mastery": avg_mastery,
        "concept_progress": {
            "concepts_total": len(concept_ids),
            "concepts_mastered": len(mastered_ids),
        },
        "active_students": len(active_students),
    }


@router.get("/diagnosis/class/{class_id}/activity-trend")
async def class_activity_trend(
    class_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """班级活跃度趋势：近 14 天按天聚合学习事件数（缺天补 0）。"""
    class_id_uuid = _require_uuid(class_id, "班级不存在")
    cls = db.get(TaClass, class_id_uuid)
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    student_ids = _class_student_ids(db, class_id_uuid)
    if not student_ids:
        return {"trend": []}

    since = datetime.now(timezone.utc) - timedelta(days=13)
    event_times = db.execute(
        select(LearningEvent.created_at)
        .where(
            LearningEvent.user_id.in_(student_ids),
            LearningEvent.created_at >= since,
        )
    ).scalars().all()
    counts: dict[str, int] = {}
    for created_at in event_times:
        day = created_at.astimezone(timezone.utc).date().isoformat()
        counts[day] = counts.get(day, 0) + 1

    today = datetime.now(timezone.utc).date()
    trend = []
    for offset in range(13, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        trend.append({"date": day, "event_count": counts.get(day, 0)})
    return {"trend": trend}


@router.get("/diagnosis/class/{class_id}/weak-points")
async def class_weak_points(
    class_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> list[dict[str, Any]]:
    """班级薄弱知识点识别：基于 concept_mastery 真实掌握度聚合，weak_rate=1-平均掌握度/100。"""
    class_id_uuid = _require_uuid(class_id, "班级不存在")
    cls = db.get(TaClass, class_id_uuid)
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    student_ids = _class_student_ids(db, class_id_uuid)
    if not student_ids:
        return []

    mastery_rows = _class_mastery_rows(db, cls, student_ids)

    concept_ids = {r.concept_id for r in mastery_rows}
    concepts = (
        db.execute(select(CourseConcept).where(CourseConcept.id.in_(concept_ids))).scalars().all()
        if concept_ids else []
    )
    title_by_id = {c.id: c.title for c in concepts}

    return _aggregate_weak_points([(r.concept_id, r.mastery) for r in mastery_rows], title_by_id)


@router.post("/diagnosis/class/{class_id}/advice")
async def class_diagnosis_advice(
    class_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """班级诊断建议（统计先行 + LLM 润色）。

    可验证的指标与优先级知识点均由真实掌握度数据计算得出，LLM 仅负责撰写总结与建议，
    避免模型编造数据；LLM 不可用时降级为规则化文案（source=fallback）。
    """
    class_id_uuid = _require_uuid(class_id, "班级不存在")
    cls = db.get(TaClass, class_id_uuid)
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    student_ids = _class_student_ids(db, class_id_uuid)
    if not student_ids:
        return {
            "class_id": str(class_id_uuid),
            "metrics": _aggregate_class_metrics([], 0),
            "priority_concepts": [],
            "summary": "班级暂无学生，无法生成诊断建议。",
            "suggestions": [],
            "source": "fallback",
        }
    mastery_rows = _class_mastery_rows(db, cls, student_ids)
    mastery_pairs = [(r.concept_id, r.mastery) for r in mastery_rows]
    metrics = _aggregate_class_metrics(mastery_pairs, len(student_ids))
    concept_ids = {r.concept_id for r in mastery_rows}
    concepts = (
        db.execute(select(CourseConcept).where(CourseConcept.id.in_(concept_ids))).scalars().all()
        if concept_ids else []
    )
    title_by_id = {c.id: c.title for c in concepts}
    priority_concepts = _top_weak_concepts(mastery_pairs, title_by_id)

    summary: str
    suggestions: list[str]
    source: str
    try:
        from app.services.model_gateway.router import ModelGateway

        messages = _diagnosis_messages(metrics, priority_concepts)
        raw_answer = await get_cached_ai("diagnosis-advice", messages)
        cache_hit = raw_answer is not None
        if not cache_hit:
            result = await ModelGateway(db).complete_chat(
                messages=messages,
                course_slug=_course_slug(db, cls.course_id),
                agent_name="TaDiagnosisAgent",
                temperature=0.3,
                max_tokens=800,
                json_mode=True,
            )
            raw_answer = result.answer or ""
        parsed = _parse_diagnosis_text(raw_answer)
        if parsed is None:
            raise ValueError("诊断 JSON 解析失败")
        if not cache_hit:
            await set_cached_ai("diagnosis-advice", messages, raw_answer)
        summary = parsed["summary"]
        suggestions = parsed["suggestions"]
        source = "llm"
    except ModelGatewayBudgetLimitError:
        raise
    except Exception as exc:
        logger.warning(
            "班级诊断建议降级为规则文案：class=%s error=%s trace_id=%s",
            class_id, str(exc)[:200], get_trace_id(), exc_info=True,
        )
        fallback = _diagnosis_fallback(metrics, priority_concepts)
        summary = fallback["summary"]
        suggestions = fallback["suggestions"]
        source = "fallback"

    return {
        "class_id": str(class_id_uuid),
        "metrics": metrics,
        "priority_concepts": priority_concepts,
        "summary": summary,
        "suggestions": suggestions,
        "source": source,
    }


@router.get("/diagnosis/student/{student_id}")
async def student_diagnosis(
    student_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """学生个体画像诊断：学习事件时间线、预警与弱知识点。"""
    student_id_uuid = _require_uuid(student_id, "学生不存在")
    events = db.execute(
        select(LearningEvent)
        .where(LearningEvent.user_id == student_id_uuid)
        .order_by(LearningEvent.created_at.desc()).limit(20)
    ).scalars().all()
    alerts = db.execute(
        select(TaAlertRecord).where(
            TaAlertRecord.student_id == student_id_uuid,
            TaAlertRecord.resolved == False,
        )
    ).scalars().all()
    # 弱知识点：该生 concept_mastery 掌握度低于阈值
    weak_rows = db.execute(
        select(ConceptMastery).where(
            ConceptMastery.user_id == student_id_uuid,
            ConceptMastery.mastery < _MASTERY_WEAK_THRESHOLD,
        )
    ).scalars().all()
    weak_concept_ids = {r.concept_id for r in weak_rows}
    weak_concepts = (
        db.execute(select(CourseConcept).where(CourseConcept.id.in_(weak_concept_ids))).scalars().all()
        if weak_concept_ids else []
    )
    weak_title_by_id = {c.id: c.title for c in weak_concepts}
    return {
        "student_id": str(student_id_uuid),
        "recent_events": [
            {"type": e.event_type, "course_id": e.course_id,
             "time": e.created_at.isoformat() if e.created_at else None}
            for e in events
        ],
        "active_alerts": len(alerts),
        "alerts": [
            {"title": a.title, "severity": a.severity, "type": a.alert_type}
            for a in alerts
        ],
        "weak_concepts": [
            {
                "concept_id": str(r.concept_id),
                "concept": weak_title_by_id.get(r.concept_id, str(r.concept_id)),
                "mastery": r.mastery,
            }
            for r in weak_rows
        ],
    }


@router.get("/diagnosis/student/{student_id}/radar")
async def student_radar(
    student_id: str,
    days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """学生个体学习雷达：测验/作业/资料查阅/活跃度/持续性五维评分（0-100）。"""
    student_id_uuid = _require_uuid(student_id, "学生不存在")
    student = db.get(User, student_id_uuid)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # 测验分（窗口内）与概念掌握度（兜底，不限窗口）
    assessments = db.execute(
        select(Assessment).where(Assessment.user_id == student_id_uuid, Assessment.created_at >= since)
    ).scalars().all()
    mastery_rows = db.execute(
        select(ConceptMastery).where(ConceptMastery.user_id == student_id_uuid)
    ).scalars().all()

    # 已批作业得分率（评分是累积成果，不限窗口）
    graded_records = db.execute(
        select(TaGradingRecord).where(
            TaGradingRecord.student_id == student_id_uuid,
            TaGradingRecord.status == "graded",
            TaGradingRecord.score.is_not(None),
        )
    ).scalars().all()

    # 学习事件（窗口内）：资料查阅数 / 总数 / 活跃天数
    events = db.execute(
        select(LearningEvent).where(LearningEvent.user_id == student_id_uuid, LearningEvent.created_at >= since)
    ).scalars().all()
    resource_view_count = sum(1 for e in events if e.event_type == "resource_view")
    active_days = len({e.created_at.astimezone(timezone.utc).date() for e in events})

    dimensions = _build_student_radar_dimensions(
        assessment_scores=[float(a.score) for a in assessments],
        mastery_values=[float(m.mastery) for m in mastery_rows],
        homework_ratios=[r.score / (r.total_score or 100) for r in graded_records],
        resource_view_count=resource_view_count,
        total_event_count=len(events),
        active_days=active_days,
        period_days=days,
    )
    return {
        "student_id": str(student_id_uuid),
        "period_days": days,
        "dimensions": dimensions,
        "meta": {
            "total_events": len(events),
            "graded_homework": len(graded_records),
            "assessment_count": len(assessments),
            "mastery_count": len(mastery_rows),
        },
    }
