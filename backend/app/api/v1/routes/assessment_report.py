from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.schemas.assessment_report import LearningReportResponse
from app.services.assessment.learning_report import LearningReportService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/report", response_model=LearningReportResponse, summary="获取学习效果评估报告")
def get_learning_report(
    user_id: str | None = Query(default=None, description="目标用户 external_id；不传则默认当前登录用户"),
    course_id: str | None = Query(default=None, description="可选课程 ID，过滤指定课程维度的评估数据"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> LearningReportResponse:
    """聚合学习行为、画像、测验评分和资源使用数据，生成学习效果评估报告。

    普通用户只能查看自己的报告；当指定其他用户的 user_id 时，要求调用方具备
    管理员或助教角色，避免越权读取他人学习数据。
    """
    # 未显式指定时，默认评估当前登录用户
    target_user_id = user_id or current_user.id

    # 越权保护：查询他人报告需管理员或助教权限
    if target_user_id != current_user.id and current_user.role not in ("admin", "ta"):
        raise HTTPException(status_code=403, detail="无权查看其他用户的学习评估报告")

    service = LearningReportService(db)
    return service.get_report(user_id=target_user_id, course_id=course_id)