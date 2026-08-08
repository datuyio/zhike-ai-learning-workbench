from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


LearningProfileScope = Literal["global", "course", "session", "cross_course"]
LearningProfileQueryScope = Literal["all", "global", "course", "session", "cross_course"]


class ProfileEvidenceDTO(BaseModel):
    """画像证据的前端返回结构。"""

    id: str
    scope: LearningProfileScope
    course_id: str | None = None
    conversation_id: str | None = None
    dimension: str
    label: str | None = None
    source_type: str
    source_id: str | None = None
    summary: str
    confidence_delta: float = 0.0
    created_at: str | None = None
    status: str = "active"


class ProfileEvidenceListMeta(BaseModel):
    """证据链分页元信息。"""

    page: int = 1
    page_size: int = 20
    total: int = 0


class ProfileEvidenceListResponse(BaseModel):
    """画像证据链列表响应，支持按维度/来源/时间范围过滤与分页。"""

    items: list[ProfileEvidenceDTO] = Field(default_factory=list)
    meta: ProfileEvidenceListMeta = Field(default_factory=ProfileEvidenceListMeta)


class ProfileDimensionDTO(BaseModel):
    """画像维度的前端返回结构。"""

    key: str
    name: str
    score: int
    label: str
    confidence: float
    evidence: list[ProfileEvidenceDTO | dict | str] = Field(default_factory=list)
    scope: LearningProfileScope
    updated_at: str | None = None
    evidence_summary: str | None = None
    source_type: str | None = None


class GlobalLearningProfileDTO(BaseModel):
    """全局画像。"""

    scope: Literal["global"] = "global"
    summary: str = ""
    confidence: float = 0.0
    dimensions: list[ProfileDimensionDTO] = Field(default_factory=list)
    major: str | None = None
    long_term_goals: list[str] = Field(default_factory=list)
    resource_preferences: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class CourseLearningProfileDTO(BaseModel):
    """课程画像。"""

    scope: Literal["course"] = "course"
    course_id: str
    course_title: str | None = None
    summary: str = ""
    confidence: float = 0.0
    dimensions: list[ProfileDimensionDTO] = Field(default_factory=list)
    current_node: str | None = None
    mastery: float | None = None
    weak_points: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class SessionLearningProfileDTO(BaseModel):
    """最近会话画像。"""

    scope: Literal["session"] = "session"
    conversation_id: str | None = None
    topic: str | None = None
    intent: str | None = None
    temporary_goal: str | None = None
    summary: str = ""
    dimensions: list[ProfileDimensionDTO] = Field(default_factory=list)
    updated_at: str | None = None


class CrossCourseLearningProfileDTO(BaseModel):
    """跨课程画像。"""

    scope: Literal["cross_course"] = "cross_course"
    summary: str = ""
    common_weaknesses: list[str] = Field(default_factory=list)
    transfer_hints: list[str] = Field(default_factory=list)
    prerequisite_alerts: list[str] = Field(default_factory=list)
    dimensions: list[ProfileDimensionDTO] = Field(default_factory=list)
    updated_at: str | None = None


class LearningProfileResponseDTO(BaseModel):
    """多层画像聚合响应。"""

    user_id: str | None = None
    active_course_id: str | None = None
    global_profile: GlobalLearningProfileDTO = Field(alias="global")
    course: CourseLearningProfileDTO | None = None
    session: SessionLearningProfileDTO | None = None
    cross_course: CrossCourseLearningProfileDTO | None = None

    model_config = {"populate_by_name": True}


class ProfileCorrectionRequest(BaseModel):
    """用户纠偏请求。"""

    scope: LearningProfileScope
    dimension_key: str
    action: Literal["update_dimension", "mark_inaccurate", "suppress_evidence", "clear_evidence"] = "update_dimension"
    label: str | None = Field(default=None, max_length=120)
    summary: str | None = Field(default=None, max_length=500)
    score: int | None = Field(default=None, ge=0, le=100)
    course_id: str | None = None
    conversation_id: str | None = None
    evidence_id: str | None = None


class ProfileCorrectionResponse(BaseModel):
    """用户纠偏响应。"""

    status: str
    scope: LearningProfileScope
    dimension_key: str
    evidence_id: str | None = None
