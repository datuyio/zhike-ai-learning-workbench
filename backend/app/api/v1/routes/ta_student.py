"""助教端学生侧路由：作业查看/提交（前缀 /ta-student）。

TA 端用 require_ta，学生端用 get_current_user + 学生身份解析，
班级归属通过 ta_class_students 校验，保证学生只能操作自己所在班级的资源。
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.routes.ta._shared import (
    _OBJECTIVE_QUESTION_TYPES,
    _compute_is_late,
    _grade_quiz_attempt,
    _require_uuid,
    _resolve_submission_delta,
)
from app.core.deps import get_current_user, get_db
from app.models.ta_assignment import TaAssignment, TaAssignmentQuestion, TaSubmission
from app.models.ta_class import TaClass
from app.models.ta_class_student import TaClassStudent
from app.models.ta_grading_record import TaGradingRecord
from app.models.ta_notification import TaNotification
from app.models.ta_quiz import TaQuiz, TaQuizQuestion, TaQuizAttempt
from app.models.user import User

router = APIRouter(prefix="/ta-student", tags=["ta-student"])


def _resolve_student(db: Session, current_user: Any) -> uuid.UUID | None:
    """把当前登录用户解析为学生内部 UUID；非学生角色返回 None。"""
    user = db.execute(select(User).where(User.external_id == current_user.id)).scalar_one_or_none()
    if not user or user.role_code != "student":
        return None
    return user.id


def _student_class_ids(db: Session, student_id: uuid.UUID) -> list[Any]:
    """学生所在班级内部 UUID 列表。"""
    return list(
        db.execute(
            select(TaClassStudent.class_id).where(TaClassStudent.student_id == student_id)
        ).scalars().all()
    )


def _build_notification_dict(n: TaNotification) -> dict[str, Any]:
    """通知 ORM → 响应 dict。"""
    return {
        "id": str(n.id),
        "title": n.title,
        "body": n.body,
        "notification_type": n.notification_type,
        "source_type": n.source_type,
        "source_id": n.source_id,
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


class SubmissionRequest(BaseModel):
    """提交作业请求体：单题提交 answer 文本；多题提交 answers {question_id: 作答}。"""
    answer: str | None = None
    answers: dict[str, str] | None = None


class QuizSubmitRequest(BaseModel):
    """测验提交请求体：{question_id: 作答}。"""
    answers: dict[str, str] = Field(min_length=1)


@router.get("/assignments")
async def list_assignments(
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """当前学生可见的已发布作业（其所在班级的 published 作业）。"""
    student_id = _resolve_student(db, current_user)
    if student_id is None:
        return []
    class_ids = _student_class_ids(db, student_id)
    if not class_ids:
        return []
    assignments = db.execute(
        select(TaAssignment)
        .where(
            TaAssignment.class_id.in_(class_ids),
            TaAssignment.status == "published",
        )
        .order_by(TaAssignment.created_at.desc())
    ).scalars().all()
    submission_rows = db.execute(
        select(TaSubmission).where(
            TaSubmission.assignment_id.in_([a.id for a in assignments]),
            TaSubmission.student_id == student_id,
        )
    ).scalars().all()
    submission_by_assignment = {row.assignment_id: row for row in submission_rows}
    # 批量统计多题作业的题目数
    assignment_ids = [a.id for a in assignments]
    question_counts: dict[Any, int] = {}
    if assignment_ids:
        rows = db.execute(
            select(TaAssignmentQuestion.assignment_id, func.count(TaAssignmentQuestion.id))
            .where(TaAssignmentQuestion.assignment_id.in_(assignment_ids))
            .group_by(TaAssignmentQuestion.assignment_id)
        ).all()
        question_counts = {assignment_id: count for assignment_id, count in rows}
    # 已提交作业的得分（多题自动判分 / 单题批改后）
    grading_ids = [row.grading_record_id for row in submission_rows if row.grading_record_id]
    grade_by_id: dict[Any, TaGradingRecord] = {}
    if grading_ids:
        grade_rows = db.execute(select(TaGradingRecord).where(TaGradingRecord.id.in_(grading_ids))).scalars().all()
        grade_by_id = {g.id: g for g in grade_rows}
    return [
        {
            "id": str(a.id),
            "title": a.title,
            "description": a.description,
            "question_type": a.question_type,
            "options": a.options or [],
            "total_score": a.total_score,
            "question_count": question_counts.get(a.id, 0),
            "due_at": a.due_at.isoformat() if a.due_at else None,
            "late_policy": a.late_policy,
            "late_penalty_ratio": a.late_penalty_ratio,
            "status": a.status,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "submitted": a.id in submission_by_assignment,
            "attempt_number": submission_by_assignment[a.id].attempt_number if a.id in submission_by_assignment else 0,
            "score": (
                grade_by_id[submission_by_assignment[a.id].grading_record_id].score
                if a.id in submission_by_assignment and submission_by_assignment[a.id].grading_record_id
                and grade_by_id.get(submission_by_assignment[a.id].grading_record_id)
                else None
            ),
            "submitted_at": (
                submission_by_assignment[a.id].submitted_at.isoformat()
                if a.id in submission_by_assignment and submission_by_assignment[a.id].submitted_at
                else None
            ),
        }
        for a in assignments
    ]


@router.get("/assignments/{assignment_id}/questions")
async def get_assignment_questions(
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """当前学生可见的作业题目详情（不含答案，仅 published 且归属本人班级）。

    单题旧作业返回 questions 为空，由前端按 question_type 渲染原交互；
    多题作业返回题目快照列表，前端逐题作答。
    """
    student_id = _resolve_student(db, current_user)
    if student_id is None:
        raise HTTPException(status_code=403, detail="当前账号没有学生权限")
    assignment_id_uuid = _require_uuid(assignment_id, "作业不存在")
    assignment = db.get(TaAssignment, assignment_id_uuid)
    if not assignment or assignment.status != "published":
        raise HTTPException(status_code=404, detail="作业不存在")
    class_ids = _student_class_ids(db, student_id)
    if assignment.class_id not in class_ids:
        raise HTTPException(status_code=404, detail="作业不存在")
    questions = db.execute(
        select(TaAssignmentQuestion).where(TaAssignmentQuestion.assignment_id == assignment.id)
        .order_by(TaAssignmentQuestion.order_index)
    ).scalars().all()
    result = {
        "id": str(assignment.id),
        "title": assignment.title,
        "description": assignment.description,
        "question_type": assignment.question_type,
        "options": assignment.options or [],
        "total_score": assignment.total_score,
        "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
        "questions": [
            {
                "id": str(q.id),
                "prompt": q.prompt,
                "question_type": q.question_type,
                "options": q.options or [],
                "score": q.score,
            }
            for q in questions
        ],
    }
    return result


@router.post("/assignments/{assignment_id}/submit")
async def submit_assignment(
    assignment_id: str,
    payload: SubmissionRequest,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """提交作业：closed 拒绝；重复提交覆盖并 attempt+1；同步生成/更新批改记录。

    生成的 TaGradingRecord(status=pending) 自动进入既有 ai-grade / manual-grade / stats 流水线。

    注：ta_submissions 的唯一约束作为并发双击场景的最终兜底，演示环境按顺序操作即可避免。
    """
    student_id = _resolve_student(db, current_user)
    if student_id is None:
        raise HTTPException(status_code=403, detail="当前账号没有学生权限")
    assignment_id_uuid = _require_uuid(assignment_id, "作业不存在")
    assignment = db.get(TaAssignment, assignment_id_uuid)
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")
    class_ids = _student_class_ids(db, student_id)
    if assignment.class_id not in class_ids:
        raise HTTPException(status_code=404, detail="作业不存在")
    if assignment.status == "closed":
        raise HTTPException(status_code=403, detail="作业已关闭，无法提交")
    if assignment.status != "published":
        raise HTTPException(status_code=403, detail="作业未发布")

    now = datetime.now(timezone.utc)
    is_late = _compute_is_late(assignment.due_at, now)
    if assignment.late_policy == "reject" and is_late:
        raise HTTPException(status_code=403, detail="作业已过截止时间，迟交不予受理")
    existing = db.execute(
        select(TaSubmission).where(
            TaSubmission.assignment_id == assignment.id,
            TaSubmission.student_id == student_id,
        )
    ).scalar_one_or_none()

    # 多题作业：载入题目快照，客观题自动判分，主观题进入 AI 批改流水线
    questions = db.execute(
        select(TaAssignmentQuestion).where(TaAssignmentQuestion.assignment_id == assignment.id)
        .order_by(TaAssignmentQuestion.order_index)
    ).scalars().all()
    if questions:
        if not payload.answers:
            raise HTTPException(status_code=400, detail="多题作业请逐题作答后提交")
        objective_questions = [q for q in questions if q.question_type in _OBJECTIVE_QUESTION_TYPES]
        subjective_questions = [q for q in questions if q.question_type not in _OBJECTIVE_QUESTION_TYPES]
        objective_score, _details = _grade_quiz_attempt(payload.answers, objective_questions) if objective_questions else (0.0, {})
        total_score = sum(q.score for q in questions)
        answers_json = json.dumps(payload.answers, ensure_ascii=False)
        has_subjective = bool(subjective_questions)
        # 客观题作答快照写入 submission（answer 列存 JSON 文本兜底，answers 列存结构化）
        if existing:
            existing.answer = answers_json
            existing.answers = payload.answers
            existing.submitted_at = now
            existing.is_late = is_late
            existing.attempt_number = _resolve_submission_delta(existing.attempt_number)
            submission = existing
        else:
            submission = TaSubmission(
                assignment_id=assignment.id,
                student_id=student_id,
                answer=answers_json,
                answers=payload.answers,
                submitted_at=now,
                is_late=is_late,
                attempt_number=1,
            )
            db.add(submission)

        grading = None
        if submission.grading_record_id:
            grading = db.get(TaGradingRecord, submission.grading_record_id)
        if grading is None:
            grading = TaGradingRecord(
                title=assignment.title,
                student_id=student_id,
                course_id=assignment.course_id,
                class_id=assignment.class_id,
                concept_id=assignment.concept_id,
                total_score=total_score,
                student_answer=answers_json,
                objective_score=objective_score,
                is_late=is_late,
                attempt_number=submission.attempt_number,
                question_type="multi",
                status="pending" if has_subjective else "graded",
                grader_type="ai_assisted" if has_subjective else "auto",
                score=None if has_subjective else objective_score,
            )
            db.add(grading)
            db.flush()
            submission.grading_record_id = grading.id
        else:
            grading.student_answer = answers_json
            grading.objective_score = objective_score
            grading.is_late = is_late
            grading.attempt_number = submission.attempt_number
            grading.grader_type = "ai_assisted" if has_subjective else "auto"
            grading.late_penalty = None
            if has_subjective:
                grading.status = "pending"
                grading.score = None
                grading.ai_comment = None
                grading.ta_comment = None
                grading.feedback = None
            else:
                grading.status = "graded"
                grading.score = objective_score
                grading.ai_comment = None
                grading.ta_comment = None
                grading.feedback = None
        db.commit()
        return {
            "id": str(submission.id),
            "is_late": is_late,
            "attempt_number": submission.attempt_number,
            "grading_record_id": str(grading.id),
            "score": None if has_subjective else objective_score,
            "total_score": total_score,
            "has_subjective": has_subjective,
            "message": "提交成功" + ("，客观题已自动判分" if not has_subjective else "，客观题已判分，主观题待 AI 批改"),
        }

    # 单题作业旧路径：文本提交，生成 pending 批改记录进入 AI/手动批改流水线
    if not payload.answer:
        raise HTTPException(status_code=400, detail="请填写作答内容")
    if existing:
        existing.answer = payload.answer
        existing.submitted_at = now
        existing.is_late = is_late
        existing.attempt_number = _resolve_submission_delta(existing.attempt_number)
        submission = existing
    else:
        submission = TaSubmission(
            assignment_id=assignment.id,
            student_id=student_id,
            answer=payload.answer,
            submitted_at=now,
            is_late=is_late,
            attempt_number=1,
        )
        db.add(submission)

    grading = None
    if submission.grading_record_id:
        grading = db.get(TaGradingRecord, submission.grading_record_id)
    if grading is None:
        grading = TaGradingRecord(
            title=assignment.title,
            student_id=student_id,
            course_id=assignment.course_id,
            class_id=assignment.class_id,
            concept_id=assignment.concept_id,
            total_score=assignment.total_score,
            student_answer=payload.answer,
            reference_answer=assignment.correct_answer,
            is_late=is_late,
            attempt_number=submission.attempt_number,
            question_type=assignment.question_type or "short_answer",
            status="pending",
            grader_type="ai_assisted",
        )
        db.add(grading)
        db.flush()
        submission.grading_record_id = grading.id
    else:
        grading.student_answer = payload.answer
        grading.reference_answer = assignment.correct_answer
        grading.is_late = is_late
        grading.attempt_number = submission.attempt_number
        grading.status = "pending"
        grading.score = None
        grading.ai_comment = None
        grading.ta_comment = None
        grading.feedback = None
        grading.grader_type = "ai_assisted"
        grading.late_penalty = None
    db.commit()
    return {
        "id": str(submission.id),
        "is_late": is_late,
        "attempt_number": submission.attempt_number,
        "grading_record_id": str(grading.id),
        "message": "提交成功",
    }


@router.get("/notifications")
async def list_notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """学生通知收件箱：按时间倒序，含 unread_count。非学生角色返回空。"""
    student_id = _resolve_student(db, current_user)
    if student_id is None:
        return {"items": [], "unread_count": 0}
    stmt = select(TaNotification).where(TaNotification.student_id == student_id)
    if unread_only:
        stmt = stmt.where(TaNotification.is_read.is_(False))
    stmt = stmt.order_by(TaNotification.created_at.desc()).limit(50)
    items = db.execute(stmt).scalars().all()
    unread = db.execute(
        select(TaNotification).where(
            TaNotification.student_id == student_id,
            TaNotification.is_read.is_(False),
        )
    ).scalars().all()
    return {
        "items": [_build_notification_dict(n) for n in items],
        "unread_count": len(unread),
    }


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> dict[str, str]:
    """标记通知已读（幂等：他人通知返回 404 不泄露存在性）。"""
    student_id = _resolve_student(db, current_user)
    if student_id is None:
        raise HTTPException(status_code=403, detail="当前账号没有学生权限")
    notification_id_uuid = _require_uuid(notification_id, "通知不存在")
    n = db.get(TaNotification, notification_id_uuid)
    if not n or n.student_id != student_id:
        raise HTTPException(status_code=404, detail="通知不存在")
    n.is_read = True
    db.commit()
    return {"message": "已标记已读"}


@router.get("/quizzes")
async def list_quizzes(
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """当前学生可见的已发布测验（其所在班级的 published 测验）。"""
    student_id = _resolve_student(db, current_user)
    if student_id is None:
        return []
    class_ids = _student_class_ids(db, student_id)
    if not class_ids:
        return []
    quizzes = db.execute(
        select(TaQuiz)
        .where(TaQuiz.class_id.in_(class_ids), TaQuiz.status == "published")
        .order_by(TaQuiz.created_at.desc())
    ).scalars().all()
    result = []
    for q in quizzes:
        d = {
            "id": str(q.id),
            "title": q.title,
            "description": q.description,
            "created_at": q.created_at.isoformat() if q.created_at else None,
        }
        submitted = db.execute(
            select(TaQuizAttempt).where(
                TaQuizAttempt.quiz_id == q.id,
                TaQuizAttempt.student_id == student_id,
            )
        ).scalar_one_or_none()
        d["submitted"] = submitted is not None
        d["score"] = submitted.score if submitted else None
        result.append(d)
    return result


@router.get("/quizzes/{quiz_id}")
async def get_quiz_detail(
    quiz_id: str,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """当前学生可见的测验题目详情（不含答案，仅 published 且归属本人班级）。"""
    student_id = _resolve_student(db, current_user)
    if student_id is None:
        raise HTTPException(status_code=403, detail="当前账号没有学生权限")
    quiz_id_uuid = _require_uuid(quiz_id, "测验不存在")
    quiz = db.get(TaQuiz, quiz_id_uuid)
    if not quiz or quiz.status != "published":
        raise HTTPException(status_code=404, detail="测验不存在")
    class_ids = _student_class_ids(db, student_id)
    if quiz.class_id not in class_ids:
        raise HTTPException(status_code=404, detail="测验不存在")
    questions = db.execute(
        select(TaQuizQuestion).where(TaQuizQuestion.quiz_id == quiz.id).order_by(TaQuizQuestion.order_index)
    ).scalars().all()
    return {
        "id": str(quiz.id),
        "title": quiz.title,
        "description": quiz.description,
        "questions": [
            {
                "id": str(q.id),
                "prompt": q.prompt,
                "question_type": q.question_type,
                "options": q.options or [],
                "score": q.score,
            }
            for q in questions
        ],
    }


@router.post("/quizzes/{quiz_id}/submit")
async def submit_quiz(
    quiz_id: str,
    payload: QuizSubmitRequest,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """提交测验：确定性判分，upsert 作答记录并写入批改记录(graded/auto)。

    注：ta_quiz_attempts 的唯一约束作为并发双击兜底，演示环境顺序操作即可。
    """
    student_id = _resolve_student(db, current_user)
    if student_id is None:
        raise HTTPException(status_code=403, detail="当前账号没有学生权限")
    quiz_id_uuid = _require_uuid(quiz_id, "测验不存在")
    quiz = db.get(TaQuiz, quiz_id_uuid)
    if not quiz:
        raise HTTPException(status_code=404, detail="测验不存在")
    class_ids = _student_class_ids(db, student_id)
    if quiz.class_id not in class_ids:
        raise HTTPException(status_code=404, detail="测验不存在")
    if quiz.status == "closed":
        raise HTTPException(status_code=403, detail="测验已关闭，无法提交")
    if quiz.status != "published":
        raise HTTPException(status_code=403, detail="测验未发布")

    questions = db.execute(
        select(TaQuizQuestion).where(TaQuizQuestion.quiz_id == quiz.id).order_by(TaQuizQuestion.order_index)
    ).scalars().all()
    total, details = _grade_quiz_attempt(payload.answers, questions)

    now = datetime.now(timezone.utc)
    existing = db.execute(
        select(TaQuizAttempt).where(
            TaQuizAttempt.quiz_id == quiz.id,
            TaQuizAttempt.student_id == student_id,
        )
    ).scalar_one_or_none()
    grading = None
    if existing:
        if existing.grading_record_id:
            grading = db.get(TaGradingRecord, existing.grading_record_id)
        existing.answers = payload.answers
        existing.score = total
        existing.submitted_at = now
        attempt = existing
    else:
        attempt = TaQuizAttempt(
            quiz_id=quiz.id,
            student_id=student_id,
            answers=payload.answers,
            score=total,
            submitted_at=now,
        )
        db.add(attempt)

    if grading is None:
        grading = TaGradingRecord(
            title=f"随堂测验：{quiz.title}",
            student_id=student_id,
            course_id=quiz.course_id,
            class_id=quiz.class_id,
            grader_type="auto",
            question_type="quiz",
            score=total,
            total_score=sum(q.score for q in questions),
            student_answer=json.dumps(payload.answers, ensure_ascii=False),
            status="graded",
        )
        db.add(grading)
        db.flush()
        attempt.grading_record_id = grading.id
    else:
        grading.score = total
        grading.total_score = sum(q.score for q in questions)
        grading.student_answer = json.dumps(payload.answers, ensure_ascii=False)
        grading.status = "graded"
    db.commit()
    return {
        "id": str(attempt.id),
        "score": total,
        "total_score": sum(q.score for q in questions),
        "grading_record_id": str(grading.id),
        "details": details,
        "message": "提交成功",
    }


class JoinClassRequest(BaseModel):
    """凭邀请码加入班级的请求体。"""
    invite_code: str = Field(min_length=1, max_length=16)


def _class_to_dict(cls: TaClass, joined_at: datetime | None = None, ta_name: str | None = None) -> dict[str, Any]:
    """班级 ORM → 学生端响应 dict。"""
    return {
        "id": str(cls.id),
        "name": cls.name,
        "description": cls.description,
        "invite_code": cls.invite_code,
        "student_count": len(cls.students) if cls.students is not None else 0,
        "max_students": cls.max_students,
        "ta_name": ta_name,
        "joined_at": joined_at.isoformat() if joined_at else None,
    }


@router.get("/classes")
async def list_my_classes(
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """当前学生已加入的班级列表（含邀请码，便于同学互相邀请）。"""
    student_id = _resolve_student(db, current_user)
    if student_id is None:
        return []
    rows = db.execute(
        select(TaClass, TaClassStudent.joined_at, User.display_name)
        .join(TaClassStudent, TaClassStudent.class_id == TaClass.id)
        .join(User, User.id == TaClass.ta_user_id)
        .where(TaClassStudent.student_id == student_id, TaClass.is_active == True)
        .order_by(TaClassStudent.joined_at.desc())
    ).all()
    return [_class_to_dict(cls, joined_at, ta_name) for cls, joined_at, ta_name in rows]


@router.post("/classes/join")
async def join_class(
    payload: JoinClassRequest,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """学生凭邀请码加入班级；重复加入幂等返回，满员拒绝。"""
    student_id = _resolve_student(db, current_user)
    if student_id is None:
        raise HTTPException(status_code=403, detail="仅学生账号可加入班级")
    code = payload.invite_code.strip().upper()
    cls = db.execute(
        select(TaClass).where(TaClass.invite_code == code, TaClass.is_active == True)
    ).scalar_one_or_none()
    if cls is None:
        raise HTTPException(status_code=404, detail="邀请码无效，请向老师确认")
    existing = db.execute(
        select(TaClassStudent).where(
            TaClassStudent.class_id == cls.id,
            TaClassStudent.student_id == student_id,
        )
    ).scalar_one_or_none()
    if existing:
        return {"message": "你已在该班级中", "already_member": True, "class": _class_to_dict(cls)}
    if cls.max_students is not None and len(cls.students) >= cls.max_students:
        raise HTTPException(status_code=400, detail="班级人数已满，请联系老师扩容")
    membership = TaClassStudent(class_id=cls.id, student_id=student_id)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return {"message": "已加入班级", "already_member": False, "class": _class_to_dict(cls, membership.joined_at)}


@router.delete("/classes/{class_id}/leave")
async def leave_class(
    class_id: str,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> dict[str, str]:
    """学生退出班级；重复退出幂等。"""
    student_id = _resolve_student(db, current_user)
    if student_id is None:
        raise HTTPException(status_code=403, detail="仅学生账号可退出班级")
    class_id_uuid = _require_uuid(class_id, "班级不存在")
    membership = db.execute(
        select(TaClassStudent).where(
            TaClassStudent.class_id == class_id_uuid,
            TaClassStudent.student_id == student_id,
        )
    ).scalar_one_or_none()
    if membership:
        db.delete(membership)
        db.commit()
    return {"message": "已退出班级"}
