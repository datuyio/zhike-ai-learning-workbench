"""助教端：作业发布 + 提交 + 成绩导出。"""
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_ta
from ._shared import (
    TaAssignment,
    TaAssignmentQuestion,
    TaClass,
    TaGradingRecord,
    TaQuestionBank,
    TaSubmission,
    User,
    _ALL_QUESTION_TYPES,
    _VALID_LATE_POLICIES,
    _apply_page,
    _class_student_ids,
    _create_notifications,
    _csv_response,
    _require_uuid,
    _user_internal_id,
)

router = APIRouter(prefix="/ta", tags=["ta-portal"])


class AssignmentQuestionInput(BaseModel):
    """作业题目输入（多题作业，手动出题使用）。"""
    prompt: str
    question_type: str = "single_choice"
    options: list[str] | None = None
    answer: str | None = None
    score: float = 10


class AssignmentCreateRequest(BaseModel):
    """创建作业请求体（单题旧路径 + 多题新路径）。

    提供 question_ids（从题库选题）或 questions（手动输入）即创建多题作业，
    题目快照写入 ta_assignment_questions；两者都不提供时走单题旧路径。
    """
    title: str = Field(..., max_length=300)
    description: str | None = None
    class_id: str
    course_id: str | None = None
    concept_id: str | None = None
    question_type: str = Field(default="short_answer", description="单题作业题型: short_answer/code/single_choice/true_false")
    options: list[str] | None = None
    correct_answer: str | None = None
    total_score: float = Field(default=100, gt=0)
    due_at: datetime | None = None
    late_policy: str = "allow_penalty"
    late_penalty_ratio: float = Field(default=0.1, ge=0, le=1)
    question_ids: list[str] | None = None
    questions: list[AssignmentQuestionInput] | None = None


class AssignmentUpdateRequest(BaseModel):
    """编辑作业请求体（仅草稿可改，字段均可选）。"""
    title: str | None = Field(default=None, max_length=300)
    description: str | None = None
    question_type: str | None = None
    options: list[str] | None = None
    correct_answer: str | None = None
    total_score: float | None = Field(default=None, gt=0)
    due_at: datetime | None = None
    late_policy: str | None = None
    late_penalty_ratio: float | None = Field(default=None, ge=0, le=1)
    question_ids: list[str] | None = None
    questions: list[AssignmentQuestionInput] | None = None


def _validate_assignment_question(question_type: str, options: list[str] | None, correct_answer: str | None) -> None:
    """校验单题作业题型字段：客观题必须提供选项与标准答案，判断题答案限 T/F。"""
    if question_type == "true_false":
        if not options or not correct_answer or correct_answer not in {"T", "F"}:
            raise HTTPException(status_code=400, detail="判断题必须提供选项且答案须为 T 或 F")
    elif question_type == "single_choice":
        if not options or len(options) < 2 or not correct_answer:
            raise HTTPException(status_code=400, detail="单选题必须提供至少两个选项与标准答案")
    elif question_type not in {"short_answer", "code", "blank"}:
        raise HTTPException(status_code=400, detail=f"不支持的题型: {question_type}")


def _validate_assignment_question_input(qi: AssignmentQuestionInput) -> None:
    """校验多题作业单题字段合法性（六类题型，客观题必须提供答案）。"""
    if qi.question_type not in _ALL_QUESTION_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的题型: {qi.question_type}")
    if qi.question_type == "true_false":
        if qi.answer not in {"T", "F"}:
            raise HTTPException(status_code=400, detail="判断题答案须为 T 或 F")
    elif qi.question_type in {"single_choice", "multiple_choice"}:
        if not qi.options or len(qi.options) < 2 or not qi.answer:
            raise HTTPException(status_code=400, detail="选择题必须提供至少两个选项与标准答案")
    elif qi.question_type == "blank":
        if not qi.answer:
            raise HTTPException(status_code=400, detail="填空题必须提供标准答案")


