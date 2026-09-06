"""画像趋势分析：跨时间维度追踪学情画像变化，支持教学决策。

基于画像证据链（ProfileEvidence 的 delta 增量记录）按时间顺序重建各维度
评分的演变序列，使教师能看到每个画像维度"如何一步步变成现在这样"，
与证据链追踪能力互为印证。
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.learning import ProfileEvidence

# 维度评分重建基线：证据链只记录增量，需约定中性起点
_BASELINE_SCORE = 50
# 评分上下限，与画像维度 0-100 分值约定保持一致
_SCORE_MIN = 0
_SCORE_MAX = 100


def profile_trend_series(
    db: Session,
    user_id: uuid.UUID,
    course_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """重建学生画像各维度的时间序列，返回趋势数据与当前值。

    参数:
        db: 数据库会话。
        user_id: 学生内部 UUID。
        course_id: 课程内部 UUID；为空时聚合该学生全部课程证据。

    返回:
        包含 student_id 与 dimensions 列表的字典；每个维度含 key、label、
        current（当前评分）与 series（按时间升序的 {date, score} 序列）。
    """
    stmt = (
        select(ProfileEvidence)
        .where(ProfileEvidence.user_id == user_id)
        .order_by(ProfileEvidence.created_at.asc())
    )
    if course_id is not None:
        stmt = stmt.where(ProfileEvidence.course_id == course_id)
    rows = db.execute(stmt).scalars().all()

    # 按维度分组后依时间顺序累加增量，重建评分轨迹
    state: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = state.setdefault(row.dimension_key, {
            "key": row.dimension_key,
            "label": row.dimension_key,
            "score": _BASELINE_SCORE,
            "series": [],
        })
        if row.label:
            entry["label"] = row.label
        entry["score"] = max(_SCORE_MIN, min(_SCORE_MAX, entry["score"] + (row.delta or 0)))
        entry["series"].append({
            "date": row.created_at.date().isoformat() if row.created_at else "",
            "score": entry["score"],
        })

    dimensions = []
    for entry in state.values():
        # 序列过长时按天取最后一个采样点，控制前端渲染数据量
        by_day: dict[str, int] = {}
        for point in entry["series"]:
            by_day[point["date"]] = point["score"]
        entry["series"] = [{"date": d, "score": s} for d, s in by_day.items()]
        dimensions.append({
            "key": entry["key"],
            "label": entry["label"],
            "current": entry["score"],
            "series": entry["series"],
        })
    dimensions.sort(key=lambda item: item["key"])
    return {"student_id": str(user_id), "dimensions": dimensions}
