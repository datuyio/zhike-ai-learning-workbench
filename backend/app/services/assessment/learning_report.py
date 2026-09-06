from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Date, cast, func, select, String
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
)
from app.schemas.assessment_report import (
    LearningReportResponse,
    ReportDimensionScore,
    ReportTrendPoint,
)

logger = logging.getLogger(__name__)

# 维度权重（总和 100%）
WEIGHT_MASTERY = 0.35     # 知识掌握度
WEIGHT_ASSESSMENT = 0.30  # 测验表现
WEIGHT_ENGAGEMENT = 0.20  # 学习参与度
WEIGHT_RESOURCE = 0.15    # 资源利用

# 等级阈值
LEVEL_EXCELLENT = 90  # 优秀
LEVEL_GOOD = 75       # 良好
LEVEL_FAIR = 60       # 中等
# < 60 为待加强

# 参与度评分阈值
ENGAGEMENT_HIGH = 50    # 事件数 >= 50 → 90 分
ENGAGEMENT_MEDIUM = 20  # 事件数 >= 20 → 70 分
ENGAGEMENT_LOW = 5      # 事件数 >= 5 → 50 分
# 事件数 < 5 → 30 分

# 画像维度中与掌握度相关的 key
MASTERY_DIMENSION_KEYS = ("knowledge_mastery", "mastery", "weakness", "error_pattern", "transfer")
# 低分维度（score 低 = 薄弱）
LOW_SCORE_WEAK_KEYS = ("knowledge_mastery", "mastery", "transfer")
# 高分维度（score 高 = 薄弱）
HIGH_SCORE_WEAK_KEYS = ("weakness", "error_pattern")

# 趋势最大周数
TREND_WEEKS = 4


def _level(score: int) -> str:
    """将 0-100 的分数映射为等级。"""
    if score >= LEVEL_EXCELLENT:
        return "优秀"
    if score >= LEVEL_GOOD:
        return "良好"
    if score >= LEVEL_FAIR:
        return "中等"
    return "待加强"


