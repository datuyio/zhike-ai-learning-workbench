"""助教端跨领域共享：常量、公共 helper 与模型 re-export。

各领域子模块只允许 import 本模块，禁止子模块之间互相 import，避免循环依赖。
"""
import csv
import io
import json
import logging
import re
import uuid
from urllib.parse import quote
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rate_limit import consume_fixed_window
from app.core.tracing import get_trace_id
from app.models.assessment import Assessment
from app.models.course import Course, CourseConcept
from app.models.learning import ConceptMastery, LearningEvent
from app.models.ta_announcement import TaAnnouncement
from app.models.user import User
from app.models.ta_class import TaClass, generate_class_invite_code
from app.models.ta_class_student import TaClassStudent
from app.models.ta_lesson_plan import TaLessonPlan
from app.models.ta_grading_record import TaGradingRecord
from app.models.ta_alert_record import TaAlertRecord
from app.models.ta_assignment import TaAssignment, TaAssignmentQuestion, TaSubmission
from app.models.ta_alert_action import TaAlertAction
from app.models.ta_notification import TaNotification
from app.models.ta_quiz import TaQuiz, TaQuizQuestion, TaQuizAttempt
from app.models.ta_question_bank import TaQuestionBank
from app.models.resource import Resource

logger = logging.getLogger(__name__)

_EPOCH_UTC = datetime.min.replace(tzinfo=timezone.utc)

# 掌握度阈值：低于该值视为薄弱知识点
_MASTERY_WEAK_THRESHOLD = 60

# 雷达图归一化封顶：资料查阅次数 / 学习事件数 达到该值即 100 分
_RADAR_RESOURCE_CAP = 20
_RADAR_ACTIVITY_CAP = 50

_VALID_LATE_POLICIES = ("reject", "allow_penalty", "allow")

_ALERT_RATE_WINDOW_SECONDS = 3600
_ALERT_RATE_MAX_COUNT = 1

# 四类客观题型：题库/测验/作业多题均按此集合自动判分
_OBJECTIVE_QUESTION_TYPES = {"single_choice", "multiple_choice", "true_false", "blank"}

# 全部题型：客观四类 + 主观两类（简答/代码，走 AI 批改）
_ALL_QUESTION_TYPES = _OBJECTIVE_QUESTION_TYPES | {"short_answer", "code"}


def _user_internal_id(db: Session, user_id_ref: str) -> uuid.UUID | None:
    """按 external_id 或内部 UUID 解析用户内部 UUID，用于与 UUID 外键列比较/写入。

    CurrentUser.id 是 external_id（如 user_xxx），而 TA 表外键均为内部 UUID，
    直接混用会导致 PostgreSQL 报 invalid input syntax for type uuid；班级学生
    列表返回的 student_id 已是内部 UUID，因此这里两种形态都要兼容。
    """
    user = db.execute(select(User).where(User.external_id == user_id_ref)).scalar_one_or_none()
    if user:
        return user.id
    try:
        candidate = uuid.UUID(user_id_ref)
    except (ValueError, TypeError, AttributeError):
        return None
    return candidate if db.get(User, candidate) else None


def _require_uuid(value: str, detail: str) -> uuid.UUID:
    """把字符串路径/查询参数解析为 UUID；非法输入统一 404，避免 UUID 主键查询抛 PG 类型错误。"""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=404, detail=detail) from None


def _apply_page(stmt: Any, limit: int | None, offset: int) -> Any:
    """对列表查询统一应用分页；limit 为 None 时全量返回，否则按 offset 截断。"""
    if limit is not None:
        return stmt.limit(limit).offset(offset)
    return stmt


def _get_or_404(db: Session, model: type, obj_id: str, detail: str):
    """按 UUID 主键取单个资源：非法 UUID 或不存在统一 404，存在返回 ORM 对象。

    消除各路由「_require_uuid → db.get → if not x: raise 404」三连重复。
    """
    obj_uuid = _require_uuid(obj_id, detail)
    obj = db.get(model, obj_uuid)
    if obj is None:
        raise HTTPException(status_code=404, detail=detail)
    return obj


def _class_student_ids(db: Session, class_id: uuid.UUID) -> list[Any]:
    """返回班级学生内部 UUID 列表。"""
    members = db.execute(
        select(TaClassStudent).where(TaClassStudent.class_id == class_id)
    ).scalars().all()
    return [m.student_id for m in members]


def _class_mastery_rows(db: Session, cls: TaClass, student_ids: list[Any]):
    """返回班级学生的 concept_mastery 记录，按班级课程过滤。"""
    stmt = select(ConceptMastery).where(ConceptMastery.user_id.in_(student_ids))
    if cls.course_id:
        stmt = stmt.where(ConceptMastery.course_id == cls.course_id)
    return db.execute(stmt).scalars().all()


