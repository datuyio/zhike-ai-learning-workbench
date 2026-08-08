from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import (
    ConceptMastery,
    Conversation,
    Course,
    CourseConcept,
    CourseProfile,
    LearningPath,
    Message,
    PathNode,
    ProfileDimension,
    ProfileEvidence,
    User,
    UserProfile,
    UserSetting,
)
from app.schemas.profile import (
    CourseLearningProfileDTO,
    CrossCourseLearningProfileDTO,
    GlobalLearningProfileDTO,
    LearningProfileResponseDTO,
    ProfileCorrectionRequest,
    ProfileCorrectionResponse,
    ProfileDimensionDTO,
    ProfileEvidenceDTO,
    SessionLearningProfileDTO,
)
from app.services.profile.extractor import ExtractedDimension, ProfileExtractor


GLOBAL_DIMENSION_NAMES: dict[str, str] = {
    "major_background": "专业背景",
    "knowledge_base": "知识基础",
    "cognitive_style": "认知风格",
    "learning_goal": "学习目标",
    "learning_pace": "学习节奏",
    "resource_preference": "资源偏好",
    "general_weakness": "通用能力短板",
    "weakness": "通用能力短板",
    "expression_preference": "表达偏好",
    "learning_habit": "学习习惯",
}

COURSE_DIMENSION_NAMES: dict[str, str] = {
    "knowledge_base": "知识基础",
    "knowledge_mastery": "课程掌握度",
    "current_node": "当前节点",
    "weakness": "易错点",
    "error_pattern": "易错点",
    "learning_goal": "课程学习目标",
    "resource_preference": "资源偏好",
    "path_status": "路径状态",
    "assessment": "测评表现",
    "transfer": "迁移能力",
}

SESSION_DIMENSION_NAMES: dict[str, str] = {
    "session_topic": "当前主题",
    "session_intent": "当前任务意图",
    "temporary_goal": "当前临时目标",
    "course_binding": "是否绑定课程",
    "temporary_preference": "临时偏好",
}

WEAKNESS_KEYWORDS = ("矩阵", "维度", "链式", "公式", "梯度", "概率", "代码", "概念", "推导", "广播")
ACTIVE_STATUS = "active"
CANDIDATE_STATUS = "candidate"
SUPPRESSED_STATUS = "suppressed"


@dataclass(slots=True)
class ProfileContext:
    """AI 调用前使用的有效画像上下文。"""

    scope: str
    course_id: str | None
    summary: str
    global_summary: str
    course_summary: str | None = None
    session_summary: str | None = None
    cross_course_summary: str | None = None

    def format_for_prompt(self) -> str:
        """返回可直接注入模型 prompt 的中文画像摘要。"""
        lines = [f"画像范围：{self.scope}", f"综合摘要：{self.summary or '暂无画像'}"]
        if self.global_summary:
            lines.append(f"全局画像：{self.global_summary}")
        if self.course_summary:
            lines.append(f"课程画像：{self.course_summary}")
        if self.session_summary:
            lines.append(f"会话画像：{self.session_summary}")
        if self.cross_course_summary:
            lines.append(f"跨课程提示：{self.cross_course_summary}")
        return "\n".join(lines)


def _safe_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _clamp_score(value: int | float | None) -> int:
    return max(0, min(100, int(round(value or 0))))


def _dimension_name(scope: str, key: str) -> str:
    if scope == "global":
        return GLOBAL_DIMENSION_NAMES.get(key, COURSE_DIMENSION_NAMES.get(key, key))
    if scope == "session":
        return SESSION_DIMENSION_NAMES.get(key, key)
    return COURSE_DIMENSION_NAMES.get(key, GLOBAL_DIMENSION_NAMES.get(key, key))


def _normalize_weakness_label(label: str | None) -> str:
    text = label or ""
    for keyword in WEAKNESS_KEYWORDS:
        if keyword in text:
            return keyword
    return text[:24]


