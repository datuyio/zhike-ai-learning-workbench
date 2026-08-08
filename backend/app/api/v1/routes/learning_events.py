from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.schemas.learning_event import (
    LearningEventCreate,
    LearningEventDimension,
    LearningEventOut,
    LearningEventStatsOut,
)
from app.services.learning.learning_behavior import LearningBehaviorService

router = APIRouter()


@router.post("/events", response_model=LearningEventOut, status_code=status.HTTP_201_CREATED)
async def record_learning_event(
    payload: LearningEventCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningEventOut:
    """采集当前登录用户的一条学习行为事件。

    登录态的 external_id 会解析为 users.id 写入 student_id；
    event_data 与 session_id 合并写入 event_metadata(JSONB)。
    """
    service = LearningBehaviorService(db)
    student_id = service.resolve_student_id(current_user.id)
    if not student_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="当前用户不存在，无法采集事件")
    event = service.record_event(
        student_id=student_id,
        course_id=payload.course_id,
        event_type=payload.event_type,
        event_data=payload.event_data,
        session_id=payload.session_id,
    )
    return LearningEventOut.model_validate(event, from_attributes=True)


@router.get("/events/stats", response_model=LearningEventStatsOut)
async def get_learning_event_stats(
    dimension: LearningEventDimension = Query(default="day", description="聚合维度：day/week/course"),
    course_id: str | None = Query(default=None, description="按课程 ID 过滤"),
    start_date: datetime | None = Query(default=None, description="起始时间（含），ISO 8601"),
    end_date: datetime | None = Query(default=None, description="结束时间（含），ISO 8601"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningEventStatsOut:
    """获取当前登录用户的学习行为事件聚合统计。

    默认维度为 day，默认时间范围为最近 30 天（当 start_date/end_date 均未提供时）。
    """
    service = LearningBehaviorService(db)
    student_id = service.resolve_student_id(current_user.id)
    if not student_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="当前用户不存在，无法统计事件")

    range_start, range_end = start_date, end_date
    if range_start is None and range_end is None:
        range_start, range_end = service.default_range()

    result = service.aggregate(
        student_id=student_id,
        dimension=dimension,
        course_id=course_id,
        start_date=range_start,
        end_date=range_end,
    )
    return LearningEventStatsOut.model_validate(result)
