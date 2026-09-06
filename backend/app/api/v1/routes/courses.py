from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser, ensure_course_access, get_current_user
from app.schemas.course import (
    Course,
    CourseConceptOutlineResponse,
    CourseListResponse,
    CurrentCourseResponse,
    CurrentCourseUpdate,
    CurrentCourseUpdateResponse,
    UserCourseListResponse,
)
from app.schemas.knowledge_cloud import CoursesWithKnowledgeResponse
from app.services.course.repository import CourseRepository
from app.services.knowledge.repository import KnowledgeRepository

router = APIRouter()


@router.get("/me/courses", response_model=UserCourseListResponse)
async def my_courses(current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> UserCourseListResponse:
    """返回当前用户可访问的课程列表。"""
    return UserCourseListResponse(user=current_user.name, items=CourseRepository(db).list_courses(current_user.id))


@router.get("/courses", response_model=CourseListResponse)
async def list_courses(db: Session = Depends(get_db)) -> CourseListResponse:
    """返回已发布课程列表。"""
    return CourseListResponse(items=CourseRepository(db).list_courses())


@router.get("/courses/with-knowledge", response_model=CoursesWithKnowledgeResponse)
async def courses_with_knowledge(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CoursesWithKnowledgeResponse:
    """返回当前用户可访问且已具备可检索知识库的课程。"""
    return CoursesWithKnowledgeResponse.model_validate(
        KnowledgeRepository(db).get_courses_with_knowledge(current_user.id)
    )


@router.get("/courses/{course_id}", response_model=Course)
async def get_course(course_id: str, db: Session = Depends(get_db)) -> Course:
    """返回单个课程详情。"""
    course = CourseRepository(db).get_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在或已被删除")
    return Course.model_validate(course)


@router.get("/me/current-course", response_model=CurrentCourseResponse)
async def get_current_course(current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> CurrentCourseResponse:
    """返回当前用户选中的课程。"""
    return CurrentCourseResponse(course_id=CourseRepository(db).get_current_course(current_user.id))


@router.put("/me/current-course", response_model=CurrentCourseUpdateResponse)
async def update_current_course(
    payload: CurrentCourseUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentCourseUpdateResponse:
    """更新当前用户选中的课程。"""
    repository = CourseRepository(db)
    course = repository.get_course(payload.course_id)
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在或已被删除")
    if current_user.role == "admin":
        course_id = repository.set_current_course(current_user.id, payload.course_id)
    else:
        if course.get("status") != "published":
            raise HTTPException(status_code=403, detail="当前课程暂不可选择")
        course_id = repository.self_select_course(current_user.id, payload.course_id)
    return CurrentCourseUpdateResponse(course_id=course_id, message="当前课程已更新")


@router.get("/courses/{course_id}/concepts", response_model=CourseConceptOutlineResponse)
async def list_concepts(course_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> CourseConceptOutlineResponse:
    """返回当前课程的知识点和章节大纲。"""
    ensure_course_access(db, current_user, course_id)
    return CourseConceptOutlineResponse.model_validate(CourseRepository(db).list_concepts_outline(course_id))
