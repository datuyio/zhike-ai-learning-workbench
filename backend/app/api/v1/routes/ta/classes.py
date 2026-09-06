"""助教端：班级管理 + 学生管理。"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_ta
from ._shared import (
    TaClass,
    TaClassStudent,
    User,
    _apply_page,
    _get_or_404,
    _require_uuid,
    _user_internal_id,
    generate_class_invite_code,
)

router = APIRouter(prefix="/ta", tags=["ta-portal"])


class ClassUpdateRequest(BaseModel):
    """编辑班级请求体。"""
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    max_students: int | None = Field(default=None, ge=0)
    course_id: str | None = None


class ClassCreateRequest(BaseModel):
    """新建班级请求体，邀请码由服务端生成并返回。"""
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    course_id: str | None = None
    max_students: int | None = Field(default=None, ge=0)


def _new_class_invite_code(db: Session) -> str:
    """生成与现有班级不冲突的邀请码；极端冲突时重试并最终报错。"""
    for _ in range(10):
        code = generate_class_invite_code()
        exists = db.execute(select(TaClass).where(TaClass.invite_code == code)).scalar_one_or_none()
        if exists is None:
            return code
    raise HTTPException(status_code=500, detail="邀请码生成失败，请重试")


# ===== 班级管理 =====

@router.get("/classes")
async def list_classes(
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> list[dict[str, Any]]:
    """获取当前助教的班级列表。"""
    user_id = _user_internal_id(db, current_user.id)
    if user_id is None:
        return []
    stmt = select(TaClass).where(TaClass.ta_user_id == user_id, TaClass.is_active == True).order_by(TaClass.created_at.desc())
    stmt = _apply_page(stmt, limit, offset)
    classes = db.execute(stmt).scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "course_id": c.course_id,
            "student_count": len(c.students) if c.students else 0,
            "invite_code": c.invite_code,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in classes
    ]

@router.post("/classes")
async def create_class(
    payload: ClassCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """创建新班级：校验班级名后自动生成唯一邀请码。"""
    user_id = _user_internal_id(db, current_user.id)
    if user_id is None:
        raise HTTPException(status_code=403, detail="当前用户不存在")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="班级名称不能为空")
    cls = TaClass(
        name=name,
        description=payload.description,
        course_id=payload.course_id,
        max_students=payload.max_students,
        ta_user_id=user_id,
        invite_code=_new_class_invite_code(db),
    )
    db.add(cls)
    db.commit()
    db.refresh(cls)
    return {"id": cls.id, "name": cls.name, "invite_code": cls.invite_code, "message": "班级创建成功"}

@router.post("/classes/{class_id}/regenerate-code")
async def regenerate_class_code(
    class_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """重置班级邀请码：旧码立即失效，防止泄露后被继续使用。"""
    class_id_uuid = _require_uuid(class_id, "班级不存在")
    cls = db.get(TaClass, class_id_uuid)
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    if not cls.is_active:
        raise HTTPException(status_code=400, detail="班级已停用")
    cls.invite_code = _new_class_invite_code(db)
    db.commit()
    db.refresh(cls)
    return {"id": str(cls.id), "invite_code": cls.invite_code, "message": "邀请码已重置"}

@router.put("/classes/{class_id}")
async def update_class(
    class_id: str,
    payload: ClassUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """编辑班级信息；容量上限不得低于当前在班人数。"""
    cls = _get_or_404(db, TaClass, class_id, "班级不存在")
    if not cls.is_active:
        raise HTTPException(status_code=400, detail="班级已停用")
    current_count = len(cls.students) if cls.students else 0
    if payload.max_students is not None and payload.max_students < current_count:
        raise HTTPException(status_code=400, detail=f"容量上限不能低于当前在班人数 {current_count}")
    if payload.name is not None:
        cls.name = payload.name
    if payload.description is not None:
        cls.description = payload.description
    if payload.max_students is not None:
        cls.max_students = payload.max_students
    if payload.course_id is not None:
        cls.course_id = payload.course_id
    db.commit()
    db.refresh(cls)
    return {"id": str(cls.id), "name": cls.name, "message": "班级已更新"}

@router.delete("/classes/{class_id}")
async def delete_class(
    class_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, str]:
    """删除班级（软删除）；班内仍有学生时拒绝删除，避免关联数据悬空。"""
    cls = _get_or_404(db, TaClass, class_id, "班级不存在")
    if cls.students:
        raise HTTPException(status_code=400, detail="班内仍有学生，请先移除全部学生后再删除")
    cls.is_active = False
    db.commit()
    return {"message": "班级已删除"}

@router.post("/classes/{class_id}/students/{student_id}")
async def add_student(
    class_id: str, student_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, str]:
    """添加学生到班级；校验班级存在/容量上限/是否已加入，避免重复与超员。"""
    class_id_uuid = _require_uuid(class_id, "班级不存在")
    student_uuid = _user_internal_id(db, student_id)
    if student_uuid is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    cls = db.get(TaClass, class_id_uuid)
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    if not cls.is_active:
        raise HTTPException(status_code=400, detail="班级已停用")
    if cls.max_students is not None and len(cls.students) >= cls.max_students:
        raise HTTPException(status_code=400, detail="班级人数已达上限")
    existing = db.execute(
        select(TaClassStudent).where(
            TaClassStudent.class_id == class_id_uuid,
            TaClassStudent.student_id == student_uuid,
        )
    ).scalar_one_or_none()
    if existing:
        return {"message": "学生已在班级中"}
    membership = TaClassStudent(class_id=class_id_uuid, student_id=student_uuid)
    db.add(membership)
    db.commit()
    return {"message": "学生已加入班级"}

@router.delete("/classes/{class_id}/students/{student_id}")
async def remove_student(
    class_id: str, student_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, str]:
    """从班级移除学生。"""
    class_id_uuid = _require_uuid(class_id, "班级不存在")
    student_uuid = _user_internal_id(db, student_id)
    if student_uuid is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    stmt = select(TaClassStudent).where(
        TaClassStudent.class_id == class_id_uuid,
        TaClassStudent.student_id == student_uuid,
    )
    membership = db.execute(stmt).scalar_one_or_none()
    if membership:
        db.delete(membership)
        db.commit()
    return {"message": "学生已移除"}

@router.get("/classes/{class_id}/students")
async def list_students(
    class_id: str,
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> list[dict[str, Any]]:
    """查看班级学生列表（批量预取用户信息，避免逐条查询的 N+1）。"""
    class_id_uuid = _require_uuid(class_id, "班级不存在")
    stmt = select(TaClassStudent).where(TaClassStudent.class_id == class_id_uuid).order_by(TaClassStudent.joined_at)
    stmt = _apply_page(stmt, limit, offset)
    members = db.execute(stmt).scalars().all()
    student_ids = [m.student_id for m in members]
    users = db.execute(select(User).where(User.id.in_(student_ids))).scalars().all() if student_ids else []
    user_by_id = {u.id: u for u in users}
    return [
        {
            "student_id": m.student_id,
            "name": user_by_id[m.student_id].display_name if m.student_id in user_by_id else "未知",
            "email": user_by_id[m.student_id].email if m.student_id in user_by_id else None,
            "joined_at": m.joined_at.isoformat() if m.joined_at else None,
        }
        for m in members
    ]