class LearningReportService:
    """学习效果评估报告服务。

    聚合学习行为事件、画像数据、测验评分和资源使用 4 个数据源，
    生成包含总体评分、维度评分和进步趋势的结构化评估报告。
    本服务是纯读取服务，不写库，失败时返回空报告而不抛出业务异常。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- 对外入口 ----

    def get_report(self, *, user_id: str, course_id: str | None = None) -> LearningReportResponse:
        """聚合所有数据源，生成学习效果评估报告。

        参数:
            user_id: 用户 external_id 字符串。
            course_id: 可选课程 ID。

        返回值:
            完整的评估报告，包含总体评分、维度评分和进步趋势。
            用户不存在或数据不足时返回一个基本报告（总体评分 0）。
        """
        user_uuid = self._resolve_user_uuid(user_id)
        if user_uuid is None:
            return self._empty_report(user_id=user_id, course_id=course_id)

        course_title = self._course_title(course_id) if course_id else None

        # 计算各维度评分
        mastery_score, mastery_desc, weak_points = self._calc_knowledge_mastery(
            user_uuid=user_uuid, course_id=course_id
        )
        assessment_score, assessment_desc, assessment_count, trend = self._calc_assessment_performance(
            user_uuid=user_uuid, course_id=course_id
        )
        engagement_score, engagement_desc, event_count = self._calc_learning_engagement(
            user_uuid=user_uuid, course_id=course_id
        )
        resource_score, resource_desc = self._calc_resource_utilization(
            user_uuid=user_uuid, course_id=course_id
        )

        # 计算总体评分（加权平均）
        overall_score = round(
            mastery_score * WEIGHT_MASTERY
            + assessment_score * WEIGHT_ASSESSMENT
            + engagement_score * WEIGHT_ENGAGEMENT
            + resource_score * WEIGHT_RESOURCE
        )

        # 构建维度评分列表
        dimensions = [
            ReportDimensionScore(
                key="knowledge_mastery",
                name="知识掌握度",
                score=mastery_score,
                level=_level(mastery_score),
                description=mastery_desc,
            ),
            ReportDimensionScore(
                key="assessment_performance",
                name="测验表现",
                score=assessment_score,
                level=_level(assessment_score),
                description=assessment_desc,
            ),
            ReportDimensionScore(
                key="learning_engagement",
                name="学习参与度",
                score=engagement_score,
                level=_level(engagement_score),
                description=engagement_desc,
            ),
            ReportDimensionScore(
                key="resource_utilization",
                name="资源利用",
                score=resource_score,
                level=_level(resource_score),
                description=resource_desc,
            ),
        ]

        recommendations = self._build_recommendations(
            weak_points=weak_points,
            dimensions=dimensions,
        )

        return LearningReportResponse(
            user_id=user_id,
            course_id=course_id,
            course_title=course_title,
            overall_score=overall_score,
            overall_level=_level(overall_score),
            dimensions=dimensions,
            progress_trend=trend,
            weak_points=weak_points,
            recommendations=recommendations,
            assessment_count=assessment_count,
            event_count=event_count,
            generated_at=datetime.now(timezone.utc),
        )

    def _empty_report(self, *, user_id: str, course_id: str | None) -> LearningReportResponse:
        """用户不存在时返回空报告。"""
        return LearningReportResponse(
            user_id=user_id,
            course_id=course_id,
            course_title=None,
            overall_score=0,
            overall_level="待加强",
            dimensions=[],
            progress_trend=[],
            weak_points=[],
            recommendations=["暂无足够数据生成评估报告，建议开始学习以积累数据。"],
            assessment_count=0,
            event_count=0,
            generated_at=datetime.now(timezone.utc),
        )

    # ---- 用户解析 ----

    def _resolve_user_uuid(self, user_id: str) -> uuid.UUID | None:
        """把登录态的 external_id 字符串解析为 users.id 的真实 UUID。

        若传入的 user_id 本身就是一个合法 UUID，则直接使用；否则按 external_id
        查询用户表。查不到对应用户时返回 None。
        """
        try:
            return uuid.UUID(str(user_id))
        except (ValueError, TypeError):
            pass
        user = self.db.execute(
            select(User).where(User.external_id == user_id)
        ).scalar_one_or_none()
        return user.id if user else None

    # ---- 维度 1：知识掌握度 ----

    def _calc_knowledge_mastery(
        self, *, user_uuid: uuid.UUID, course_id: str | None
    ) -> tuple[int, str, list[str]]:
        """计算知识掌握度评分，并提取薄弱点。

        优先使用课程画像维度评分，若没有课程画像则使用 ConceptMastery 平均值。
        """
        try:
            scores: list[int] = []
            weak_points: list[str] = []

            # 1) 从画像维度中获取掌握度评分
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
                    scores.append(dim.score)
                    # 判断是否为薄弱维度
                    if self._is_weak(dim):
                        weak_points.append(dim.dimension_name or dim.dimension_key)

            # 2) 从 ConceptMastery 获取掌握度评分
            mastery_rows = self.db.execute(
                select(ConceptMastery).where(
                    ConceptMastery.user_id == user_uuid,
                )
            ).scalars().all()
            for row in mastery_rows:
                if course_id and str(row.course_id) != course_id:
                    continue
                scores.append(row.mastery)
                if row.mastery < LEVEL_FAIR:
                    concept = self.db.get(CourseConcept, row.concept_id) if row.concept_id else None
                    name = concept.title if concept else f"概念({row.concept_id})"
                    weak_points.append(name)

            if not scores:
                return 0, "暂无画像和掌握度数据", []

            avg_score = round(sum(scores) / len(scores))
            desc = f"基于 {len(scores)} 项掌握度指标，平均分为 {avg_score}"
            return avg_score, desc, weak_points
        except Exception:
            logger.exception("计算知识掌握度失败")
            self.db.rollback()
            return 0, "计算知识掌握度时出错", []

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
        global_profile = self.db.execute(
            select(CourseProfile).where(CourseProfile.user_id == user_uuid).limit(1)
        ).scalar_one_or_none()
        return global_profile

    def _is_weak(self, dim: ProfileDimension) -> bool:
        """判断画像维度是否为薄弱维度。"""
        if dim.dimension_key in LOW_SCORE_WEAK_KEYS:
            return dim.score < LEVEL_FAIR
        if dim.dimension_key in HIGH_SCORE_WEAK_KEYS:
            return dim.score > (100 - LEVEL_FAIR)
        return False

    # ---- 维度 2：测验表现 ----

    def _calc_assessment_performance(
        self, *, user_uuid: uuid.UUID, course_id: str | None
    ) -> tuple[int, str, int, list[ReportTrendPoint]]:
        """计算测验表现评分，并生成进步趋势。

        取最近最多 10 次测评评分的平均值，并按周聚合生成趋势数据。
        """
        try:
            query = (
                select(Assessment)
                .where(Assessment.user_id == user_uuid)
                .order_by(Assessment.created_at.desc())
                .limit(10)
            )
            if course_id:
                query = query.where(Assessment.course_id == course_id)
            assessments = self.db.execute(query).scalars().all()

            if not assessments:
                return 0, "暂无测评记录", 0, []

            # 计算平均分
            scores = [a.score for a in assessments]
            avg_score = round(sum(scores) / len(scores))
            desc = f"最近 {len(assessments)} 次测评平均分为 {avg_score}"

            # 生成进步趋势（按周聚合）
            trend = self._build_assessment_trend(
                user_uuid=user_uuid, course_id=course_id
            )

            return avg_score, desc, len(assessments), trend
        except Exception:
            logger.exception("计算测验表现失败")
            self.db.rollback()
            return 0, "计算测验表现时出错", 0, []

    def _build_assessment_trend(
        self, *, user_uuid: uuid.UUID, course_id: str | None
    ) -> list[ReportTrendPoint]:
        """按天聚合测验评分，生成最近 TREND_WEEKS 周的趋势数据。

        使用方法:
            PostgreSQL 的 date_trunc 无法跨方言使用，故这里按天分组后，在内存中
            合并且只保留最近的 TREND_WEEKS 个数据点，保证跨数据库可移植。
        """
        try:
            now = datetime.now(timezone.utc)
            week_start = now - timedelta(weeks=TREND_WEEKS)

            query = (
                select(
                    cast(Assessment.created_at, Date).label("day"),
                    func.avg(Assessment.score).label("avg_score"),
                )
                .where(
                    Assessment.user_id == user_uuid,
                    Assessment.created_at >= week_start,
                )
            )
            if course_id:
                query = query.where(Assessment.course_id == course_id)
            query = query.group_by(cast(Assessment.created_at, Date)).order_by("day")

            rows = self.db.execute(query).all()
            if not rows:
                return []

            # 每个有测评的日期生成一个数据点，按日期自然升序
            trends: list[ReportTrendPoint] = []
            for row in rows:
                day = row.day
                label = day.strftime("%Y-%m-%d")
                score = round(row.avg_score)
                trends.append(ReportTrendPoint(label=label, score=score, metric="测验平均分"))

            # 只保留最近的 TREND_WEEKS 个数据点
            return trends[-TREND_WEEKS:]
        except Exception:
            logger.exception("构建进步趋势失败")
            return []

    # ---- 维度 3：学习参与度 ----

    def _calc_learning_engagement(
        self, *, user_uuid: uuid.UUID, course_id: str | None
    ) -> tuple[int, str, int]:
        """计算学习参与度评分。

        统计近 30 天学习行为事件总数，按事件数量折算参与度评分。
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            total_events = 0

            # 1) 业务学习事件表
            event_query = select(func.count(LearningEvent.id)).where(
                LearningEvent.user_id == user_uuid,
                LearningEvent.created_at >= cutoff,
            )
            if course_id:
                event_query = event_query.where(LearningEvent.course_id == course_id)
            biz_count = self.db.execute(event_query).scalar() or 0
            total_events += biz_count

            # 2) TA 学生事件表
            ta_query = select(func.count(StudentLearningEvent.id)).where(
                StudentLearningEvent.student_id == user_uuid,
                StudentLearningEvent.created_at >= cutoff,
            )
            if course_id:
                # course_id 在 student_learning_events 中是 String(36)，cast 后比较
                ta_query = ta_query.where(cast(StudentLearningEvent.course_id, String) == course_id)
            ta_count = self.db.execute(ta_query).scalar() or 0
            total_events += ta_count

            # 按事件数量折算评分
            if total_events >= ENGAGEMENT_HIGH:
                score = 90
            elif total_events >= ENGAGEMENT_MEDIUM:
                score = 70
            elif total_events >= ENGAGEMENT_LOW:
                score = 50
            else:
                score = 30

            desc = f"近 30 天共 {total_events} 次学习行为"
            return score, desc, total_events
        except Exception:
            logger.exception("计算学习参与度失败")
            self.db.rollback()
            return 0, "计算学习参与度时出错", 0

    # ---- 维度 4：资源利用 ----

    def _calc_resource_utilization(
        self, *, user_uuid: uuid.UUID, course_id: str | None
    ) -> tuple[int, str]:
        """计算资源利用评分。

        统计用户访问过的资源（通过 LearningEvent 中的 resource_view 事件）
        以及资源表本身的 view_count。
        """
        try:
            total_views = 0

            # 1) 从 LearningEvent 统计 resource_view 事件数
            view_query = select(func.count(LearningEvent.id)).where(
                LearningEvent.user_id == user_uuid,
                LearningEvent.event_type == "resource_view",
            )
            if course_id:
                view_query = view_query.where(LearningEvent.course_id == course_id)
            view_events = self.db.execute(view_query).scalar() or 0
            total_views += view_events

            # 2) 从 Resource 表统计用户课程的资源查看次数
            resource_query = select(func.sum(Resource.view_count)).where(Resource.view_count > 0)
            if course_id:
                resource_query = resource_query.where(Resource.course_id == course_id)
            resource_views = self.db.execute(resource_query).scalar() or 0
            total_views += resource_views

            # 折算评分
            if total_views >= 50:
                score = 90
            elif total_views >= 20:
                score = 70
            elif total_views >= 5:
                score = 50
            elif total_views > 0:
                score = 40
            else:
                score = 0

            desc = f"共 {total_views} 次资源使用行为"
            return score, desc
        except Exception:
            logger.exception("计算资源利用失败")
            self.db.rollback()
            return 0, "计算资源利用时出错"

    # ---- 建议生成 ----

    def _build_recommendations(
        self,
        *,
        weak_points: list[str],
        dimensions: list[ReportDimensionScore],
    ) -> list[str]:
        """根据薄弱点和维度评分生成改进建议。"""
        recommendations: list[str] = []

        if weak_points:
            weak_str = "、".join(weak_points[:5])
            recommendations.append(f"重点关注薄弱知识点：{weak_str}，建议安排针对性复习。")

        for dim in dimensions:
            if dim.score < LEVEL_FAIR:
                if dim.key == "knowledge_mastery":
                    recommendations.append("知识掌握度偏低，建议通过系统学习和练习巩固基础知识点。")
                elif dim.key == "assessment_performance":
                    recommendations.append("测验表现不佳，建议多做练习并分析错因，针对性提升薄弱环节。")
                elif dim.key == "learning_engagement":
                    recommendations.append("学习参与度不足，建议制定规律的学习计划，保持持续学习节奏。")
                elif dim.key == "resource_utilization":
                    recommendations.append("资源利用率较低，建议充分利用平台提供的学习资料和视频资源。")

        if not recommendations:
            recommendations.append("整体表现良好，继续保持当前学习节奏，可以尝试挑战更高难度的内容。")

        return recommendations

    # ---- 通用辅助 ----

    def _course_title(self, course_id: str) -> str | None:
        """查询课程标题。"""
        try:
            from app.models import Course
            course = self.db.get(Course, course_id)
            return course.title if course else None
        except Exception:
            return None