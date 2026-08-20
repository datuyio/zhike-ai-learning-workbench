from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser, ensure_course_access, get_current_user
from app.schemas.recommendation import PushListResponse
from app.services.recommendation.adaptive_push import AdaptivePushService

router = APIRouter()


@router.get("/push", response_model=PushListResponse)
async def get_adaptive_push(
    course_id: str | None = Query(default=None, description="按课程过滤推送；为空时看全局画像"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PushListResponse:
    """获取当前登录用户的自适应推送列表。

    聚合画像驱动、评分驱动、时间驱动三条规则，返回按优先级排序的个性化推送。
    """
    if course_id:
        ensure_course_access(db, current_user, course_id)
    items = AdaptivePushService(db).get_push_list(user_id=current_user.id, course_id=course_id)
    return PushListResponse(items=items, total=len(items))