class LearningProfileRepository:
    """多层学习画像读写与上下文解析服务。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_learning_profile(
        self,
        *,
        user_external_id: str,
        scope: str = "all",
        course_id: str | None = None,
        conversation_id: str | None = None,
    ) -> LearningProfileResponseDTO:
        """聚合全局、课程、会话和跨课程画像。"""
        user = self._user(user_external_id)
        global_profile = self._build_global_profile(user) if scope in {"all", "global"} else self._empty_global()
        course = self._course(course_id) if course_id else None
        course_profile = (
            self._build_course_profile(user, course)
            if user and course and scope in {"all", "course"}
            else None
        )
        session_profile = (
            self._build_session_profile(user, conversation_id=conversation_id, course=course)
            if user and scope in {"all", "session"}
            else None
        )
        cross_course = (
            self._build_cross_course_profile(user)
            if user and scope in {"all", "cross_course"}
            else None
        )
        return LearningProfileResponseDTO(
            user_id=user.external_id if user else user_external_id,
            active_course_id=course.slug if course else None,
            global_profile=global_profile,
            course=course_profile,
            session=session_profile,
            cross_course=cross_course,
        )

    def get_course_profile_summary(self, course_slug: str, user_external_id: str) -> dict[str, Any]:
        """返回旧 `/courses/{course_id}/profile` 兼容结构。"""
        user = self._user(user_external_id)
        course = self._course(course_slug)
        if not user or not course:
            return {"course_id": course_slug, "summary": "", "dimensions": []}
        profile = self._build_course_profile(user, course)
        return {
            "course_id": course.slug,
            "summary": profile.summary,
            "confidence": profile.confidence,
            "dimensions": [item.model_dump(mode="json", by_alias=True) for item in profile.dimensions],
        }

    def resolve_context(
        self,
        *,
        user_external_id: str,
        course_id: str | None = None,
        conversation_id: str | None = None,
        message: str | None = None,
        task_type: str | None = None,
        resource_type: str | None = None,
    ) -> ProfileContext:
        """生成本次 AI 调用可用的画像上下文。"""
        response = self.get_learning_profile(
            user_external_id=user_external_id,
            scope="all",
            course_id=course_id,
            conversation_id=conversation_id,
        )
        global_summary = self._usable_summary(response.global_profile.dimensions, response.global_profile.summary)
        course_summary = self._usable_summary(response.course.dimensions, response.course.summary) if response.course else None
        session_summary = self._usable_summary(response.session.dimensions, response.session.summary) if response.session else None
        cross_summary = self._usable_summary(response.cross_course.dimensions, response.cross_course.summary) if response.cross_course else None
        pieces = [global_summary]
        if course_summary:
            pieces.append(course_summary)
        if session_summary:
            pieces.append(session_summary)
        if cross_summary:
            pieces.append(cross_summary)
        if task_type:
            pieces.append(f"当前任务：{task_type}")
        if resource_type:
            pieces.append(f"资源类型：{resource_type}")
        if message and not session_summary:
            pieces.append(f"本轮主题：{message[:80]}")
        return ProfileContext(
            scope="course" if course_id else "general",
            course_id=course_id,
            summary="；".join(item for item in pieces if item),
            global_summary=global_summary,
            course_summary=course_summary,
            session_summary=session_summary,
            cross_course_summary=cross_summary,
        )

    def apply_dimensions_to_global(
        self,
        *,
        user: User,
        dimensions: list[ExtractedDimension],
        source_type: str,
        source_id: str | None,
        conversation_id: str | None = None,
        force_confidence: float | None = None,
    ) -> None:
        """将通用学习证据写入全局画像。"""
        user_profile = self._ensure_user_profile(user)
        self._apply_dimensions(
            target_scope="global",
            user=user,
            user_profile=user_profile,
            course_profile=None,
            dimensions=dimensions,
            source_type=source_type,
            source_id=source_id,
            conversation_id=conversation_id,
            status=ACTIVE_STATUS,
            force_confidence=force_confidence,
        )

    def apply_dimensions_to_course(
        self,
        *,
        user: User,
        course: Course,
        dimensions: list[ExtractedDimension],
        source_type: str,
        source_id: str | None,
        conversation_id: str | None = None,
    ) -> CourseProfile:
        """将课程学习证据写入指定课程画像，并生成全局候选证据。"""
        profile = self._ensure_course_profile(user, course)
        self._apply_dimensions(
            target_scope="course",
            user=user,
            user_profile=None,
            course_profile=profile,
            dimensions=dimensions,
            source_type=source_type,
            source_id=source_id,
            conversation_id=conversation_id,
            status=ACTIVE_STATUS,
        )
        self._write_global_candidates_from_course(
            user=user,
            course=course,
            dimensions=dimensions,
            source_type=source_type,
            source_id=source_id,
            conversation_id=conversation_id,
        )
        self.promote_cross_course_candidates(user)
        return profile

    def record_assessment_evidence(
        self,
        *,
        user: User,
        course: Course,
        concept_title: str,
        assessment_id: str,
        score: int,
        mastery_delta: int,
        weak_reasons: list[str],
    ) -> None:
        """记录测评证据到课程画像，不直接升级全局画像。"""
        profile = self._ensure_course_profile(user, course)
        label = "、".join(weak_reasons[:2]) if weak_reasons else f"{concept_title} 测评"
        dimension = ExtractedDimension(
            dimension_key="knowledge_mastery",
            dimension_name="课程掌握度",
            score=score,
            label=label,
            evidence=f"{concept_title}: score={score}, mastery_delta={mastery_delta}",
            confidence=0.78,
            method="assessment",
        )
        self._apply_dimensions(
            target_scope="course",
            user=user,
            user_profile=None,
            course_profile=profile,
            dimensions=[dimension],
            source_type="assessment",
            source_id=assessment_id,
            status=ACTIVE_STATUS,
        )
        self._write_global_candidates_from_course(
            user=user,
            course=course,
            dimensions=[dimension],
            source_type="assessment",
            source_id=assessment_id,
        )
        self.promote_cross_course_candidates(user)

    def record_session_evidence(
        self,
        *,
        user: User,
        conversation_id: str | None,
        course: Course | None,
        message: str,
        intent: str | None,
        answer: str | None = None,
    ) -> None:
        """记录当前会话画像证据。"""
        conversation_uuid = _safe_uuid(conversation_id)
        topic = message.strip().replace("\n", " ")[:80] or "通用学习"
        entries = [
            ("session_topic", topic, "conversation", topic, 0.82),
            ("session_intent", intent or "default_chat", "conversation", intent or "普通问答", 0.78),
            ("course_binding", course.slug if course else "general", "conversation", f"已绑定：{course.title}" if course else "未绑定课程", 1.0),
        ]
        for key, source_id, source_type, label, confidence in entries:
            self.db.add(
                ProfileEvidence(
                    user_id=user.id,
                    course_id=course.id if course else None,
                    conversation_id=conversation_uuid,
                    scope="session",
                    dimension_key=key,
                    label=label[:120],
                    source_type=source_type,
                    source_id=str(source_id)[:120],
                    delta=0,
                    confidence_delta=confidence,
                    note=(answer or message)[:500],
                    summary=label[:500],
                    confidence=confidence,
                    status=ACTIVE_STATUS,
                )
            )

    def record_resource_usage_evidence(
        self,
        *,
        user: User,
        course: Course | None,
        resource_id: str,
        resource_title: str,
        resource_type: str | None = None,
    ) -> None:
        """记录一条资源使用证据到画像证据链。

        当学生浏览/使用资源时（由学习行为事件 resource_view 触发），
        转写一条 source_type="resource_usage" 的课程作用域证据，
        维度为 resource_preference（资源偏好），用于后续偏好分析与推荐。

        参数:
            user: 当前用户对象。
            course: 资源所属课程，通用资源为 None。
            resource_id: 资源标识，写入 source_id。
            resource_title: 资源标题，写入 label 与 summary。
            resource_type: 资源类型（lecture/quiz/code_lab 等），写入 note。

        副作用与失败模式:
            会新增一条 ProfileEvidence 记录；不单独提交事务（由调用方提交）。
            course 为 None 时作用域仍记 course 但 course_id 留空，
            避免无课程资源污染全局画像。
        """
        label = (resource_title or "资源浏览")[:120]
        note = f"资源类型：{resource_type}" if resource_type else "资源浏览"
        self.db.add(
            ProfileEvidence(
                user_id=user.id,
                course_id=course.id if course else None,
                conversation_id=None,
                scope="course",
                dimension_key="resource_preference",
                label=label,
                source_type="resource_usage",
                source_id=str(resource_id)[:120],
                delta=0,
                confidence_delta=0.6,
                note=note[:500],
                summary=label,
                confidence=0.6,
                status=ACTIVE_STATUS,
            )
        )

    def promote_cross_course_candidates(self, user: User) -> None:
        """把多课程重复出现的候选弱点提升为全局画像维度。"""
        rows = self.db.execute(
            select(ProfileEvidence)
            .where(
                ProfileEvidence.user_id == user.id,
                ProfileEvidence.scope == "global",
                ProfileEvidence.status == CANDIDATE_STATUS,
                ProfileEvidence.course_id.is_not(None),
            )
            .order_by(ProfileEvidence.created_at.desc())
        ).scalars().all()
        grouped: dict[tuple[str, str], list[ProfileEvidence]] = defaultdict(list)
        for row in rows:
            normalized = _normalize_weakness_label(row.label or row.summary or row.note)
            if normalized:
                grouped[(row.dimension_key, normalized)].append(row)

        promoted: list[ExtractedDimension] = []
        for (dimension_key, normalized), evidences in grouped.items():
            course_ids = {item.course_id for item in evidences if item.course_id}
            if len(course_ids) < 2:
                continue
            promoted.append(
                ExtractedDimension(
                    dimension_key="general_weakness" if dimension_key in {"weakness", "knowledge_mastery", "error_pattern"} else dimension_key,
                    dimension_name=GLOBAL_DIMENSION_NAMES.get("general_weakness", "通用能力短板"),
                    score=max(35, min(65, 100 - len(evidences) * 12)),
                    label=f"{normalized}存在跨课程薄弱信号",
                    evidence=f"来自 {len(course_ids)} 门课程的重复证据",
                    confidence=min(0.88, 0.58 + len(course_ids) * 0.1),
                    method="rule",
                )
            )
            for evidence in evidences:
                evidence.status = ACTIVE_STATUS
        if promoted:
            self.apply_dimensions_to_global(
                user=user,
                dimensions=promoted,
                source_type="assessment",
                source_id="cross_course_promotion",
            )

    def apply_correction(self, *, user_external_id: str, payload: ProfileCorrectionRequest) -> ProfileCorrectionResponse:
        """应用用户纠偏并写入最高优先级证据。"""
        user = self._user(user_external_id)
        if not user:
            return ProfileCorrectionResponse(status="user_not_found", scope=payload.scope, dimension_key=payload.dimension_key)

        course = self._course(payload.course_id) if payload.course_id else None
        target_dimension = self._find_dimension(user=user, scope=payload.scope, course=course, dimension_key=payload.dimension_key)
        evidence_uuid = _safe_uuid(payload.evidence_id)
        if payload.action in {"suppress_evidence", "clear_evidence", "mark_inaccurate"} and evidence_uuid:
            evidence = self.db.get(ProfileEvidence, evidence_uuid)
            if evidence and evidence.user_id == user.id:
                evidence.status = SUPPRESSED_STATUS
                self.db.add(evidence)
        if payload.action == "mark_inaccurate" and target_dimension:
            target_dimension.status = SUPPRESSED_STATUS
            self.db.add(target_dimension)

        if payload.action == "update_dimension":
            label = (payload.label or payload.summary or "用户确认").strip()[:120]
            score = payload.score if payload.score is not None else 90
            dimension = ExtractedDimension(
                dimension_key=payload.dimension_key,
                dimension_name=_dimension_name(payload.scope, payload.dimension_key),
                score=score,
                label=label,
                evidence=payload.summary or label,
                confidence=0.95,
                method="user_correction",
            )
            if payload.scope == "global":
                self.apply_dimensions_to_global(
                    user=user,
                    dimensions=[dimension],
                    source_type="user_correction",
                    source_id=payload.evidence_id or payload.dimension_key,
                    conversation_id=payload.conversation_id,
                    force_confidence=0.95,
                )
            elif payload.scope == "course" and course:
                self._apply_dimensions(
                    target_scope="course",
                    user=user,
                    user_profile=None,
                    course_profile=self._ensure_course_profile(user, course),
                    dimensions=[dimension],
                    source_type="user_correction",
                    source_id=payload.evidence_id or payload.dimension_key,
                    conversation_id=payload.conversation_id,
                    status=ACTIVE_STATUS,
                    force_confidence=0.95,
                )
        correction = self._write_correction_evidence(user=user, course=course, payload=payload)
        self.db.commit()
        return ProfileCorrectionResponse(
            status="ok",
            scope=payload.scope,
            dimension_key=payload.dimension_key,
            evidence_id=str(correction.id),
        )

    def _apply_dimensions(
        self,
        *,
        target_scope: str,
        user: User,
        user_profile: UserProfile | None,
        course_profile: CourseProfile | None,
        dimensions: list[ExtractedDimension],
        source_type: str,
        source_id: str | None,
        conversation_id: str | None = None,
        status: str,
        force_confidence: float | None = None,
    ) -> None:
        """把抽取结果合并到目标画像维度。"""
        if not dimensions:
            return
        if target_scope == "global" and user_profile:
            existing = {
                item.dimension_key: item
                for item in self.db.execute(
                    select(ProfileDimension).where(
                        ProfileDimension.user_profile_id == user_profile.id,
                        ProfileDimension.profile_scope == "global",
                    )
                ).scalars().all()
            }
        elif target_scope == "course" and course_profile:
            existing = {
                item.dimension_key: item
                for item in self.db.execute(
                    select(ProfileDimension).where(ProfileDimension.profile_id == course_profile.id)
                ).scalars().all()
            }
        else:
            return

        confidences: list[float] = []
        for dim in dimensions:
            item = existing.get(dim.dimension_key)
            prior_score = item.score if item else None
            if item and item.status == SUPPRESSED_STATUS and source_type != "user_correction":
                continue
            prior_len = len(item.evidence_json or []) if item else 0
            confidence = force_confidence if force_confidence is not None else ProfileExtractor._bumped_confidence(
                item.confidence if item else None,
                prior_len,
                dim.method if dim.method in {"rule", "llm"} else "llm",
            )
            if item:
                item.score = dim.score if source_type == "user_correction" else round(item.score * 0.7 + dim.score * 0.3)
                item.label = dim.label
                item.confidence = max(item.confidence or 0, confidence)
                item.status = ACTIVE_STATUS
                item.evidence_json = (item.evidence_json or [])[-4:] + [
                    {"source": source_type, "method": dim.method, "note": dim.evidence, "scope": target_scope}
                ]
            else:
                item = ProfileDimension(
                    profile_id=course_profile.id if course_profile else None,
                    user_profile_id=user_profile.id if user_profile else None,
                    profile_scope=target_scope,
                    dimension_key=dim.dimension_key,
                    dimension_name=_dimension_name(target_scope, dim.dimension_key),
                    score=dim.score,
                    label=dim.label,
                    confidence=confidence,
                    evidence_json=[{"source": source_type, "method": dim.method, "note": dim.evidence, "scope": target_scope}],
                    status=status,
                )
                self.db.add(item)
                existing[dim.dimension_key] = item
            confidences.append(item.confidence)
            self.db.add(
                ProfileEvidence(
                    profile_id=course_profile.id if course_profile else None,
                    user_profile_id=user_profile.id if user_profile else None,
                    user_id=user.id,
                    course_id=course_profile.course_id if course_profile else None,
                    conversation_id=_safe_uuid(conversation_id),
                    scope=target_scope,
                    dimension_key=dim.dimension_key,
                    label=dim.label,
                    source_type=source_type,
                    source_id=source_id,
                    delta=(item.score - prior_score) if prior_score is not None else 0,
                    confidence_delta=dim.confidence,
                    note=dim.evidence,
                    summary=dim.evidence,
                    confidence=item.confidence,
                    status=status,
                )
            )

        if confidences:
            if user_profile:
                user_profile.summary = self._summary_from_dimensions(existing.values())
                user_profile.confidence = min(ProfileExtractor.CONFIDENCE_CAP, max(user_profile.confidence or 0, sum(confidences) / len(confidences)))
            if course_profile:
                course_profile.summary = self._summary_from_dimensions(existing.values())
                course_profile.confidence = min(ProfileExtractor.CONFIDENCE_CAP, max(course_profile.confidence or 0, sum(confidences) / len(confidences)))

    def _write_global_candidates_from_course(
        self,
        *,
        user: User,
        course: Course,
        dimensions: list[ExtractedDimension],
        source_type: str,
        source_id: str | None,
        conversation_id: str | None = None,
    ) -> None:
        """保存课程证据的全局候选，避免单次课程信号污染全局画像。"""
        for dim in dimensions:
            if dim.dimension_key not in {"weakness", "error_pattern", "knowledge_mastery", "resource_preference", "cognitive_style"}:
                continue
            self.db.add(
                ProfileEvidence(
                    user_id=user.id,
                    course_id=course.id,
                    conversation_id=_safe_uuid(conversation_id),
                    scope="global",
                    dimension_key=dim.dimension_key,
                    label=dim.label,
                    source_type=source_type,
                    source_id=source_id,
                    delta=0,
                    confidence_delta=dim.confidence,
                    note=dim.evidence,
                    summary=dim.evidence,
                    confidence=dim.confidence,
                    status=CANDIDATE_STATUS,
                )
            )

    def _write_correction_evidence(self, *, user: User, course: Course | None, payload: ProfileCorrectionRequest) -> ProfileEvidence:
        """写入用户纠偏证据。"""
        evidence = ProfileEvidence(
            user_id=user.id,
            course_id=course.id if course else None,
            conversation_id=_safe_uuid(payload.conversation_id),
            scope=payload.scope,
            dimension_key=payload.dimension_key,
            label=payload.label,
            source_type="user_correction",
            source_id=payload.evidence_id or payload.dimension_key,
            delta=0,
            confidence_delta=0.95,
            note=payload.summary or payload.label or payload.action,
            summary=payload.summary or payload.label or payload.action,
            confidence=0.95,
            status=ACTIVE_STATUS,
        )
        self.db.add(evidence)
        return evidence

    def _build_global_profile(self, user: User | None) -> GlobalLearningProfileDTO:
        if not user:
            return self._empty_global()
        user_profile = self._ensure_user_profile(user)
        dimensions = self._dimensions_for_global(user_profile)
        settings = self.db.execute(select(UserSetting).where(UserSetting.user_id == user.id)).scalar_one_or_none()
        major = self._dimension_label(dimensions, "major_background")
        resource_preferences = self._list_from_dimension(dimensions, "resource_preference")
        if settings and settings.resource_preferences:
            resource_preferences = list(dict.fromkeys([*settings.resource_preferences, *resource_preferences]))
        goals = self._list_from_dimension(dimensions, "learning_goal")
        if settings and settings.learning_goals:
            goals = list(dict.fromkeys([*settings.learning_goals, *goals]))
        summary = user_profile.summary or self._summary_from_dtos(dimensions)
        return GlobalLearningProfileDTO(
            summary=summary,
            confidence=user_profile.confidence or self._avg_confidence(dimensions),
            dimensions=dimensions,
            major=major,
            long_term_goals=goals,
            resource_preferences=resource_preferences,
            updated_at=_iso(user_profile.updated_at),
        )

    def _build_course_profile(self, user: User, course: Course) -> CourseLearningProfileDTO:
        profile = self.db.execute(
            select(CourseProfile).where(CourseProfile.course_id == course.id, CourseProfile.user_id == user.id)
        ).scalar_one_or_none()
        dimensions = self._dimensions_for_course(profile) if profile else []
        mastery = self._course_mastery(user, course)
        current_node = self._current_node(user, course)
        weak_points = self._course_weak_points(user, course, dimensions)
        summary = profile.summary if profile and profile.summary else self._summary_from_dtos(dimensions)
        if current_node and "当前节点" not in summary:
            summary = f"{summary} 当前节点：{current_node}。".strip()
        return CourseLearningProfileDTO(
            course_id=course.slug,
            course_title=course.title,
            summary=summary,
            confidence=profile.confidence if profile else self._avg_confidence(dimensions),
            dimensions=dimensions,
            current_node=current_node,
            mastery=mastery / 100 if mastery is not None else None,
            weak_points=weak_points,
            updated_at=_iso(profile.updated_at) if profile else None,
        )

    def _build_session_profile(self, user: User, *, conversation_id: str | None, course: Course | None) -> SessionLearningProfileDTO | None:
        conversation = self._conversation(user=user, conversation_id=conversation_id, course=course)
        if not conversation:
            return None
        evidence_rows = self.db.execute(
            select(ProfileEvidence)
            .where(
                ProfileEvidence.user_id == user.id,
                ProfileEvidence.conversation_id == conversation.id,
                ProfileEvidence.scope == "session",
                ProfileEvidence.status == ACTIVE_STATUS,
            )
            .order_by(ProfileEvidence.created_at.desc())
            .limit(20)
        ).scalars().all()
        dimensions = self._session_dimensions_from_evidence(evidence_rows, conversation)
        topic = self._label_by_key(dimensions, "session_topic") or conversation.title
        intent = self._label_by_key(dimensions, "session_intent")
        summary = "；".join(item.label for item in dimensions[:3] if item.label) or "暂无最近会话画像"
        return SessionLearningProfileDTO(
            conversation_id=str(conversation.id),
            topic=topic,
            intent=intent,
            temporary_goal=self._label_by_key(dimensions, "temporary_goal"),
            summary=summary,
            dimensions=dimensions,
            updated_at=_iso(conversation.updated_at),
        )

    def _build_cross_course_profile(self, user: User) -> CrossCourseLearningProfileDTO:
        rows = self.db.execute(
            select(ProfileDimension, Course)
            .join(CourseProfile, CourseProfile.id == ProfileDimension.profile_id)
            .join(Course, Course.id == CourseProfile.course_id)
            .where(
                CourseProfile.user_id == user.id,
                ProfileDimension.profile_scope == "course",
                ProfileDimension.status == ACTIVE_STATUS,
            )
        ).all()
        grouped: dict[str, list[tuple[ProfileDimension, Course]]] = defaultdict(list)
        for dimension, course in rows:
            if dimension.score > 65 and dimension.dimension_key not in {"weakness", "error_pattern", "knowledge_mastery", "transfer"}:
                continue
            label_key = _normalize_weakness_label(dimension.label)
            if label_key:
                grouped[label_key].append((dimension, course))

        dimensions: list[ProfileDimensionDTO] = []
        common: list[str] = []
        alerts: list[str] = []
        hints: list[str] = []
        for label_key, items in grouped.items():
            courses = {course.slug for _dimension, course in items}
            if len(courses) < 2:
                continue
            common.append(label_key)
            score = _clamp_score(sum(item.score for item, _course in items) / len(items))
            dimensions.append(
                ProfileDimensionDTO(
                    key=f"cross_{label_key}",
                    name="共性短板",
                    score=score,
                    label=f"{label_key}在多课程中反复出现",
                    confidence=min(0.9, 0.55 + len(courses) * 0.1),
                    evidence=[f"来自 {len(courses)} 门课程：{', '.join(sorted(courses))}"],
                    scope="cross_course",
                    updated_at=_iso(max((item.updated_at for item, _course in items if item.updated_at), default=None)),
                    evidence_summary=f"来自 {len(courses)} 门课程画像维度",
                    source_type="assessment",
                )
            )
            if label_key in {"矩阵", "维度", "广播"}:
                alerts.append("线性代数矩阵运算不稳，可能影响课程中的张量形状和维度推导。")
            if label_key in {"链式", "梯度", "公式", "推导"}:
                alerts.append("高等数学链式求导薄弱，可能影响反向传播和梯度下降理解。")
            hints.append(f"围绕“{label_key}”生成跨课程补救卡。")
        summary = "；".join(common[:3]) if common else ""
        return CrossCourseLearningProfileDTO(
            summary=f"跨课程共性短板：{summary}" if summary else "",
            common_weaknesses=common[:5],
            transfer_hints=list(dict.fromkeys(hints))[:5],
            prerequisite_alerts=list(dict.fromkeys(alerts))[:5],
            dimensions=dimensions,
            updated_at=max((item.updated_at for item, _course in rows if item.updated_at), default=None).isoformat()
            if rows and any(item.updated_at for item, _course in rows)
            else None,
        )

    def _dimensions_for_global(self, user_profile: UserProfile) -> list[ProfileDimensionDTO]:
        rows = self.db.execute(
            select(ProfileDimension)
            .where(
                ProfileDimension.user_profile_id == user_profile.id,
                ProfileDimension.profile_scope == "global",
                ProfileDimension.status == ACTIVE_STATUS,
            )
            .order_by(ProfileDimension.dimension_key)
        ).scalars().all()
        return [self._dimension_to_dto(item, "global") for item in rows]

    def _dimensions_for_course(self, profile: CourseProfile | None) -> list[ProfileDimensionDTO]:
        if not profile:
            return []
        rows = self.db.execute(
            select(ProfileDimension)
            .where(
                ProfileDimension.profile_id == profile.id,
                ProfileDimension.profile_scope == "course",
                ProfileDimension.status == ACTIVE_STATUS,
            )
            .order_by(ProfileDimension.dimension_key)
        ).scalars().all()
        return [self._dimension_to_dto(item, "course") for item in rows]

    def _dimension_to_dto(self, item: ProfileDimension, scope: str) -> ProfileDimensionDTO:
        evidences = self._evidence_for_dimension(item, scope)
        latest = evidences[0] if evidences else None
        return ProfileDimensionDTO(
            key=item.dimension_key,
            name=item.dimension_name or _dimension_name(scope, item.dimension_key),
            score=item.score,
            label=item.label or "待观察",
            confidence=item.confidence or 0.0,
            evidence=evidences or (item.evidence_json or []),
            scope=scope,  # type: ignore[arg-type]
            updated_at=_iso(item.updated_at),
            evidence_summary=latest.summary if latest else self._latest_evidence_note(item),
            source_type=latest.source_type if latest else None,
        )

    def list_evidence(
        self,
        *,
        user_external_id: str,
        dimension: str | None = None,
        source_type: str | None = None,
        scope: str | None = None,
        course_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """查询当前用户的画像证据链，支持按维度、来源、作用域、课程和时间范围过滤并分页。

        参数:
            user_external_id: 当前用户外部 ID。
            dimension: 仅返回该维度键的证据，为空则不限。
            source_type: 仅返回该来源类型（conversation/assessment/user_correction/resource_usage 等）的证据。
            scope: 作用域过滤（global/course/session），为空则不限。
            course_id: 课程 slug 过滤，仅在课程作用域证据中匹配。
            start_date: 起始时间（含），ISO 8601。
            end_date: 结束时间（含），ISO 8601。
            page: 页码，从 1 开始。
            page_size: 每页条数，默认 20。

        返回:
            {"items": list[ProfileEvidenceDTO], "meta": {"page", "page_size", "total"}}。

        副作用与失败模式:
            仅读取数据库；用户不存在时返回空列表与零计数，不抛异常。
        """
        user = self._user(user_external_id)
        if not user:
            return {"items": [], "meta": {"page": page, "page_size": page_size, "total": 0}}

        clauses: list[ColumnElement[bool]] = [ProfileEvidence.user_id == user.id]
        if dimension:
            clauses.append(ProfileEvidence.dimension_key == dimension)
        if source_type:
            clauses.append(ProfileEvidence.source_type == source_type)
        if scope:
            clauses.append(ProfileEvidence.scope == scope)
        if course_id:
            course = self._course(course_id)
            if course:
                clauses.append(ProfileEvidence.course_id == course.id)
            else:
                # 课程 slug 无效时直接返回空，避免误返回其他课程证据
                return {"items": [], "meta": {"page": page, "page_size": page_size, "total": 0}}
        if start_date:
            clauses.append(ProfileEvidence.created_at >= start_date)
        if end_date:
            clauses.append(ProfileEvidence.created_at <= end_date)

        total = self.db.execute(
            select(func.count()).select_from(ProfileEvidence).where(*clauses)
        ).scalar_one()
        rows = (
            self.db.execute(
                select(ProfileEvidence)
                .where(*clauses)
                .order_by(ProfileEvidence.created_at.desc())
                .offset(max(0, (page - 1) * page_size))
                .limit(max(1, page_size))
            )
            .scalars()
            .all()
        )
        return {
            "items": [self._evidence_to_dto(row) for row in rows],
            "meta": {"page": page, "page_size": page_size, "total": int(total or 0)},
        }

    def _evidence_for_dimension(self, item: ProfileDimension, scope: str) -> list[ProfileEvidenceDTO]:
        clauses = [
            ProfileEvidence.dimension_key == item.dimension_key,
            ProfileEvidence.scope == scope,
            ProfileEvidence.status == ACTIVE_STATUS,
        ]
        if scope == "global":
            clauses.append(ProfileEvidence.user_profile_id == item.user_profile_id)
        else:
            clauses.append(ProfileEvidence.profile_id == item.profile_id)
        rows = self.db.execute(select(ProfileEvidence).where(*clauses).order_by(ProfileEvidence.created_at.desc()).limit(4)).scalars().all()
        return [self._evidence_to_dto(row) for row in rows]

    def _evidence_to_dto(self, row: ProfileEvidence) -> ProfileEvidenceDTO:
        return ProfileEvidenceDTO(
            id=str(row.id),
            scope=row.scope,  # type: ignore[arg-type]
            course_id=self._course_slug_by_id(row.course_id),
            conversation_id=str(row.conversation_id) if row.conversation_id else None,
            dimension=row.dimension_key,
            label=row.label,
            source_type=row.source_type,
            source_id=row.source_id,
            summary=row.summary or row.note or row.label or "",
            confidence_delta=row.confidence_delta or 0.0,
            created_at=_iso(row.created_at),
            status=row.status or ACTIVE_STATUS,
        )

    def _session_dimensions_from_evidence(self, rows: list[ProfileEvidence], conversation: Conversation) -> list[ProfileDimensionDTO]:
        latest_by_key: dict[str, ProfileEvidence] = {}
        for row in rows:
            latest_by_key.setdefault(row.dimension_key, row)
        if "session_topic" not in latest_by_key:
            latest_by_key["session_topic"] = ProfileEvidence(
                id=uuid.uuid4(),
                scope="session",
                dimension_key="session_topic",
                label=conversation.title,
                source_type="conversation",
                source_id=str(conversation.id),
                note=conversation.title,
                summary=conversation.title,
                confidence=0.65,
                confidence_delta=0.65,
                status=ACTIVE_STATUS,
            )
        dimensions: list[ProfileDimensionDTO] = []
        for key, evidence in latest_by_key.items():
            dimensions.append(
                ProfileDimensionDTO(
                    key=key,
                    name=_dimension_name("session", key),
                    score=_clamp_score((evidence.confidence or 0.65) * 100),
                    label=evidence.label or evidence.summary or evidence.note or "待观察",
                    confidence=evidence.confidence or 0.65,
                    evidence=[self._evidence_to_dto(evidence)] if getattr(evidence, "created_at", None) else [evidence.summary or evidence.note or ""],
                    scope="session",
                    updated_at=_iso(evidence.created_at) or _iso(conversation.updated_at),
                    evidence_summary=evidence.summary or evidence.note,
                    source_type=evidence.source_type,
                )
            )
        return sorted(dimensions, key=lambda item: item.key)

    def _ensure_user_profile(self, user: User) -> UserProfile:
        profile = self.db.execute(select(UserProfile).where(UserProfile.user_id == user.id)).scalar_one_or_none()
        if profile:
            return profile
        profile = UserProfile(user_id=user.id, summary="", confidence=0.0)
        self.db.add(profile)
        self.db.flush()
        return profile

    def _ensure_course_profile(self, user: User, course: Course) -> CourseProfile:
        profile = self.db.execute(
            select(CourseProfile).where(CourseProfile.course_id == course.id, CourseProfile.user_id == user.id)
        ).scalar_one_or_none()
        if profile:
            return profile
        profile = CourseProfile(course_id=course.id, user_id=user.id, summary="", confidence=0.55)
        self.db.add(profile)
        self.db.flush()
        return profile

    def _find_dimension(self, *, user: User, scope: str, course: Course | None, dimension_key: str) -> ProfileDimension | None:
        if scope == "global":
            profile = self._ensure_user_profile(user)
            return self.db.execute(
                select(ProfileDimension).where(
                    ProfileDimension.user_profile_id == profile.id,
                    ProfileDimension.profile_scope == "global",
                    ProfileDimension.dimension_key == dimension_key,
                )
            ).scalar_one_or_none()
        if scope == "course" and course:
            profile = self._ensure_course_profile(user, course)
            return self.db.execute(
                select(ProfileDimension).where(
                    ProfileDimension.profile_id == profile.id,
                    ProfileDimension.profile_scope == "course",
                    ProfileDimension.dimension_key == dimension_key,
                )
            ).scalar_one_or_none()
        return None

    def _course(self, slug: str | None) -> Course | None:
        if not slug:
            return None
        clauses = [Course.slug == slug]
        course_uuid = _safe_uuid(slug)
        if course_uuid:
            clauses.append(Course.id == course_uuid)
        return self.db.execute(select(Course).where(or_(*clauses))).scalar_one_or_none()

    def _user(self, external_id: str) -> User | None:
        return self.db.execute(select(User).where(User.external_id == external_id)).scalar_one_or_none()

    def _course_slug_by_id(self, course_id: uuid.UUID | None) -> str | None:
        if not course_id:
            return None
        course = self.db.get(Course, course_id)
        return course.slug if course else str(course_id)

    def _conversation(self, *, user: User, conversation_id: str | None, course: Course | None) -> Conversation | None:
        conversation_uuid = _safe_uuid(conversation_id)
        if conversation_uuid:
            conversation = self.db.get(Conversation, conversation_uuid)
            if conversation and conversation.user_id == user.id:
                return conversation
        clauses = [Conversation.user_id == user.id, Conversation.status != "deleted"]
        if course:
            clauses.append(Conversation.course_id == course.id)
        else:
            clauses.append(Conversation.course_id.is_(None))
        return self.db.execute(select(Conversation).where(*clauses).order_by(Conversation.updated_at.desc())).scalars().first()

    def _course_mastery(self, user: User, course: Course) -> int | None:
        rows = self.db.execute(
            select(ConceptMastery.mastery).where(ConceptMastery.course_id == course.id, ConceptMastery.user_id == user.id)
        ).scalars().all()
        if not rows:
            return None
        return _clamp_score(sum(rows) / len(rows))

    def _current_node(self, user: User, course: Course) -> str | None:
        path = self.db.execute(
            select(LearningPath)
            .where(LearningPath.course_id == course.id, LearningPath.user_id == user.id, LearningPath.status == "active")
            .order_by(LearningPath.version.desc())
        ).scalars().first()
        if not path:
            return None
        node = self.db.execute(
            select(PathNode)
            .where(PathNode.learning_path_id == path.id, PathNode.status.in_(("learning", "needs_remedial", "review", "not_started")))
            .order_by(PathNode.order_index)
        ).scalars().first()
        return node.title if node else None

    def _course_weak_points(self, user: User, course: Course, dimensions: list[ProfileDimensionDTO]) -> list[str]:
        labels = [
            item.label
            for item in dimensions
            if item.key in {"weakness", "error_pattern", "knowledge_mastery", "transfer"} and item.score <= 65 and item.label
        ]
        mastery_rows = self.db.execute(
            select(CourseConcept.title, ConceptMastery.mastery)
            .join(ConceptMastery, ConceptMastery.concept_id == CourseConcept.id)
            .where(ConceptMastery.course_id == course.id, ConceptMastery.user_id == user.id, ConceptMastery.mastery < 60)
            .order_by(ConceptMastery.mastery.asc())
            .limit(4)
        ).all()
        labels.extend(title for title, _mastery in mastery_rows)
        return list(dict.fromkeys(labels))[:6]

    @staticmethod
    def _avg_confidence(dimensions: list[ProfileDimensionDTO]) -> float:
        if not dimensions:
            return 0.0
        return sum(item.confidence for item in dimensions) / len(dimensions)

    @staticmethod
    def _latest_evidence_note(item: ProfileDimension) -> str | None:
        latest = (item.evidence_json or [])[-1:] if item.evidence_json else []
        if latest and isinstance(latest[0], dict):
            return latest[0].get("note")
        return None

    @staticmethod
    def _summary_from_dimensions(dimensions: Any) -> str:
        parts = []
        for item in dimensions:
            if getattr(item, "status", ACTIVE_STATUS) != ACTIVE_STATUS:
                continue
            label = getattr(item, "label", None)
            name = getattr(item, "dimension_name", None)
            if label and name:
                parts.append(f"{name}：{label}")
        return "；".join(parts[:5]) + ("。" if parts else "")

    @staticmethod
    def _summary_from_dtos(dimensions: list[ProfileDimensionDTO]) -> str:
        parts = [f"{item.name}：{item.label}" for item in dimensions if item.label]
        return "；".join(parts[:5]) + ("。" if parts else "")

    @staticmethod
    def _usable_summary(dimensions: list[ProfileDimensionDTO], fallback: str) -> str:
        usable = [item for item in dimensions if item.confidence >= 0.4]
        if not usable:
            return fallback or ""
        return "；".join(f"{item.name}：{item.label}（置信 {item.confidence:.0%}）" for item in usable[:6])

    @staticmethod
    def _dimension_label(dimensions: list[ProfileDimensionDTO], key: str) -> str | None:
        for item in dimensions:
            if item.key == key:
                return item.label
        return None

    @staticmethod
    def _label_by_key(dimensions: list[ProfileDimensionDTO], key: str) -> str | None:
        for item in dimensions:
            if item.key == key:
                return item.label
        return None

    @staticmethod
    def _list_from_dimension(dimensions: list[ProfileDimensionDTO], key: str) -> list[str]:
        label = LearningProfileRepository._dimension_label(dimensions, key)
        if not label:
            return []
        return [part.strip() for part in label.replace("，", "、").replace(",", "、").split("、") if part.strip()]

    @staticmethod
    def _empty_global() -> GlobalLearningProfileDTO:
        return GlobalLearningProfileDTO(summary="", confidence=0.0, dimensions=[])
