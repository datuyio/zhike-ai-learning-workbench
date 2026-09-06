"""持续学习中心 API：遗忘风险预测、错误模式识别、AI 反馈闭环、进化日志与画像趋势。

该路由承载"持续学习与遗忘风险预测"独创亮点的全部后端入口，
所有接口仅助教（ta/admin）角色可访问。
"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_ta
from app.models.ta_class import TaClass
from app.models.user import User
from app.services.continual_learning import (
    compute_forgetting_risk,
    feedback_summary,
    list_evolution,
    profile_trend_series,
    record_evolution,
    record_feedback,
    top_error_patterns,
)

router = APIRouter(prefix="/ta/continual", tags=["continual-learning"])

logger = logging.getLogger(__name__)

# 反馈目标类型白名单：与前端评分组件的可选类型保持一致
_VALID_TARGET_TYPES = ("lesson_plan", "grading", "advice", "resource")


class ContinualFeedbackRequest(BaseModel):
    """教师对 AI 输出的评分反馈请求体。"""

    target_type: str = Field(description="AI 输出类型：lesson_plan/grading/advice/resource")
    rating: int = Field(ge=1, le=5, description="1-5 星评分")
    comment: str | None = Field(default=None, max_length=1000)
    target_id: str | None = Field(default=None, max_length=160)
    course_id: str | None = None
    class_id: str | None = None


def _parse_uuid(value: str, detail: str) -> uuid.UUID:
    """安全解析 UUID，非法输入统一返回 404 语义错误。"""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=404, detail=detail)


def _user_internal_id(db: Session, user_id_ref: str) -> uuid.UUID | None:
    """按 external_id 或内部 UUID 解析用户内部 UUID，兼容两种形态。"""
    user = db.execute(select(User).where(User.external_id == user_id_ref)).scalar_one_or_none()
    if user:
        return user.id
    try:
        candidate = uuid.UUID(user_id_ref)
    except (ValueError, TypeError, AttributeError):
        return None
    return candidate if db.get(User, candidate) else None


@router.get("/forgetting-risk")
def forgetting_risk(
    class_id: str = Query(..., description="班级 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """遗忘风险预测：基于学习事件频率与掌握度变化趋势，识别需要复习的学生。"""
    class_uuid = _parse_uuid(class_id, "班级不存在")
    return compute_forgetting_risk(db, class_uuid)


@router.get("/error-patterns")
def error_patterns(
    class_id: str = Query(..., description="班级 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """错误模式识别：返回班级历史易错点 TOP3，供教案生成与教学决策使用。"""
    class_uuid = _parse_uuid(class_id, "班级不存在")
    return {"class_id": class_id, "patterns": top_error_patterns(db, class_uuid)}


@router.post("/feedback")
def submit_feedback(
    payload: ContinualFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """AI 反馈闭环入口：教师提交 1-5 星评分与文字反馈，驱动系统持续校准。"""
    if payload.target_type not in _VALID_TARGET_TYPES:
        raise HTTPException(status_code=422, detail="不支持的反馈目标类型")
    ta_user_id = _user_internal_id(db, current_user.id)
    if ta_user_id is None:
        raise HTTPException(status_code=403, detail="当前用户不存在")
    course_uuid = _parse_uuid(payload.course_id, "课程不存在") if payload.course_id else None
    class_uuid = _parse_uuid(payload.class_id, "班级不存在") if payload.class_id else None
    record_feedback(
        db,
        ta_user_id=ta_user_id,
        target_type=payload.target_type,
        rating=payload.rating,
        comment=payload.comment,
        target_id=payload.target_id,
        course_id=course_uuid,
        class_id=class_uuid,
    )
    db.commit()
    return {"message": "反馈已记录，系统将据此持续校准 AI 输出", "ok": True}


@router.get("/feedback/summary")
def get_feedback_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """反馈统计：总量、均值、分布、按类型均值、周趋势与最近反馈列表。"""
    return feedback_summary(db)


@router.get("/evolution")
def get_evolution_log(
    limit: int = Query(default=60, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """进化日志：系统学习行为演变历史，供可视化进化轨迹展示。"""
    return {"events": list_evolution(db, limit=limit)}


@router.get("/profile-trends")
def get_profile_trends(
    student_id: str = Query(..., description="学生 ID"),
    course_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """画像趋势分析：跨时间维度重建学生画像各维度评分轨迹。"""
    student_uuid = _parse_uuid(student_id, "学生不存在")
    course_uuid = _parse_uuid(course_id, "课程不存在") if course_id else None
    return profile_trend_series(db, student_uuid, course_uuid)


@router.post("/refresh")
def refresh_continual(
    class_id: str = Query(..., description="班级 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """触发一次持续学习进化：重算遗忘风险与易错点，并写入进化日志。

    该接口把"预测 → 记录 → 可视化"串成闭环：每次刷新都会把本轮量化指标
    沉淀为进化事件，前端时间线即可呈现系统学习行为的演变轨迹。
    """
    class_uuid = _parse_uuid(class_id, "班级不存在")
    cls = db.get(TaClass, class_uuid)
    if cls is None:
        raise HTTPException(status_code=404, detail="班级不存在")

    risk = compute_forgetting_risk(db, class_uuid)
    record_evolution(
        db,
        event_type="risk_recalibrated",
        title=f"遗忘风险模型重算（{cls.name}）",
        detail=(
            f"本轮识别高风险学生 {risk['high_count']} 人、中风险 {risk['medium_count']} 人，"
            "已为教师生成主动复习干预建议。"
        ),
        metrics={
            "class_id": str(class_uuid),
            "total": risk["total_count"],
            "high": risk["high_count"],
            "medium": risk["medium_count"],
        },
    )

    patterns = top_error_patterns(db, class_uuid)
    if patterns:
        record_evolution(
            db,
            event_type="error_patterns_updated",
            title=f"历史易错点更新（{cls.name}）",
            detail="、".join(p["concept"] for p in patterns) + " 被列为本轮 TOP 易错点，将注入教案生成。",
            metrics={"class_id": str(class_uuid), "top": [p["concept"] for p in patterns]},
        )
    db.commit()
    return {
        "message": "持续学习进化完成",
        "risk": risk,
        "patterns": patterns,
    }
