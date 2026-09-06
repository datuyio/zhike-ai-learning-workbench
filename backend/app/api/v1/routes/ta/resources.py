"""助教端资源审核路由：复用 ResourceRepository，仅做薄封装与错误映射。"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_ta
from app.schemas.resource import ResourceReviewRequest
from app.services.resource.repository import ResourceRepository
from ._shared import User

router = APIRouter(prefix="/ta", tags=["ta-portal"])


class ResourceRejectRequest(BaseModel):
    """驳回资源请求体。"""
    comment: str | None = None


@router.get("/resources/pending")
async def pending_resources(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> list[dict[str, Any]]:
    """待审核资源列表。"""
    return ResourceRepository(db).list_review_queue(None, "pending_review")


@router.post("/resources/{resource_id}/approve")
async def approve_resource(
    resource_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """审核通过资源。"""
    return _apply_resource_review(db, resource_id, {"action": "approve"}, current_user.id)


@router.post("/resources/{resource_id}/reject")
async def reject_resource(
    resource_id: str,
    payload: ResourceRejectRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """驳回资源并附审核评语。"""
    body = payload or ResourceRejectRequest()
    return _apply_resource_review(db, resource_id, {"action": "reject", "comment": body.comment}, current_user.id)


def _apply_resource_review(
    db: Session,
    resource_id: str,
    payload: dict[str, Any],
    reviewer_id: str,
) -> dict[str, Any]:
    """执行资源审核动作的薄封装：复用 ResourceRepository，统一 400/404 错误映射。"""
    try:
        result = ResourceRepository(db).review_resource(resource_id, ResourceReviewRequest(**payload), reviewer_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="资源不存在或已删除")
    return result