def _resolve_assignment_questions(
    db: Session,
    question_ids: list[str] | None,
    questions: list[AssignmentQuestionInput] | None,
) -> list[AssignmentQuestionInput]:
    """把「从题库选题 + 手动输入」合并为统一的作业题目列表（题库题在前）。

    从题库选取的题目按当前题库内容生成快照，保证布置后题目内容稳定；
    至少需要提供一种题目来源，否则返回 400。
    """
    merged: list[AssignmentQuestionInput] = []
    if question_ids:
        id_set = list(dict.fromkeys(question_ids))
        uuid_set = [_require_uuid(qid, "题库题目不存在") for qid in id_set]
        bank_questions = db.execute(
            select(TaQuestionBank).where(TaQuestionBank.id.in_(uuid_set))
        ).scalars().all()
        found = {str(q.id) for q in bank_questions}
        missing = [qid for qid in id_set if qid not in found]
        if missing:
            raise HTTPException(status_code=400, detail=f"题库中不存在以下题目: {', '.join(missing[:5])}")
        merged.extend([
            AssignmentQuestionInput(
                prompt=q.prompt,
                question_type=q.question_type,
                options=q.options,
                answer=q.answer,
                score=q.score,
            )
            for q in bank_questions
        ])
    if questions:
        for qi in questions:
            _validate_assignment_question_input(qi)
        merged.extend(questions)
    if not merged:
        raise HTTPException(status_code=400, detail="请从题库选择题目或手动输入题目")
    return merged


def _save_assignment_questions(db: Session, assignment_id: Any, questions: list[AssignmentQuestionInput]) -> None:
    """全量替换作业题目快照（先删后插）。"""
    db.execute(
        TaAssignmentQuestion.__table__.delete().where(TaAssignmentQuestion.assignment_id == assignment_id)
    )
    for idx, qi in enumerate(questions):
        db.add(TaAssignmentQuestion(
            assignment_id=assignment_id,
            order_index=idx,
            question_type=qi.question_type,
            prompt=qi.prompt,
            options=qi.options,
            answer=qi.answer,
            score=qi.score,
        ))


def _assignment_question_count_map(db: Session, assignment_ids: list[Any]) -> dict[Any, int]:
    """批量统计作业题目数：{assignment_id: 题目数}，空列表返回空 dict。"""
    if not assignment_ids:
        return {}
    rows = db.execute(
        select(TaAssignmentQuestion.assignment_id, func.count(TaAssignmentQuestion.id))
        .where(TaAssignmentQuestion.assignment_id.in_(assignment_ids))
        .group_by(TaAssignmentQuestion.assignment_id)
    ).all()
    return {assignment_id: count for assignment_id, count in rows}


