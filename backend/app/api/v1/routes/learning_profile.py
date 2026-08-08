from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser, ensure_course_access, get_current_user
from app.schemas.onboarding import PresetChipSubmitRequest, PresetChipSubmitResponse
from app.schemas.profile import (
    LearningProfileQueryScope,
    LearningProfileResponseDTO,
    ProfileCorrectionRequest,
    ProfileCorrectionResponse,
    ProfileEvidenceListResponse,
)
from app.services.onboarding.service import OnboardingService
from app.services.profile.repository import LearningProfileRepository

router = APIRouter()


@router.get("", response_model=LearningProfileResponseDTO)
async def get_learning_profile(
    scope: LearningProfileQueryScope = Query(default="all"),
    course_id: str | None = Query(default=None),
    conversation_id: str | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningProfileResponseDTO:
    """读取当前用户的多层学习画像。"""
    if course_id:
        ensure_course_access(db, current_user, course_id)
    return LearningProfileRepository(db).get_learning_profile(
        user_external_id=current_user.id,
        scope=scope,
        course_id=course_id,
        conversation_id=conversation_id,
    )


@router.get("/evidence", response_model=ProfileEvidenceListResponse)
async def list_profile_evidence(
    dimension: str | None = Query(default=None, description="按维度键过滤，如 mastery_level、learning_style"),
    source_type: str | None = Query(default=None, description="按来源过滤：conversation/assessment/user_correction/resource_usage"),
    scope: str | None = Query(default=None, description="按作用域过滤：global/course/session"),
    course_id: str | None = Query(default=None, description="按课程 ID 过滤"),
    start_date: datetime | None = Query(default=None, description="起始时间（含），ISO 8601"),
    end_date: datetime | None = Query(default=None, description="结束时间（含），ISO 8601"),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数，1-100"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileEvidenceListResponse:
    """查询当前用户的画像证据链列表。

    支持按维度、来源、作用域、课程和时间范围过滤并分页，
    用于画像详情页的证据链 Tab 展示。返回结构化证据：
    证据来源、时间戳、内容摘要、置信度。
    """
    if course_id:
        ensure_course_access(db, current_user, course_id)
    result = LearningProfileRepository(db).list_evidence(
        user_external_id=current_user.id,
        dimension=dimension,
        source_type=source_type,
        scope=scope,
        course_id=course_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return ProfileEvidenceListResponse.model_validate(result, from_attributes=True)


@router.post("/corrections", response_model=ProfileCorrectionResponse)
async def correct_learning_profile(
    payload: ProfileCorrectionRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileCorrectionResponse:
    """提交用户画像纠偏。"""
    if payload.course_id:
        ensure_course_access(db, current_user, payload.course_id)
    return LearningProfileRepository(db).apply_correction(user_external_id=current_user.id, payload=payload)


@router.post("/onboarding/submit-chip", response_model=PresetChipSubmitResponse)
async def submit_preset_chip(
    payload: PresetChipSubmitRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PresetChipSubmitResponse:
    """预设 chip 直写：不走 LLM，直接写入画像维度并返回下一轮模板话术。"""
    service = OnboardingService(db)
    return service.apply_preset_chip(
        user_external_id=current_user.id,
        chip=payload.chip,
        round_num=payload.round,
        history=payload.history,
    )