def _course_slug(db: Session, course_id) -> str | None:
    """按课程 ID 查找课程 slug 供模型网关路由使用；非法或未找到返回 None。"""
    if course_id is None:
        return None
    try:
        parsed_id = uuid.UUID(str(course_id))
    except (ValueError, TypeError):
        return None
    course = db.get(Course, parsed_id)
    return course.slug if course else None


def _relative_time(dt: datetime | None) -> str:
    """把时间格式化为友好相对文案，用于待办列表元信息。"""
    if not dt:
        return "未知时间"
    minutes = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
    if minutes < 1:
        return "刚刚"
    if minutes < 60:
        return f"{minutes} 分钟前"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} 小时前"
    return f"{hours // 24} 天前"


def _weakness_severity(avg_mastery: float) -> str:
    """按平均掌握度分档薄弱强度：<40 严重 / <55 中等 / <70 轻微 / 其余正常。"""
    if avg_mastery < 40:
        return "严重"
    if avg_mastery < 55:
        return "中等"
    if avg_mastery < 70:
        return "轻微"
    return "正常"


def _compute_is_late(due_at: datetime | None, now: datetime) -> bool:
    """逾期判定：有截止时间且当前时间已过截止 → True，否则 False。"""
    if due_at is None:
        return False
    return now > due_at


def _resolve_submission_delta(existing_attempt: int | None) -> int:
    """提交次数：无历史提交 → 1；已有提交 → 在原次数基础上 +1。"""
    return (existing_attempt or 0) + 1


def _csv_response(rows: list[list[Any]], filename: str) -> StreamingResponse:
    """把行列表编码为 utf-8-sig CSV（Excel 兼容中文）并返回 StreamingResponse。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    content = buffer.getvalue()
    return StreamingResponse(
        iter(["﻿" + content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=\"{quote(filename, safe='')}\"; filename*=UTF-8''{quote(filename, safe='')}"},
    )


def _sse_payload(data: dict[str, Any]) -> str:
    """把事件 dict 编码为 SSE data 帧；default=str 兼容 UUID 等对象。"""
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _render_template(template: str, variables: dict[str, Any]) -> str:
    """把 {key} 占位符替换为变量值，并剥除仍残留的未知占位符，避免花括号泄漏到文案。"""
    result = template
    for key, value in variables.items():
        result = result.replace("{" + key + "}", str(value if value is not None else ""))
    return re.sub(r"\{[^{}]*\}", "", result)


def _create_notifications(
    db: Session,
    student_ids: list[Any],
    title: str,
    body: str,
    notification_type: str,
    source_type: str,
    source_id: str | None = None,
    class_id: uuid.UUID | None = None,
) -> int:
    """批量生成学生通知，返回条数；空学生列表直接 0。"""
    if not student_ids:
        return 0
    for sid in student_ids:
        db.add(TaNotification(
            student_id=sid,
            class_id=class_id,
            title=title,
            body=body,
            notification_type=notification_type,
            source_type=source_type,
            source_id=source_id,
        ))
    db.flush()
    return len(student_ids)


def _normalize_choice_answer(value: str) -> str:
    """把多选作答规范化为有序大写字母串（如 'B,A' → 'AB'），用于等价比较判分。"""
    return "".join(sorted(ch for ch in str(value).upper() if ch.isalpha()))


def _grade_quiz_attempt(
    answers: dict[str, str],
    questions: list[Any],
) -> tuple[float, dict[str, Any]]:
    """客观题逐题判分：返回 (总分, 每题明细 {question_id: {correct, score}})。

    支持四类客观题型：单选/判断精确比较，多选按选项集合规范化比较，
    填空忽略首尾空格与大小写比较；未作答或答错该题 0 分。
    questions 元素需提供 id/answer/score，question_type 缺省按单选处理。
    """
    total = 0.0
    details: dict[str, Any] = {}
    for q in questions:
        qid = str(q.id)
        student = answers.get(qid)
        qtype = getattr(q, "question_type", None) or "single_choice"
        if student is None or str(student).strip() == "":
            correct = False
        elif qtype == "multiple_choice":
            correct = _normalize_choice_answer(student) == _normalize_choice_answer(q.answer or "")
        elif qtype == "blank":
            correct = str(student).strip().lower() == str(q.answer or "").strip().lower()
        else:
            correct = student == q.answer
        s = float(q.score) if correct else 0.0
        total += s
        details[qid] = {"correct": correct, "score": s}
    return total, details