def _assignment_to_dict(a: TaAssignment) -> dict[str, Any]:
    """作业 ORM → 响应 dict。"""
    return {
        "id": str(a.id),
        "title": a.title,
        "description": a.description,
        "class_id": str(a.class_id),
        "course_id": str(a.course_id) if a.course_id else None,
        "concept_id": str(a.concept_id) if a.concept_id else None,
        "question_type": a.question_type,
        "options": a.options or [],
        "correct_answer": a.correct_answer,
        "total_score": a.total_score,
        "due_at": a.due_at.isoformat() if a.due_at else None,
        "late_policy": a.late_policy,
        "late_penalty_ratio": a.late_penalty_ratio,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _build_grades_csv_rows(
    students: list[tuple[str, str]],
    assignment_titles: list[str],
    score_map: dict[tuple[str, str], float],
    total_map: dict[tuple[str, str], float],
) -> list[list[Any]]:
    """构造班级成绩 CSV 行（含表头与末列平均分）。

    students 为 [(student_id, name)]；score_map/total_map 键为 (student_id, title)。
    缺成绩补空串；平均分按满分归一化（Σ得分/Σ满分×100），无成绩为空串。
    """
    header = ["学生", "学生ID"] + assignment_titles + ["平均分"]
    rows: list[list[Any]] = [header]
    for student_id, name in students:
        scores: list[Any] = []
        scored: list[tuple[float, float]] = []
        for title in assignment_titles:
            score = score_map.get((student_id, title))
            scores.append(score if score is not None else "")
            if score is not None:
                total = total_map.get((student_id, title), 100.0) or 100.0
                scored.append((float(score), float(total)))
        avg = round(100 * sum(s for s, _ in scored) / sum(t for _, t in scored), 1) if scored else ""
        rows.append([name, student_id] + scores + [avg])
    return rows


# ===== 作业发布 =====

@router.post("/assignments")
async def create_assignment(
    payload: AssignmentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """创建作业草稿；支持从题库选题/手动出题的多题作业，或单题旧路径。"""
    user_id = _user_internal_id(db, current_user.id)
    if user_id is None:
        raise HTTPException(status_code=403, detail="当前用户不存在")
    if payload.late_policy not in _VALID_LATE_POLICIES:
        raise HTTPException(status_code=400, detail="无效的迟交策略")
    class_id_uuid = _require_uuid(payload.class_id, "目标班级不存在")
    cls = db.get(TaClass, class_id_uuid)
    if not cls or not cls.is_active:
        raise HTTPException(status_code=404, detail="目标班级不存在")
    course_id_uuid = _require_uuid(payload.course_id, "课程不存在") if payload.course_id else None
    concept_id_uuid = _require_uuid(payload.concept_id, "知识点不存在") if payload.concept_id else None

    is_multi = payload.question_ids is not None or payload.questions is not None
    if is_multi:
        # 多题作业：题目快照写入 ta_assignment_questions，满分按题目分值求和
        resolved = _resolve_assignment_questions(db, payload.question_ids, payload.questions)
        total_score = sum(q.score for q in resolved)
        assignment = TaAssignment(
            ta_user_id=user_id,
            class_id=class_id_uuid,
            course_id=course_id_uuid,
            concept_id=concept_id_uuid,
            title=payload.title,
            description=payload.description,
            question_type="multi",
            options=None,
            correct_answer=None,
            total_score=total_score,
            due_at=payload.due_at,
            late_policy=payload.late_policy,
            late_penalty_ratio=payload.late_penalty_ratio,
            status="draft",
        )
        db.add(assignment)
        db.flush()
        _save_assignment_questions(db, assignment.id, resolved)
        db.commit()
        db.refresh(assignment)
        result = _assignment_to_dict(assignment)
        result["question_count"] = len(resolved)
        return result

    # 单题作业旧路径（主观题 AI 批改 / 客观单选判断）
    _validate_assignment_question(payload.question_type, payload.options, payload.correct_answer)
    assignment = TaAssignment(
        ta_user_id=user_id,
        class_id=class_id_uuid,
        course_id=course_id_uuid,
        concept_id=concept_id_uuid,
        title=payload.title,
        description=payload.description,
        question_type=payload.question_type,
        options=payload.options,
        correct_answer=payload.correct_answer,
        total_score=payload.total_score,
        due_at=payload.due_at,
        late_policy=payload.late_policy,
        late_penalty_ratio=payload.late_penalty_ratio,
        status="draft",
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return _assignment_to_dict(assignment)


@router.get("/assignments")
async def list_assignments(
    class_id: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> list[dict[str, Any]]:
    """作业列表，可按班级过滤；多题作业附带题目数。"""
    stmt = select(TaAssignment)
    if class_id:
        class_id_uuid = _require_uuid(class_id, "班级不存在")
        stmt = stmt.where(TaAssignment.class_id == class_id_uuid)
    stmt = stmt.order_by(TaAssignment.created_at.desc())
    stmt = _apply_page(stmt, limit, offset)
    assignments = db.execute(stmt).scalars().all()
    count_map = _assignment_question_count_map(db, [a.id for a in assignments])
    result = [_assignment_to_dict(a) for a in assignments]
    for item in result:
        item["question_count"] = count_map.get(uuid.UUID(item["id"]), 0)
    return result


@router.get("/classes/{class_id}/export/grades.csv")
async def export_class_grades(
    class_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> StreamingResponse:
    """导出班级成绩 CSV：学生 × 作业成绩明细，utf-8-sig 兼容 Excel。"""
    class_id_uuid = _require_uuid(class_id, "班级不存在")
    cls = db.get(TaClass, class_id_uuid)
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    student_ids = _class_student_ids(db, class_id_uuid)
    users = db.execute(select(User).where(User.id.in_(student_ids))).scalars().all() if student_ids else []
    name_by_id = {u.id: (u.display_name or str(u.id)) for u in users}
    assignments = db.execute(
        select(TaAssignment).where(TaAssignment.class_id == class_id_uuid)
    ).scalars().all()
    titles = [a.title for a in assignments]
    records = db.execute(
        select(TaGradingRecord).where(TaGradingRecord.class_id == class_id_uuid)
    ).scalars().all()
    score_map: dict[tuple[str, str], float] = {}
    total_map: dict[tuple[str, str], float] = {}
    for r in records:
        if r.score is not None and r.status == "graded":
            key = (str(r.student_id), r.title)
            score_map[key] = float(r.score)
            total_map[key] = float(r.total_score) if r.total_score else 100.0
    students = [(str(sid), name_by_id.get(sid, "未知")) for sid in student_ids]
    rows = _build_grades_csv_rows(students, titles, score_map, total_map)
    return _csv_response(rows, f"{cls.name}-成绩.csv")


@router.get("/assignments/{assignment_id}")
async def get_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """作业详情（含提交数/已批数统计）。"""
    assignment_id_uuid = _require_uuid(assignment_id, "作业不存在")
    assignment = db.get(TaAssignment, assignment_id_uuid)
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")
    result = _assignment_to_dict(assignment)
    submission_count = db.execute(
        select(TaSubmission).where(TaSubmission.assignment_id == assignment.id)
    ).scalars().all()
    graded = 0
    for s in submission_count:
        if s.grading_record_id:
            grading = db.get(TaGradingRecord, s.grading_record_id)
            if grading and grading.status == "graded":
                graded += 1
    result["submission_count"] = len(submission_count)
    result["graded_count"] = graded
    # 多题作业附带题目快照（含标准答案，TA 出题视角可见）
    if assignment.question_type == "multi":
        questions = db.execute(
            select(TaAssignmentQuestion).where(TaAssignmentQuestion.assignment_id == assignment.id)
            .order_by(TaAssignmentQuestion.order_index)
        ).scalars().all()
        result["questions"] = [
            {
                "id": str(q.id),
                "order_index": q.order_index,
                "question_type": q.question_type,
                "prompt": q.prompt,
                "options": q.options or [],
                "answer": q.answer,
                "score": q.score,
            }
            for q in questions
        ]
    else:
        result["questions"] = []
    return result


@router.put("/assignments/{assignment_id}")
async def update_assignment(
    assignment_id: str,
    payload: AssignmentUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """编辑作业：仅草稿可编辑，其余状态拒绝；多题作业题目整体替换。"""
    assignment_id_uuid = _require_uuid(assignment_id, "作业不存在")
    assignment = db.get(TaAssignment, assignment_id_uuid)
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")
    if assignment.status != "draft":
        raise HTTPException(status_code=403, detail="仅草稿状态可编辑")
    if payload.title is not None:
        assignment.title = payload.title
    if payload.description is not None:
        assignment.description = payload.description
    # 多题作业更新：题目整体替换并重算满分
    if payload.question_ids is not None or payload.questions is not None:
        resolved = _resolve_assignment_questions(db, payload.question_ids, payload.questions)
        _save_assignment_questions(db, assignment.id, resolved)
        assignment.question_type = "multi"
        assignment.options = None
        assignment.correct_answer = None
        assignment.total_score = sum(q.score for q in resolved)
    if payload.question_type is not None:
        assignment.question_type = payload.question_type
    if payload.options is not None:
        assignment.options = payload.options
    if payload.correct_answer is not None:
        assignment.correct_answer = payload.correct_answer
    if payload.question_type is not None or payload.options is not None or payload.correct_answer is not None:
        _validate_assignment_question(
            assignment.question_type or "short_answer",
            assignment.options,
            assignment.correct_answer,
        )
    if payload.total_score is not None:
        assignment.total_score = payload.total_score
    if payload.due_at is not None:
        assignment.due_at = payload.due_at
    if payload.late_policy is not None:
        if payload.late_policy not in _VALID_LATE_POLICIES:
            raise HTTPException(status_code=400, detail="无效的迟交策略")
        assignment.late_policy = payload.late_policy
    if payload.late_penalty_ratio is not None:
        assignment.late_penalty_ratio = payload.late_penalty_ratio
    db.commit()
    db.refresh(assignment)
    return _assignment_to_dict(assignment)


@router.post("/assignments/{assignment_id}/publish")
async def publish_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """发布作业：draft→published，学生端即可见可提交，并给学生生成通知。"""
    assignment_id_uuid = _require_uuid(assignment_id, "作业不存在")
    assignment = db.get(TaAssignment, assignment_id_uuid)
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")
    if assignment.status == "published":
        return _assignment_to_dict(assignment)
    if assignment.status == "closed":
        raise HTTPException(status_code=403, detail="作业已关闭，无法发布")
    assignment.status = "published"
    student_ids = _class_student_ids(db, assignment.class_id)
    _create_notifications(
        db,
        student_ids,
        title=f"新作业：{assignment.title}",
        body=f"《{assignment.title}》已发布，截止时间 "
             + (assignment.due_at.strftime("%Y-%m-%d %H:%M") if assignment.due_at else "待定")
             + "。",
        notification_type="assignment",
        source_type="assignment",
        source_id=str(assignment.id),
        class_id=assignment.class_id,
    )
    db.commit()
    db.refresh(assignment)
    return _assignment_to_dict(assignment)


@router.post("/assignments/{assignment_id}/close")
async def close_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> dict[str, Any]:
    """关闭作业：published→closed，禁止再提交。"""
    assignment_id_uuid = _require_uuid(assignment_id, "作业不存在")
    assignment = db.get(TaAssignment, assignment_id_uuid)
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")
    if assignment.status == "draft":
        raise HTTPException(status_code=403, detail="草稿作业无需关闭")
    if assignment.status == "closed":
        return _assignment_to_dict(assignment)
    assignment.status = "closed"
    db.commit()
    db.refresh(assignment)
    return _assignment_to_dict(assignment)


@router.get("/assignments/{assignment_id}/submissions")
async def list_assignment_submissions(
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ta),
) -> list[dict[str, Any]]:
    """作业提交列表：含学生姓名/得分/is_late/提交次数/批改状态。

    多题作业额外返回结构化作答（answers）与题目快照（questions，含标准答案），
    供教师端逐题对照查看学生答案。
    """
    assignment_id_uuid = _require_uuid(assignment_id, "作业不存在")
    assignment = db.get(TaAssignment, assignment_id_uuid)
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")
    submissions = db.execute(
        select(TaSubmission).where(TaSubmission.assignment_id == assignment.id)
    ).scalars().all()
    student_ids = {s.student_id for s in submissions}
    users = db.execute(select(User).where(User.id.in_(student_ids))).scalars().all() if student_ids else []
    name_by_id = {u.id: (u.display_name or str(u.id)) for u in users}
    # 多题作业附带题目快照（TA 视角含标准答案）
    questions: list[dict[str, Any]] = []
    if assignment.question_type == "multi":
        q_rows = db.execute(
            select(TaAssignmentQuestion).where(TaAssignmentQuestion.assignment_id == assignment.id)
            .order_by(TaAssignmentQuestion.order_index)
        ).scalars().all()
        questions = [
            {
                "id": str(q.id),
                "order_index": q.order_index,
                "question_type": q.question_type,
                "prompt": q.prompt,
                "options": q.options or [],
                "answer": q.answer,
                "score": q.score,
            }
            for q in q_rows
        ]
    result = []
    for s in submissions:
        grading = db.get(TaGradingRecord, s.grading_record_id) if s.grading_record_id else None
        result.append({
            "id": str(s.id),
            "student_id": str(s.student_id),
            "student_name": name_by_id.get(s.student_id, "未知"),
            "answer": s.answer,
            "answers": s.answers,
            "questions": questions,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
            "is_late": s.is_late,
            "attempt_number": s.attempt_number,
            "score": grading.score if grading else None,
            "total_score": grading.total_score if grading else None,
            "status": grading.status if grading else None,
        })
    return result
