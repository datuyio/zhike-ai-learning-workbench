"""助教端公告通知路由：发布/列表/编辑/删除/置顶/撤回，支持多班级定向。"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_ta
from ._shared import (
    TaAnnouncement,
    TaClass,
    User,
    _apply_page,
    _class_student_ids,
    _create_notifications,
    _require_uuid,
    _user_internal_id,
)

router = APIRouter(prefix="/ta", tags=["ta-portal"])


class AnnouncementCreateRequest(BaseModel):
    """发布公告请求体。"""
    title: str
    body: str
    announcement_type: str = "general"
    class_id: str | None = None
    class_ids: list[str] | None = None


class AnnouncementUpdateRequest(BaseModel):
    """编辑公告请求体。"""
    title: str | None = Field(default=None, max_length=300)
    body: str | None = None
    announcement_type: str | None = Field(default=None, max_length=30)


def _normalize_announcement_class_ids(payload: AnnouncementCreateRequest) -> list[str]:
    """归一化公告目标班级：class_ids 优先，兼容旧单 class_id 字段，返回去重后的班级 id 字符串列表。

    返回空列表表示未指定班级（面向全体学生）。
    """
    if payload.class_ids:
        return list(dict.fromkeys(cid for cid in payload.class_ids if cid))
    if payload.class_id:
        return [payload.class_id]
    return []


@router.get("/announcements")
async def list_announcements(
    class_id: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> list[dict[str, Any]]:
    """公告列表（仅当前助教发布），可按目标班级过滤，置顶优先，再按发布时间倒序。"""
    user_id = _user_internal_id(db, current_user.id)
    if user_id is None:
        return []
    stmt = select(TaAnnouncement).where(TaAnnouncement.created_by == user_id)
    if class_id:
        class_id_uuid = _require_uuid(class_id, "班级不存在")
        stmt = stmt.where(TaAnnouncement.class_id == class_id_uuid)
    stmt = stmt.order_by(TaAnnouncement.is_pinned.desc(), TaAnnouncement.created_at.desc())
    stmt = _apply_page(stmt, limit, offset)
    announcements = db.execute(stmt).scalars().all()
    # 批量解析目标班级名，避免逐条查询
    class_ids = {a.class_id for a in announcements if a.class_id}
    class_name_by_id: dict[Any, str] = {}
    if class_ids:
        rows = db.execute(select(TaClass).where(TaClass.id.in_(class_ids))).scalars().all()
        class_name_by_id = {c.id: c.name for c in rows}
    return [
        {
            "id": str(a.id),
            "title": a.title,
            "body": a.body,
            "announcement_type": a.announcement_type,
            "class_id": str(a.class_id) if a.class_id else None,
            "class_name": class_name_by_id.get(a.class_id) if a.class_id else None,
            "created_by": str(a.created_by),
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "is_pinned": a.is_pinned,
            "is_active": a.is_active,
        }
        for a in announcements
    ]


@router.post("/announcements")
async def create_announcement(
    payload: AnnouncementCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """发布公告：可定向到指定班级（支持多选），未指定班级时面向全体学生。

    每个目标班级生成一条公告记录并定向通知该班学生，便于按班级独立置顶/撤回；
    同时校验班级归属，禁止向非本人管理的班级发布。
    """
    user_id = _user_internal_id(db, current_user.id)
    if user_id is None:
        raise HTTPException(status_code=403, detail="当前用户不存在")

    requested_class_ids = _normalize_announcement_class_ids(payload)
    # 解析并校验目标班级：必须存在且归属当前助教；None 表示全体学生
    target_class_ids: list[uuid.UUID | None]
    if not requested_class_ids:
        target_class_ids = [None]
    else:
        target_class_ids = []
        for cid in requested_class_ids:
            class_uuid = _require_uuid(cid, "目标班级不存在")
            cls = db.get(TaClass, class_uuid)
            if not cls:
                raise HTTPException(status_code=404, detail="目标班级不存在")
            if cls.ta_user_id != user_id:
                raise HTTPException(status_code=403, detail="只能向自己管理的班级发布公告")
            target_class_ids.append(class_uuid)

    created: list[str] = []
    for class_uuid in target_class_ids:
        announcement = TaAnnouncement(
            title=payload.title,
            body=payload.body,
            announcement_type=payload.announcement_type,
            class_id=class_uuid,
            created_by=user_id,
        )
        db.add(announcement)
        db.flush()
        if class_uuid:
            student_ids = _class_student_ids(db, class_uuid)
        else:
            student_ids = [
                u.id for u in db.execute(
                    select(User).where(User.role_code == "student")
                ).scalars().all()
            ]
        _create_notifications(
            db,
            student_ids,
            title=payload.title,
            body=payload.body,
            notification_type="announcement",
            source_type="announcement",
            source_id=str(announcement.id),
            class_id=class_uuid,
        )
        created.append(str(announcement.id))

    db.commit()
    return {
        "ids": created,
        "id": created[0] if created else None,
        "title": payload.title,
        "count": len(created),
        "message": "公告发布成功",
    }


@router.delete("/announcements/{announcement_id}")
async def delete_announcement(
    announcement_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, str]:
    """删除公告：仅允许删除本人发布的公告，否则 403。"""
    announcement_id_uuid = _require_uuid(announcement_id, "公告不存在")
    announcement = db.get(TaAnnouncement, announcement_id_uuid)
    if not announcement:
        raise HTTPException(status_code=404, detail="公告不存在")
    user_id = _user_internal_id(db, current_user.id)
    if user_id is None or announcement.created_by != user_id:
        raise HTTPException(status_code=403, detail="只能删除自己发布的公告")
    if not announcement.is_active:
        raise HTTPException(status_code=403, detail="公告已撤回，无法删除")
    db.delete(announcement)
    db.commit()
    return {"message": "公告已删除"}


@router.put("/announcements/{announcement_id}")
async def update_announcement(
    announcement_id: str,
    payload: AnnouncementUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """编辑公告：仅本人发布且未撤回可编辑。"""
    announcement_id_uuid = _require_uuid(announcement_id, "公告不存在")
    announcement = db.get(TaAnnouncement, announcement_id_uuid)
    if not announcement:
        raise HTTPException(status_code=404, detail="公告不存在")
    user_id = _user_internal_id(db, current_user.id)
    if user_id is None or announcement.created_by != user_id:
        raise HTTPException(status_code=403, detail="只能编辑自己发布的公告")
    if not announcement.is_active:
        raise HTTPException(status_code=403, detail="公告已撤回，无法编辑")
    if payload.title is not None:
        announcement.title = payload.title
    if payload.body is not None:
        announcement.body = payload.body
    if payload.announcement_type is not None:
        announcement.announcement_type = payload.announcement_type
    db.commit()
    return {"id": str(announcement.id), "message": "公告已更新"}


@router.post("/announcements/{announcement_id}/pin")
async def toggle_pin_announcement(
    announcement_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """置顶/取消置顶切换。"""
    announcement_id_uuid = _require_uuid(announcement_id, "公告不存在")
    announcement = db.get(TaAnnouncement, announcement_id_uuid)
    if not announcement:
        raise HTTPException(status_code=404, detail="公告不存在")
    user_id = _user_internal_id(db, current_user.id)
    if user_id is None or announcement.created_by != user_id:
        raise HTTPException(status_code=403, detail="只能操作自己发布的公告")
    if not announcement.is_active:
        raise HTTPException(status_code=403, detail="公告已撤回，无法置顶")
    announcement.is_pinned = not announcement.is_pinned
    db.commit()
    return {
        "id": str(announcement.id),
        "is_pinned": announcement.is_pinned,
        "message": "公告已置顶" if announcement.is_pinned else "公告已取消置顶",
    }


@router.post("/announcements/{announcement_id}/withdraw")
async def withdraw_announcement(
    announcement_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, str]:
    """撤回公告（软删除，保留历史）。"""
    announcement_id_uuid = _require_uuid(announcement_id, "公告不存在")
    announcement = db.get(TaAnnouncement, announcement_id_uuid)
    if not announcement:
        raise HTTPException(status_code=404, detail="公告不存在")
    user_id = _user_internal_id(db, current_user.id)
    if user_id is None or announcement.created_by != user_id:
        raise HTTPException(status_code=403, detail="只能撤回自己发布的公告")
    if not announcement.is_active:
        return {"message": "公告已撤回"}
    announcement.is_active = False
    db.commit()
    return {"message": "公告已撤回"}
