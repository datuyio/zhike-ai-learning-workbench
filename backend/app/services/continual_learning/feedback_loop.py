"""AI 反馈闭环：教师对 AI 输出进行 1-5 星评分与文字反馈，持续优化模型表现。

反馈数据一方面沉淀为评分统计与趋势，另一方面转化为"校准提示"注入后续
生成链路（教案、批改、诊断建议等），实现"教师反馈 → 系统校准 → 输出改进"
的持续学习闭环；低分反馈与阶段性校准都会写入进化日志。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.continual_learning import ContinualAiFeedback
from app.services.continual_learning.evolution_log import record_evolution

# 各 AI 输出类型的中文标签与默认改进方向，用于生成校准提示
_TARGET_META: dict[str, dict[str, str]] = {
    "lesson_plan": {"label": "AI 教案", "improve": "强化教学目标可测性与教学过程可操作性，减少空泛表述"},
    "grading": {"label": "AI 批改", "improve": "评语应更具体，指出错因并给出可执行的改进示例"},
    "advice": {"label": "AI 诊断建议", "improve": "建议应更聚焦可落地的课堂动作与分层策略"},
    "resource": {"label": "AI 资源生成", "improve": "资源应更贴合课程知识点与难度梯度"},
}
# 低分阈值：低于等于该评分视为负面反馈
_NEGATIVE_RATING = 2
# 每累计该数量反馈触发一次阶段性校准进化事件
_CALIBRATION_BATCH = 5
# 校准提示最少反馈样本数，样本过少不生成提示避免过拟合
_MIN_SAMPLES_FOR_HINT = 2


def record_feedback(
    db: Session,
    *,
    ta_user_id: uuid.UUID,
    target_type: str,
    rating: int,
    comment: str | None = None,
    target_id: str | None = None,
    course_id: uuid.UUID | None = None,
    class_id: uuid.UUID | None = None,
) -> ContinualAiFeedback:
    """记录一条教师反馈，并按规则触发进化日志。

    参数:
        db: 数据库会话。
        ta_user_id: 提交反馈的助教用户 ID。
        target_type: 被评价的 AI 输出类型（lesson_plan/grading/advice/resource）。
        rating: 1-5 星评分，调用方需保证范围。
        comment: 文字反馈，可选。
        target_id: 被评价对象标识，可选。
        course_id / class_id: 关联课程/班级，可选。

    返回:
        已写入的反馈模型实例。
    """
    feedback = ContinualAiFeedback(
        ta_user_id=ta_user_id,
        course_id=course_id,
        class_id=class_id,
        target_type=target_type,
        target_id=target_id,
        rating=rating,
        comment=comment.strip() if comment and comment.strip() else None,
    )
    db.add(feedback)
    db.flush()

    label = _TARGET_META.get(target_type, {"label": target_type})["label"]
    if rating <= _NEGATIVE_RATING:
        # 低分反馈立即进入进化日志，提醒系统该输出类型需要校准
        record_evolution(
            db,
            event_type="negative_feedback",
            title=f"收到{label}低分反馈（{rating} 星）",
            detail=feedback.comment or "教师认为该输出质量不佳，已纳入校准队列。",
            metrics={"target_type": target_type, "rating": rating},
        )
    total = db.execute(
        select(ContinualAiFeedback).where(ContinualAiFeedback.target_type == target_type)
    ).scalars().all()
    if len(total) % _CALIBRATION_BATCH == 0:
        avg = round(sum(f.rating for f in total) / len(total), 2)
        record_evolution(
            db,
            event_type="feedback_calibration",
            title=f"{label}反馈阶段性校准（累计 {len(total)} 条）",
            detail=f"累计反馈 {len(total)} 条，平均 {avg} 星；校准提示已更新并注入后续生成链路。",
            metrics={"target_type": target_type, "count": len(total), "avg_rating": avg},
        )
    return feedback


def feedback_summary(db: Session) -> dict[str, Any]:
    """聚合全部教师反馈，输出统计、分布、按类型均值、周趋势与最近反馈。"""
    rows = db.execute(select(ContinualAiFeedback).order_by(ContinualAiFeedback.created_at.desc())).scalars().all()
    distribution = {i: 0 for i in range(1, 6)}
    for f in rows:
        if 1 <= f.rating <= 5:
            distribution[f.rating] += 1

    by_type: dict[str, list[int]] = {}
    for f in rows:
        by_type.setdefault(f.target_type, []).append(f.rating)
    type_stats = [
        {
            "target_type": key,
            "label": _TARGET_META.get(key, {"label": key})["label"],
            "count": len(ratings),
            "avg_rating": round(sum(ratings) / len(ratings), 2),
        }
        for key, ratings in sorted(by_type.items())
    ]

    # 近 8 周评分趋势：用于展示模型表现随反馈持续改进的轨迹
    now = datetime.now(timezone.utc)
    trend: list[dict[str, Any]] = []
    for week in range(7, -1, -1):
        start = now - timedelta(days=(week + 1) * 7)
        end = now - timedelta(days=week * 7)
        bucket = [f.rating for f in rows if f.created_at and start <= f.created_at < end]
        trend.append({
            "week": f"W-{week}" if week else "本周",
            "avg_rating": round(sum(bucket) / len(bucket), 2) if bucket else None,
            "count": len(bucket),
        })

    return {
        "total": len(rows),
        "avg_rating": round(sum(f.rating for f in rows) / len(rows), 2) if rows else 0,
        "distribution": distribution,
        "by_target_type": type_stats,
        "rating_trend": trend,
        "recent": [
            {
                "id": str(f.id),
                "target_type": f.target_type,
                "label": _TARGET_META.get(f.target_type, {"label": f.target_type})["label"],
                "rating": f.rating,
                "comment": f.comment,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in rows[:10]
        ],
    }


def calibration_hints(db: Session) -> list[str]:
    """根据历史反馈生成注入生成链路的校准提示（规则化，样本过少不输出）。"""
    rows = db.execute(select(ContinualAiFeedback)).scalars().all()
    by_type: dict[str, list[ContinualAiFeedback]] = {}
    for f in rows:
        by_type.setdefault(f.target_type, []).append(f)

    hints: list[str] = []
    for target_type, items in by_type.items():
        if len(items) < _MIN_SAMPLES_FOR_HINT:
            continue
        avg = sum(f.rating for f in items) / len(items)
        if avg >= 4.0:
            continue
        meta = _TARGET_META.get(target_type, {"label": target_type, "improve": "结合教师反馈持续优化输出质量"})
        low_comments = [f.comment for f in items if f.comment and f.rating <= 3][:2]
        hint = f"教师反馈校准：{meta['label']}近期平均 {round(avg, 1)} 星，{meta['improve']}。"
        if low_comments:
            hint += "教师意见：" + "；".join(low_comments) + "。"
        hints.append(hint)
    return hints
