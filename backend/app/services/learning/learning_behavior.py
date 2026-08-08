from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import StudentLearningEvent, User
from app.schemas.learning_event import LearningEventDimension


class LearningBehaviorService:
    """学生学习行为事件的采集与聚合统计服务。

    复用 0045_ta_portal_base 迁移建立的 student_learning_events 表，不改 schema。
    采集时把 event_data 与 session_id 合并写入 event_metadata(JSONB)；
    聚合时按天 / 按周 / 按课程维度分组并统计事件类型分布。

    参数:
        db: 当前请求使用的 SQLAlchemy 会话。

    副作用/失败模式:
        record_event 会写入并提交事务；aggregate 仅读取数据库。
        数据库异常会向上抛出到路由层。
    """

    def __init__(self, db: Session) -> None:
        """保存数据库会话，供采集与聚合方法使用。"""
        self.db = db

    @staticmethod
    def _build_metadata(event_data: dict[str, Any] | None, session_id: str | None) -> dict[str, Any]:
        """合并事件数据与会话标识，构造写入 event_metadata 的载荷。

        参数:
            event_data: 前端传入的事件元数据，可为空。
            session_id: 学习会话标识，可为空。

        返回值:
            合并后的字典；session_id 存在时写入其 "session_id" 键。

        副作用/失败模式:
            无外部副作用；输入为 None 时回退到空字典。
        """
        payload: dict[str, Any] = dict(event_data or {})
        if session_id:
            payload["session_id"] = session_id
        return payload

    def resolve_student_id(self, external_id: str) -> str | None:
        """按外部标识解析用户的数据库主键，作为 student_id 写入。

        参数:
            external_id: 当前登录用户的外部标识（CurrentUser.id）。

        返回值:
            解析到的 users.id 字符串；用户不存在时返回 None。

        副作用/失败模式:
            仅读取数据库；查询异常会向上抛出。
        """
        user = self.db.execute(select(User).where(User.external_id == external_id)).scalar_one_or_none()
        return str(user.id) if user else None

    def record_event(
        self,
        *,
        student_id: str,
        course_id: str | None,
        event_type: str,
        event_data: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> StudentLearningEvent:
        """采集一条学生学习行为事件并提交。

        参数:
            student_id: 已解析的 users.id 字符串，写入 student_id。
            course_id: 事件关联课程 ID，可为空。
            event_type: 事件类型，需在枚举范围内。
            event_data: 事件元数据载荷，写入 event_metadata。
            session_id: 学习会话标识，合并进 event_metadata。

        返回值:
            已提交并刷新的学习事件模型。

        副作用/失败模式:
            会写入 student_learning_events 表并提交事务；数据库异常会向上抛出。
            当 event_type 为 resource_view 时，同步转写一条画像证据链记录；
            证据写入失败不回滚已提交的事件，仅记录日志，避免画像耦合影响行为采集。
        """
        event = StudentLearningEvent(
            student_id=student_id,
            course_id=course_id,
            event_type=event_type,
            event_metadata=self._build_metadata(event_data, session_id),
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        # 资源浏览事件同步转写画像证据，支撑资源偏好维度与推荐
        if event_type == "resource_view":
            self._write_resource_usage_evidence(
                student_id=student_id,
                course_id=course_id,
                event_data=event_data or {},
            )
        return event

    def _write_resource_usage_evidence(
        self,
        *,
        student_id: str,
        course_id: str | None,
        event_data: dict[str, Any],
    ) -> None:
        """把 resource_view 事件转写为画像证据链记录。

        从 event_data 提取 resource_id / resource_title / resource_type，
        通过 LearningProfileRepository 写入一条 source_type="resource_usage" 证据。
        证据写入失败仅记录日志，不影响已提交的学习行为事件。

        参数:
            student_id: 已解析的 users.id 字符串。
            course_id: 事件关联课程 ID，可为空。
            event_data: 前端上报的资源元数据，含 resource_id / resource_title / resource_type。
        """
        import logging

        logger = logging.getLogger(__name__)

        resource_id = event_data.get("resource_id") or event_data.get("resource_code")
        if not resource_id:
            # 缺少资源标识无法构造证据，跳过（事件本身已正常落库）
            return
        resource_title = str(event_data.get("resource_title") or "资源浏览")
        resource_type = event_data.get("resource_type")

        # 延迟 import 避免学习行为服务与画像服务形成循环依赖
        from app.models import Course
        from app.services.profile.repository import LearningProfileRepository

        user = self.db.get(User, student_id)
        if not user:
            return
        course = None
        if course_id:
            course = self.db.execute(
                select(Course).where(Course.id == course_id)
            ).scalar_one_or_none()
        try:
            repo = LearningProfileRepository(self.db)
            repo.record_resource_usage_evidence(
                user=user,
                course=course,
                resource_id=str(resource_id),
                resource_title=resource_title,
                resource_type=str(resource_type) if resource_type else None,
            )
            self.db.commit()
        except Exception:  # noqa: BLE001 - 证据写入失败不应影响行为采集主流程
            self.db.rollback()
            logger.warning("资源使用证据写入失败 student_id=%s resource_id=%s", student_id, resource_id, exc_info=True)

    @staticmethod
    def _group_rows(rows: list[tuple[Any, str]], dimension: LearningEventDimension) -> list[dict[str, Any]]:
        """将数据库分组查询结果聚合为桶列表（纯函数，便于单测）。

        参数:
            rows: 查询返回的 (bucket_key, event_type, count) 三元组列表；
                  course 维度时 bucket_key 可能为 None（跨课程事件）。
            dimension: 当前聚合维度。

        返回值:
            桶字典列表，每项含 key/total/by_type；按 key 排序。

        副作用/失败模式:
            无外部副作用；bucket_key 为 None 时用 "uncategorized" 占位。
        """
        buckets: dict[str, dict[str, Any]] = {}
        for raw_key, event_type, count in rows:
            key = str(raw_key) if raw_key is not None else "uncategorized"
            bucket = buckets.setdefault(key, {"key": key, "total": 0, "by_type": {}})
            bucket["total"] += int(count)
            bucket["by_type"][event_type] = bucket["by_type"].get(event_type, 0) + int(count)
        return [buckets[k] for k in sorted(buckets.keys())]

    def aggregate(
        self,
        *,
        student_id: str,
        dimension: LearningEventDimension,
        course_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """按维度聚合当前学生的学习行为事件统计。

        参数:
            student_id: 已解析的 users.id 字符串。
            dimension: 聚合维度，day/week/course。
            course_id: 可选课程过滤，按 courses.id 字符串匹配。
            start_date: 起始时间（含），按 created_at 过滤。
            end_date: 结束时间（含）。

        返回值:
            含 dimension/student_id/course_id/range_start/range_end/buckets/total 的字典。

        副作用/失败模式:
            仅读取数据库；查询异常会向上抛出。
        """
        # 按维度选择分组表达式：day 取日期，week 取所在周起始，course 取课程 ID
        if dimension == "day":
            group_expr = func.DATE(StudentLearningEvent.created_at)
        elif dimension == "week":
            group_expr = func.date_trunc("week", StudentLearningEvent.created_at)
        else:
            group_expr = StudentLearningEvent.course_id

        stmt = (
            select(group_expr, StudentLearningEvent.event_type, func.count().label("count"))
            .where(StudentLearningEvent.student_id == student_id)
            .group_by(group_expr, StudentLearningEvent.event_type)
        )
        if course_id is not None:
            stmt = stmt.where(StudentLearningEvent.course_id == course_id)
        if start_date is not None:
            stmt = stmt.where(StudentLearningEvent.created_at >= start_date)
        if end_date is not None:
            stmt = stmt.where(StudentLearningEvent.created_at <= end_date)

        rows = self.db.execute(stmt).all()
        buckets = self._group_rows(list(rows), dimension)
        total = sum(bucket["total"] for bucket in buckets)
        return {
            "dimension": dimension,
            "student_id": student_id,
            "course_id": course_id,
            "range_start": start_date,
            "range_end": end_date,
            "buckets": buckets,
            "total": total,
        }

    @staticmethod
    def default_range(days: int = 30) -> tuple[datetime, datetime]:
        """生成默认的最近 N 天统计区间（UTC）。

        参数:
            days: 往前回溯的天数，默认 30。

        返回值:
            (起始时间, 结束时间) 二元组，均为带时区的 UTC 时间。

        副作用/失败模式:
            无外部副作用。
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        return start, end
