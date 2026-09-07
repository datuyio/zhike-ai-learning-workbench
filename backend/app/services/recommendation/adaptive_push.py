from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import cast, func, select, String
from sqlalchemy.orm import Session

from app.models import (
    Assessment,
    ConceptMastery,
    CourseConcept,
    CourseProfile,
    LearningEvent,
    ProfileDimension,
    Resource,
    StudentLearningEvent,
    User,
    WrongAnswerAnalysis,
)
from app.schemas.recommendation import PushItemDTO

logger = logging.getLogger(__name__)

# 默认规则阈值（0-100 分制）
DEFAULT_MASTERY_THRESHOLD = 60  # 画像驱动：掌握度低于该值推送复习
DEFAULT_ASSESSMENT_THRESHOLD = 60  # 评分驱动：Rubric 评分低于该值推送补救
DEFAULT_IDLE_HOURS = 48  # 时间驱动：超过该小时数未学习推送提醒

# 画像中表示掌握度/薄弱点的维度 key
MASTERY_DIMENSION_KEYS = ("knowledge_mastery", "mastery", "weakness", "error_pattern", "transfer")
# 画像维度中数值越低越薄弱的关键维度（score 低 = 薄弱）
LOW_SCORE_WEAK_DIMENSIONS = ("knowledge_mastery", "mastery", "transfer")
# 画像维度中数值越高越薄弱的关键维度（score 高 = 薄弱）
HIGH_SCORE_WEAK_DIMENSIONS = ("weakness", "error_pattern")


class AdaptivePushService:
    """自适应推送规则引擎。

    依据用户画像、测验评分和学习时间三类信号，生成个性化的复习/补救/提醒推送。
    规则引擎是纯读取服务，不写库，失败时返回空列表而不会抛出业务异常。

    参数:
        db: 当前请求范围内的 SQLAlchemy 会话。

    方法:
        get_push_list(user_id, course_id): 聚合三条规则并返回按优先级排序的推送列表。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- 对外入口 ----

    def get_push_list(self, *, user_id: str, course_id: str | None = None) -> list[PushItemDTO]:
        """聚合画像、评分、时间三条规则，返回按优先级降序的推送列表。

        参数:
            user_id: 用户 ID（登录态提供的 external_id 字符串）。
            course_id: 可选课程 ID；为空时只看全局画像与跨课程数据。

        返回值:
            按 priority 降序排列的推送项列表；无任何触发时返回空列表。

        副作用/失败模式:
            仅读取数据库；单条规则异常会被记录并跳过，不影响其余规则。

        说明:
            推荐相关表的 user_id 外键指向 users.id（UUID 类型），而登录态拿到的是
            external_id 字符串，因此先解析出真实 UUID 再交给各规则，避免 UUID 列
            比对失败导致规则全部静默返回空。
        """
        user_uuid = self._resolve_user_uuid(user_id)
        if user_uuid is None:
            return []
        items: list[PushItemDTO] = []
        items.extend(self._profile_rule(user_uuid=user_uuid, course_id=course_id))
        items.extend(self._assessment_rule(user_uuid=user_uuid, course_id=course_id))
        items.extend(self._time_rule(user_uuid=user_uuid, course_id=course_id))
        # 优先级高的排前面，同级按 title 稳定排序
        items.sort(key=lambda it: (-it.priority, it.title))
        return items

    def _resolve_user_uuid(self, user_id: str) -> uuid.UUID | None:
        """把登录态的 external_id 字符串解析为 users.id 的真实 UUID。

        若传入的 user_id 本身就是一个合法 UUID，则直接使用；否则按 external_id
        查询用户表。查不到对应用户时返回 None，调用方据此返回空推送列表。
        """
        try:
            return uuid.UUID(str(user_id))
        except (ValueError, TypeError):
            pass
        user = self.db.execute(
            select(User).where(User.external_id == user_id)
        ).scalar_one_or_none()
        return user.id if user else None

    # ---- 规则 1：画像驱动 ----

    def _profile_rule(self, *, user_uuid: uuid.UUID, course_id: str | None) -> list[PushItemDTO]:
        """画像驱动：掌握度低于阈值时推送对应知识点/资源的复习内容。

        优先使用单课程画像（course_profile）中的掌握度维度；无课程时回退到全局画像。
        同时补充知识点级掌握度（ConceptMastery）低于阈值的概念。
        """
        items: list[PushItemDTO] = []
        try:
            # 1) 由课程画像/全局画像中的掌握度维度触发
            profile = self._find_profile(user_uuid=user_uuid, course_id=course_id)
            if profile is not None:
                dims = self.db.execute(
                    select(ProfileDimension).where(
                        ProfileDimension.profile_id == profile.id,
                        ProfileDimension.status == "active",
                    )
                ).scalars().all()
                for dim in dims:
                    if dim.dimension_key not in MASTERY_DIMENSION_KEYS:
                        continue
                    weak = self._is_weak_dimension(dim)
                    if not weak:
                        continue
                    concept = self._find_concept_by_title(dim.dimension_name, course_id=course_id)
                    resource = self._find_resource_for(concept_id=concept.id if concept else None)
                    items.append(
                        PushItemDTO(
                            rule_type="profile_driven",
                            rule_label="掌握度低于阈值",
                            priority=70,
                            title=f"复习：{dim.dimension_name or dim.dimension_key} 掌握度偏低",
                            description=(
                                f"画像显示「{dim.dimension_name or dim.dimension_key}」掌握度仅 {dim.score} 分，"
                                "建议安排复习以巩固该知识点。"
                            ),
                            concept_id=str(concept.id) if concept else None,
                            concept_title=concept.title if concept else None,
                            resource_id=str(resource.id) if resource else None,
                            resource_title=resource.title if resource else None,
                            resource_type=resource.resource_type if resource else None,
                            current_score=dim.score,
                            threshold=DEFAULT_MASTERY_THRESHOLD,
                        )
                    )

            # 2) 知识点级掌握度（ConceptMastery）触发
            concept_items = self._concept_mastery_items(user_uuid=user_uuid, course_id=course_id)
            items.extend(concept_items)
        except Exception:
            logger.exception("自适应推送-画像规则执行失败")
            self.db.rollback()
        return items

    def _find_profile(self, *, user_uuid: uuid.UUID, course_id: str | None) -> CourseProfile | None:
        """按课程优先、全局回退的顺序查找用户画像记录。"""
        if course_id:
            profile = self.db.execute(
                select(CourseProfile).where(
                    CourseProfile.course_id == course_id,
                    CourseProfile.user_id == user_uuid,
                )
            ).scalar_one_or_none()
            if profile is not None:
                return profile
        # 全局课程画像（无课程时）
        global_profile = self.db.execute(
            select(CourseProfile).where(CourseProfile.user_id == user_uuid).limit(1)
        ).scalar_one_or_none()
        return global_profile

    def _is_weak_dimension(self, dim: ProfileDimension) -> bool:
        """判断画像维度是否达到推送阈值：低分维度低于阈值，高分维度高于阈值。"""
        if dim.dimension_key in LOW_SCORE_WEAK_DIMENSIONS:
            return dim.score < DEFAULT_MASTERY_THRESHOLD
        if dim.dimension_key in HIGH_SCORE_WEAK_DIMENSIONS:
            return dim.score > (100 - DEFAULT_MASTERY_THRESHOLD)
        return False

    def _concept_mastery_items(self, *, user_uuid: uuid.UUID, course_id: str | None) -> list[PushItemDTO]:
        """知识点级掌握度低于阈值的概念推送。"""
        items: list[PushItemDTO] = []
        mastery_rows = self.db.execute(
            select(ConceptMastery).where(
                ConceptMastery.user_id == user_uuid,
                ConceptMastery.mastery < DEFAULT_MASTERY_THRESHOLD,
            )
        ).scalars().all()
        for row in mastery_rows:
            if course_id and str(row.course_id) != course_id:
                continue
            concept = self.db.get(CourseConcept, row.concept_id) if row.concept_id else None
            if concept is None:
                continue
            resource = self._find_resource_for(concept_id=row.concept_id)
            items.append(
                PushItemDTO(
                    rule_type="profile_driven",
                    rule_label="知识点掌握度低于阈值",
                    priority=65,
                    title=f"巩固：{concept.title} 掌握度不足",
                    description=f"「{concept.title}」当前掌握度为 {row.mastery} 分，低于 {DEFAULT_MASTERY_THRESHOLD} 分，建议复习巩固。",
                    concept_id=str(concept.id),
                    concept_title=concept.title,
                    resource_id=str(resource.id) if resource else None,
                    resource_title=resource.title if resource else None,
                    resource_type=resource.resource_type if resource else None,
                    current_score=row.mastery,
                    threshold=DEFAULT_MASTERY_THRESHOLD,
                )
            )
        return items

    # ---- 规则 2：评分驱动 ----

    def _assessment_rule(self, *, user_uuid: uuid.UUID, course_id: str | None) -> list[PushItemDTO]:
        """评分驱动：Rubric 评分低于设定值时推送补救内容。

        读取用户最近评分低于阈值的测评，结合错因分析（WrongAnswerAnalysis）中的
        推荐资源 ID 推送补救资源。
        """
        items: list[PushItemDTO] = []
        try:
            query = (
                select(Assessment)
                .where(
                    Assessment.user_id == user_uuid,
                    Assessment.score < DEFAULT_ASSESSMENT_THRESHOLD,
                )
                .order_by(Assessment.created_at.desc())
                .limit(5)
            )
            if course_id:
                query = query.where(Assessment.course_id == course_id)
            assessments = self.db.execute(query).scalars().all()
            for assessment in assessments:
                resource_ids = self._wrong_answer_resources(assessment.id)
                resource = self._pick_resource(resource_ids)
                concept_title = self._concept_title(assessment.concept_id)
                items.append(
                    PushItemDTO(
                        rule_type="assessment_driven",
                        rule_label="Rubric 评分低于阈值",
                        priority=70,
                        title = f"补救：{'测验' if concept_title is None else concept_title} 评分不理想",
                        description=(
                            f"最近一次测评评分为 {assessment.score} 分，低于 {DEFAULT_ASSESSMENT_THRESHOLD} 分。"
                            "建议针对薄弱环节进行补救练习。"
                        ),
                        concept_id=str(assessment.concept_id) if assessment.concept_id else None,
                        concept_title=concept_title,
                        resource_id=str(resource.id) if resource else None,
                        resource_title=resource.title if resource else None,
                        resource_type=resource.resource_type if resource else None,
                        current_score=assessment.score,
                        threshold=DEFAULT_ASSESSMENT_THRESHOLD,
                    )
                )
        except Exception:
            logger.exception("自适应推送-评分规则执行失败")
            self.db.rollback()
        return items

    def _wrong_answer_resources(self, assessment_id: uuid.UUID) -> list[str]:
        """读取错因分析中推荐的资源 ID，合并去重。"""
        resource_ids: list[str] = []
        analyses = self.db.execute(
            select(WrongAnswerAnalysis).where(WrongAnswerAnalysis.assessment_id == assessment_id)
        ).scalars().all()
        for analysis in analyses:
            resource_ids.extend(analysis.recommended_resource_ids or [])
        # 去重并保留原有顺序
        return list(dict.fromkeys(resource_ids))

    def _pick_resource(self, resource_ids: list[str]) -> Resource | None:
        """从一组资源 ID 中挑选第一个仍存在的资源。"""
        for rid in resource_ids:
            try:
                resource = self.db.execute(
                    select(Resource).where(
                        Resource.id == rid,
                        Resource.status == "published",
                    )
                ).scalar_one_or_none()
            except Exception:
                resource = None
            if resource is not None:
                return resource
        return None

    # ---- 规则 3：时间驱动 ----

    def _time_rule(self, *, user_uuid: uuid.UUID, course_id: str | None) -> list[PushItemDTO]:
        """时间驱动：超过设定时间未学习时推送提醒。

        同时查询业务学习事件表（learning_events）与 TA 学生事件表（student_learning_events），
        取最近一次活动时间；超过 DEFAULT_IDLE_HOURS 未学习则生成提醒推送。
        """
        try:
            last_activity = self._last_activity_at(user_uuid=user_uuid, course_id=course_id)
            if last_activity is None:
                # 从未产生学习行为，也视为需要首启引导提醒
                return [
                    PushItemDTO(
                        rule_type="time_driven",
                        rule_label="长时间未学习",
                        priority=60,
                        title="开启你的学习之旅",
                        description="检测到你还没有学习记录，建议现在开始今天的学习计划。",
                        last_active_at=None,
                    )
                ]
            idle_gap = datetime.now(timezone.utc) - last_activity
            if idle_gap.total_seconds() < DEFAULT_IDLE_HOURS * 3600:
                return []
            hours = int(idle_gap.total_seconds() // 3600)
            return [
                PushItemDTO(
                    rule_type="time_driven",
                    rule_label="长时间未学习",
                    priority=60,
                    title="是该回来学习啦",
                    description=f"距上次学习已超过 {DEFAULT_IDLE_HOURS} 小时（约 {hours} 小时），温故而知新，建议继续学习。",
                    last_active_at=last_activity,
                )
            ]
        except Exception:
            logger.exception("自适应推送-时间规则执行失败")
            self.db.rollback()
            return []

    def _last_activity_at(self, *, user_uuid: uuid.UUID, course_id: str | None) -> datetime | None:
        """返回用户最近一次学习行为时间，跨两张事件表取最新。

        两张表的时间可能一为带时区、一为 naive datetime，统一按 UTC 归一后比较。
        """
        latest: datetime | None = None
        # 业务学习事件表
        query = select(func.max(LearningEvent.created_at)).where(LearningEvent.user_id == user_uuid)
        if course_id:
            query = query.where(LearningEvent.course_id == course_id)
        business_latest = self.db.execute(query).scalar_one_or_none()
        # TA 学生事件表（student_id 即用户 id）；course_id 为 UUID 列，但调用方可能传入
        # 课程 slug，因此把列 cast 为字符串再比较，以兼容两种课程标识。
        query2 = select(func.max(StudentLearningEvent.created_at)).where(
            StudentLearningEvent.student_id == user_uuid
        )
        if course_id:
            query2 = query2.where(cast(StudentLearningEvent.course_id, String) == course_id)
        ta_latest = self.db.execute(query2).scalar_one_or_none()
        for candidate in (business_latest, ta_latest):
            if candidate is None:
                continue
            # 统一为带时区的 aware datetime，避免 max() 比较 naive/aware 时报错
            candidate_utc = candidate
            if candidate_utc.tzinfo is None:
                candidate_utc = candidate_utc.replace(tzinfo=timezone.utc)
            if latest is None or candidate_utc > latest:
                latest = candidate_utc
        return latest

    # ---- 通用查询辅助 ----

    def _find_concept_by_title(self, title: str, *, course_id: str | None) -> CourseConcept | None:
        """按标题模糊匹配知识点，用于将画像维度名关联到知识点。"""
        if not title:
            return None
        query = select(CourseConcept).where(CourseConcept.title.ilike(f"%{title}%"))
        if course_id:
            query = query.where(CourseConcept.course_id == course_id)
        return self.db.execute(query.limit(1)).scalar_one_or_none()

    def _find_resource_for(self, *, concept_id: uuid.UUID | None) -> Resource | None:
        """按知识点查找已发布资源，优先返回视频/文档等学习型资源。"""
        if concept_id is None:
            return None
        return self.db.execute(
            select(Resource)
            .where(
                Resource.concept_id == concept_id,
                Resource.status == "published",
            )
            .order_by(Resource.resource_type.in_(["video", "document"]).desc(), Resource.quality_score.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _concept_title(self, concept_id: uuid.UUID | None) -> str | None:
        """查询知识点标题。"""
        if concept_id is None:
            return None
        concept = self.db.get(CourseConcept, concept_id)
        return concept.title if concept else None
