"""教师端 AI 教学助手工具集（function calling）。

工具契约：
- ``name`` / ``description`` / ``parameters``(JSON Schema)：供 LLM function calling 使用。
- ``scope``：``read``（只读，可直接执行）或 ``write``（写操作，需教师确认）。
- ``execute(ctx, args)``：真正执行工具并返回可序列化结果。
- ``summarize(data)``：把执行结果压缩为供 LLM 观察的一句话摘要。

写操作在 Agent 循环中会返回 ``need_confirmation=True`` 暂停执行，由确认端点放行；
本模块只负责"执行"，不放行护栏在确认端点（scope 为 write 的工具不在循环内直接执行）。
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Course, User
from app.models.ta_announcement import TaAnnouncement
from app.models.ta_assignment import TaAssignment, TaAssignmentQuestion
from app.models.ta_class import TaClass
from app.models.ta_class_student import TaClassStudent
from app.models.ta_quiz import TaQuiz
from app.models.ta_question_bank import TaQuestionBank
from app.services.knowledge.local_knowledge import LocalKnowledgeService

# 单题作业/测验题型枚举（与 ta 路由口径一致）
_OBJECTIVE_QUESTION_TYPES = {"single_choice", "multiple_choice", "true_false", "blank"}
_ALL_QUESTION_TYPES = _OBJECTIVE_QUESTION_TYPES | {"short_answer", "code"}


def _safe_uuid(value: Any) -> uuid.UUID | None:
    """把字符串/对象解析为 UUID，非法输入返回 None。"""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _teacher_user(db: Session, user_external_id: str) -> User | None:
    """按 external_id 解析教师账号。"""
    return db.execute(select(User).where(User.external_id == user_external_id)).scalar_one_or_none()


def _owned_class_ids(db: Session, user: User) -> list[uuid.UUID]:
    """返回当前教师名下全部班级 id（仅活动班级）。"""
    classes = db.execute(
        select(TaClass).where(TaClass.ta_user_id == user.id, TaClass.is_active.is_(True))
    ).scalars().all()
    return [c.id for c in classes]


def _class_name(db: Session, class_id: uuid.UUID) -> str:
    """按班级 id 取班级名。"""
    cls = db.get(TaClass, class_id)
    return cls.name if cls else "未知班级"


class TaToolContext:
    """工具执行上下文：由路由注入，限定当前教师数据范围。"""

    def __init__(self, db: Session, user_external_id: str, user_internal_id: uuid.UUID):
        self.db = db
        self.user_external_id = user_external_id
        self.user_internal_id = user_internal_id


ToolExecutor = Callable[[TaToolContext, dict[str, Any]], dict[str, Any]]


class TaTool:
    """教师端工具定义。"""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        scope: str,
        execute: ToolExecutor,
        summarize: Callable[[dict[str, Any]], str],
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.scope = scope
        self._execute = execute
        self._summarize = summarize

    def execute(self, ctx: TaToolContext, args: dict[str, Any]) -> dict[str, Any]:
        """执行工具并返回结果；执行器抛出的 ValueError 转为 error 结果。"""
        try:
            return self._execute(ctx, args)
        except ValueError as exc:
            return {"error": str(exc)}

    def summarize(self, data: dict[str, Any]) -> str:
        """把结果压缩为 LLM 可观察的一句话摘要。"""
        return self._summarize(data)

    def to_openai(self) -> dict[str, Any]:
        """转换为 OpenAI function calling 工具定义。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ── 只读工具执行器 ──────────────────────────────────────────────────────────


def _list_classes(ctx: TaToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    classes = ctx.db.execute(
        select(TaClass).where(TaClass.ta_user_id == ctx.user_internal_id, TaClass.is_active.is_(True))
    ).scalars().all()
    rows = []
    for cls in classes:
        count = ctx.db.execute(
            select(func.count()).select_from(TaClassStudent).where(TaClassStudent.class_id == cls.id)
        ).scalar() or 0
        rows.append({
            "id": str(cls.id),
            "name": cls.name,
            "student_count": count,
            "course_id": str(cls.course_id) if cls.course_id else None,
            "invite_code": cls.invite_code,
        })
    return {"classes": rows, "total": len(rows)}


def _list_class_students(ctx: TaToolContext, args: dict[str, Any]) -> dict[str, Any]:
    class_id = _safe_uuid(args.get("class_id"))
    if class_id is None:
        raise ValueError("class_id 必填且为合法 UUID")
    cls = ctx.db.get(TaClass, class_id)
    if not cls or cls.ta_user_id != ctx.user_internal_id:
        raise ValueError("班级不存在或无权访问")
    members = ctx.db.execute(
        select(User, TaClassStudent).join(TaClassStudent, TaClassStudent.student_id == User.id)
        .where(TaClassStudent.class_id == class_id)
    ).all()
    rows = [{"id": str(u.id), "name": u.display_name, "email": u.email} for u, _m in members]
    return {"students": rows, "total": len(rows), "class_name": cls.name}


def _list_assignments(ctx: TaToolContext, args: dict[str, Any]) -> dict[str, Any]:
    stmt = select(TaAssignment).where(TaAssignment.ta_user_id == ctx.user_internal_id)
    class_id = _safe_uuid(args.get("class_id"))
    if class_id is not None:
        stmt = stmt.where(TaAssignment.class_id == class_id)
    assignments = ctx.db.execute(stmt.order_by(TaAssignment.created_at.desc()).limit(20)).scalars().all()
    rows = [
        {
            "id": str(a.id),
            "title": a.title,
            "class_id": str(a.class_id),
            "class_name": _class_name(ctx.db, a.class_id),
            "status": a.status,
            "total_score": a.total_score,
            "due_at": a.due_at.isoformat() if a.due_at else None,
        }
        for a in assignments
    ]
    return {"assignments": rows, "total": len(rows)}


def _query_question_bank(ctx: TaToolContext, args: dict[str, Any]) -> dict[str, Any]:
    stmt = select(TaQuestionBank)
    course_id = _safe_uuid(args.get("course_id"))
    if course_id is not None:
        stmt = stmt.where(TaQuestionBank.course_id == course_id)
    if args.get("question_type") in _ALL_QUESTION_TYPES:
        stmt = stmt.where(TaQuestionBank.question_type == args["question_type"])
    keyword = (args.get("keyword") or "").strip()
    if keyword:
        stmt = stmt.where(TaQuestionBank.prompt.ilike(f"%{keyword}%"))
    limit = min(int(args.get("limit") or 10), 30)
    rows = ctx.db.execute(stmt.order_by(TaQuestionBank.created_at.desc()).limit(limit)).scalars().all()
    return {
        "questions": [
            {
                "id": str(q.id),
                "question_type": q.question_type,
                "prompt": q.prompt,
                "options": q.options or [],
                "answer": q.answer,
                "score": q.score,
            }
            for q in rows
        ],
        "total": len(rows),
    }


def _list_quizzes(ctx: TaToolContext, args: dict[str, Any]) -> dict[str, Any]:
    stmt = select(TaQuiz).where(TaQuiz.ta_user_id == ctx.user_internal_id)
    class_id = _safe_uuid(args.get("class_id"))
    if class_id is not None:
        stmt = stmt.where(TaQuiz.class_id == class_id)
    quizzes = ctx.db.execute(stmt.order_by(TaQuiz.created_at.desc()).limit(20)).scalars().all()
    return {
        "quizzes": [
            {"id": str(q.id), "title": q.title, "class_id": str(q.class_id), "status": q.status}
            for q in quizzes
        ],
        "total": len(quizzes),
    }


def _list_courses(ctx: TaToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    courses = ctx.db.execute(select(Course).where(Course.status == "published").order_by(Course.slug)).scalars().all()
    return {
        "courses": [
            {"slug": c.slug, "title": c.title}
            for c in courses
        ],
        "total": len(courses),
    }


def _search_knowledge_base(ctx: TaToolContext, args: dict[str, Any]) -> dict[str, Any]:
    question = (args.get("question") or "").strip()
    course_slug = (args.get("course_slug") or "").strip()
    if not question:
        raise ValueError("question 必填")
    if not course_slug:
        raise ValueError("course_slug 必填（可先调用 list_courses 获取课程 slug）")
    service = LocalKnowledgeService(ctx.db)
    try:
        citations = service.search(course_slug, question, limit=3)
    except Exception as exc:  # noqa: BLE001 - 课程无切片等情况返回空结果
        return {"answer": "", "citations": [], "note": f"检索失败：{exc}"}
    snippets = [{"title": c.source_title, "content": (c.content or "")[:300]} for c in citations]
    return {"answer": "", "citations": snippets, "count": len(snippets)}


# ── 写操作执行器（需确认，由确认端点放行） ──────────────────────────────────


def _create_assignment(ctx: TaToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """创建作业草稿（不发布，发布走 publish 工具或教师手动发布）。"""
    from app.models.ta_assignment import TaAssignment as _TaAssignment
    from app.models.ta_assignment import TaAssignmentQuestion as _TaAssignmentQuestion

    class_id = _safe_uuid(args.get("class_id"))
    if class_id is None:
        raise ValueError("class_id 必填且为合法 UUID")
    cls = ctx.db.get(TaClass, class_id)
    if not cls or cls.ta_user_id != ctx.user_internal_id:
        raise ValueError("班级不存在或无权访问")
    title = (args.get("title") or "").strip()
    if not title:
        raise ValueError("title 必填")

    question_ids = args.get("question_ids") or []
    manual_questions = args.get("questions") or []
    if question_ids:
        id_uuids = [_safe_uuid(qid) for qid in question_ids]
        bank = ctx.db.execute(select(TaQuestionBank).where(TaQuestionBank.id.in_(id_uuids))).scalars().all()
        found = {str(q.id): q for q in bank}
        missing = [qid for qid in question_ids if qid not in found]
        if missing:
            raise ValueError(f"题库中不存在以下题目: {', '.join(missing[:5])}")
    else:
        found = {}
    if not question_ids and not manual_questions:
        raise ValueError("请至少提供 question_ids（题库选题）或 questions（手动出题）")

    course_id = _safe_uuid(args.get("course_id"))
    due_at = args.get("due_at")
    assignment = _TaAssignment(
        ta_user_id=ctx.user_internal_id,
        class_id=class_id,
        course_id=course_id,
        title=title,
        description=(args.get("description") or "").strip() or None,
        question_type="multi" if (question_ids or manual_questions) else "short_answer",
        total_score=100,
        due_at=None,
        late_policy="allow_penalty",
        late_penalty_ratio=0.1,
        status="draft",
    )
    ctx.db.add(assignment)
    ctx.db.flush()
    order = 0
    total_score = 0.0
    for qid in question_ids:
        q = found.get(qid)
        if q is None:
            continue
        ctx.db.add(_TaAssignmentQuestion(
            assignment_id=assignment.id, order_index=order, question_type=q.question_type,
            prompt=q.prompt, options=q.options, answer=q.answer, score=q.score,
        ))
        total_score += q.score
        order += 1
    for mq in manual_questions:
        qtype = mq.get("question_type") or "short_answer"
        if qtype not in _ALL_QUESTION_TYPES:
            raise ValueError(f"不支持的题型: {qtype}")
        ctx.db.add(_TaAssignmentQuestion(
            assignment_id=assignment.id, order_index=order, question_type=qtype,
            prompt=(mq.get("prompt") or "").strip(), options=mq.get("options"),
            answer=mq.get("answer"), score=float(mq.get("score") or 10),
        ))
        total_score += float(mq.get("score") or 10)
        order += 1
    assignment.total_score = total_score or 100
    ctx.db.commit()
    return {
        "assignment_id": str(assignment.id),
        "title": title,
        "class_name": cls.name,
        "question_count": order,
        "total_score": assignment.total_score,
        "status": "draft",
    }


def _publish_assignment(ctx: TaToolContext, args: dict[str, Any]) -> dict[str, Any]:
    assignment_id = _safe_uuid(args.get("assignment_id"))
    if assignment_id is None:
        raise ValueError("assignment_id 必填且为合法 UUID")
    assignment = ctx.db.get(TaAssignment, assignment_id)
    if not assignment or assignment.ta_user_id != ctx.user_internal_id:
        raise ValueError("作业不存在或无权访问")
    assignment.status = "published"
    ctx.db.commit()
    return {"assignment_id": str(assignment.id), "title": assignment.title, "status": "published"}


def _create_quiz(ctx: TaToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.models.ta_quiz import TaQuiz as _TaQuiz
    from app.models.ta_quiz import TaQuizQuestion as _TaQuizQuestion

    class_id = _safe_uuid(args.get("class_id"))
    if class_id is None:
        raise ValueError("class_id 必填且为合法 UUID")
    cls = ctx.db.get(TaClass, class_id)
    if not cls or cls.ta_user_id != ctx.user_internal_id:
        raise ValueError("班级不存在或无权访问")
    title = (args.get("title") or "").strip()
    if not title:
        raise ValueError("title 必填")

    question_ids = args.get("question_ids") or []
    manual_questions = args.get("questions") or []
    if question_ids:
        id_uuids = [_safe_uuid(qid) for qid in question_ids]
        bank = ctx.db.execute(select(TaQuestionBank).where(TaQuestionBank.id.in_(id_uuids))).scalars().all()
        found = {str(q.id): q for q in bank}
        missing = [qid for qid in question_ids if qid not in found]
        if missing:
            raise ValueError(f"题库中不存在以下题目: {', '.join(missing[:5])}")
    else:
        found = {}
    if not question_ids and not manual_questions:
        raise ValueError("请至少提供 question_ids 或 questions")

    quiz = _TaQuiz(
        ta_user_id=ctx.user_internal_id,
        class_id=class_id,
        course_id=_safe_uuid(args.get("course_id")),
        title=title,
        description=(args.get("description") or "").strip() or None,
    )
    ctx.db.add(quiz)
    ctx.db.flush()
    order = 0
    for qid in question_ids:
        q = found.get(qid)
        if q is None:
            continue
        ctx.db.add(_TaQuizQuestion(
            quiz_id=quiz.id, order_index=order, question_type=q.question_type,
            prompt=q.prompt, options=q.options, answer=q.answer, score=q.score,
        ))
        order += 1
    for mq in manual_questions:
        qtype = mq.get("question_type") or "single_choice"
        if qtype not in _OBJECTIVE_QUESTION_TYPES:
            raise ValueError(f"测验不支持题型: {qtype}")
        ctx.db.add(_TaQuizQuestion(
            quiz_id=quiz.id, order_index=order, question_type=qtype,
            prompt=(mq.get("prompt") or "").strip(), options=mq.get("options"),
            answer=mq.get("answer"), score=float(mq.get("score") or 10),
        ))
        order += 1
    ctx.db.commit()
    return {"quiz_id": str(quiz.id), "title": title, "class_name": cls.name, "question_count": order}


def _create_announcement(ctx: TaToolContext, args: dict[str, Any]) -> dict[str, Any]:
    title = (args.get("title") or "").strip()
    body = (args.get("body") or "").strip()
    if not title or not body:
        raise ValueError("title 和 body 必填")
    class_ids = args.get("class_ids") or []
    targets: list[uuid.UUID | None] = []
    if class_ids:
        for cid in class_ids:
            cu = _safe_uuid(cid)
            if cu is None:
                raise ValueError(f"班级 id 非法: {cid}")
            cls = ctx.db.get(TaClass, cu)
            if not cls or cls.ta_user_id != ctx.user_internal_id:
                raise ValueError(f"班级不存在或无权访问: {cid}")
            targets.append(cu)
    else:
        targets = [None]
    created = []
    for cu in targets:
        announcement = TaAnnouncement(
            title=title, body=body, announcement_type="general",
            class_id=cu, created_by=ctx.user_internal_id,
        )
        ctx.db.add(announcement)
        ctx.db.flush()
        created.append(str(announcement.id))
    ctx.db.commit()
    return {"announcement_ids": created, "title": title, "target_count": len(targets)}


# ── 工具注册表 ──────────────────────────────────────────────────────────────


def _summary_classes(data: dict[str, Any]) -> str:
    if data.get("error"):
        return data["error"]
    return f"共 {data['total']} 个班级"


def _summary_students(data: dict[str, Any]) -> str:
    if data.get("error"):
        return data["error"]
    return f"班级「{data.get('class_name', '')}」共 {data['total']} 名学生"


def _summary_assignments(data: dict[str, Any]) -> str:
    if data.get("error"):
        return data["error"]
    return f"共 {data['total']} 份作业"


def _summary_question_bank(data: dict[str, Any]) -> str:
    if data.get("error"):
        return data["error"]
    return f"检索到 {data['total']} 道题"


def _summary_quizzes(data: dict[str, Any]) -> str:
    if data.get("error"):
        return data["error"]
    return f"共 {data['total']} 场测验"


def _summary_courses(data: dict[str, Any]) -> str:
    if data.get("error"):
        return data["error"]
    return f"共 {data['total']} 门课程"


def _summary_knowledge(data: dict[str, Any]) -> str:
    if data.get("error"):
        return data["error"]
    return f"知识库检索到 {data.get('count', 0)} 条引用"


def _summary_created_assignment(data: dict[str, Any]) -> str:
    if data.get("error"):
        return data["error"]
    return f"已创建作业《{data['title']}》到 {data['class_name']}（{data['question_count']} 题，共 {data['total_score']} 分）"


def _summary_publish_assignment(data: dict[str, Any]) -> str:
    if data.get("error"):
        return data["error"]
    return f"已发布作业《{data['title']}》"


def _summary_created_quiz(data: dict[str, Any]) -> str:
    if data.get("error"):
        return data["error"]
    return f"已创建测验《{data['title']}》到 {data['class_name']}（{data['question_count']} 题）"


def _summary_created_announcement(data: dict[str, Any]) -> str:
    if data.get("error"):
        return data["error"]
    return f"已发布公告《{data['title']}》（{data['target_count']} 个目标）"


TA_TOOLS: list[TaTool] = [
    TaTool(
        name="list_classes",
        description="列出当前教师的所有班级（id、名称、学生数、邀请码）。教师提到班级、学生、作业、测验时，先调用本工具获取班级 id。",
        parameters={"type": "object", "properties": {}, "required": []},
        scope="read",
        execute=_list_classes,
        summarize=_summary_classes,
    ),
    TaTool(
        name="list_class_students",
        description="查询某班级学生列表（id、姓名、邮箱）。参数 class_id 来自 list_classes。",
        parameters={"type": "object", "properties": {"class_id": {"type": "string", "description": "班级 id"}}, "required": ["class_id"]},
        scope="read",
        execute=_list_class_students,
        summarize=_summary_students,
    ),
    TaTool(
        name="list_assignments",
        description="列出作业（可按班级过滤，class_id 来自 list_classes）。含标题、状态、满分、截止时间。",
        parameters={"type": "object", "properties": {"class_id": {"type": "string", "description": "可选：班级 id"}}, "required": []},
        scope="read",
        execute=_list_assignments,
        summarize=_summary_assignments,
    ),
    TaTool(
        name="query_question_bank",
        description="从本地题库检索题目。question_type=single_choice/multiple_choice/true_false/blank/short_answer/code；keyword=题干关键词；返回题目含标准答案（供教师审核）。",
        parameters={
            "type": "object",
            "properties": {
                "course_id": {"type": "string", "description": "可选：课程 UUID"},
                "question_type": {"type": "string", "description": "题型"},
                "keyword": {"type": "string", "description": "题干关键词"},
                "limit": {"type": "integer", "description": "返回条数（默认 10，上限 30）"},
            },
            "required": [],
        },
        scope="read",
        execute=_query_question_bank,
        summarize=_summary_question_bank,
    ),
    TaTool(
        name="list_quizzes",
        description="列出测验（可按班级过滤）。含标题、状态。",
        parameters={"type": "object", "properties": {"class_id": {"type": "string", "description": "可选：班级 id"}}, "required": []},
        scope="read",
        execute=_list_quizzes,
        summarize=_summary_quizzes,
    ),
    TaTool(
        name="list_courses",
        description="列出已发布课程（slug、标题）。教师提到具体课程、知识库检索时，先调用本工具获取课程 slug。",
        parameters={"type": "object", "properties": {}, "required": []},
        scope="read",
        execute=_list_courses,
        summarize=_summary_courses,
    ),
    TaTool(
        name="search_knowledge_base",
        description="检索本地课程知识库（零幻觉 RAG）。question=教师问题；course_slug=课程 slug（来自 list_courses）。返回引用片段。",
        parameters={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "教师问题"},
                "course_slug": {"type": "string", "description": "课程 slug（来自 list_courses）"},
            },
            "required": ["question", "course_slug"],
        },
        scope="read",
        execute=_search_knowledge_base,
        summarize=_summary_knowledge,
    ),
    TaTool(
        name="create_assignment",
        description="布置作业（创建草稿，需教师确认后执行）。class_id 来自 list_classes；question_ids 来自 query_question_bank 的题目 id；也可用 questions 手动出题（含 prompt/question_type/options/answer/score）。title 必填。",
        parameters={
            "type": "object",
            "properties": {
                "class_id": {"type": "string", "description": "班级 id（来自 list_classes）"},
                "title": {"type": "string", "description": "作业标题"},
                "description": {"type": "string", "description": "可选：作业说明"},
                "course_id": {"type": "string", "description": "可选：课程 UUID"},
                "question_ids": {"type": "array", "items": {"type": "string"}, "description": "题库题目 id 列表"},
                "questions": {"type": "array", "items": {"type": "object"}, "description": "手动出题列表"},
                "due_at": {"type": "string", "description": "可选：截止时间 ISO 字符串"},
            },
            "required": ["class_id", "title"],
        },
        scope="write",
        execute=_create_assignment,
        summarize=_summary_created_assignment,
    ),
    TaTool(
        name="publish_assignment",
        description="发布作业（需教师确认）。assignment_id 来自 list_assignments。",
        parameters={"type": "object", "properties": {"assignment_id": {"type": "string"}}, "required": ["assignment_id"]},
        scope="write",
        execute=_publish_assignment,
        summarize=_summary_publish_assignment,
    ),
    TaTool(
        name="create_quiz",
        description="创建随堂测验（需教师确认）。class_id 来自 list_classes；question_ids 来自 query_question_bank；或 questions 手动出题。title 必填。",
        parameters={
            "type": "object",
            "properties": {
                "class_id": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "course_id": {"type": "string"},
                "question_ids": {"type": "array", "items": {"type": "string"}},
                "questions": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["class_id", "title"],
        },
        scope="write",
        execute=_create_quiz,
        summarize=_summary_created_quiz,
    ),
    TaTool(
        name="create_announcement",
        description="发布公告（需教师确认）。title/body 必填；class_ids 可选（多班定向，来自 list_classes），不填则面向全体学生。",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "class_ids": {"type": "array", "items": {"type": "string"}, "description": "可选：目标班级 id 列表"},
            },
            "required": ["title", "body"],
        },
        scope="write",
        execute=_create_announcement,
        summarize=_summary_created_announcement,
    ),
]

_TOOLS_BY_NAME = {tool.name: tool for tool in TA_TOOLS}


def tool_definitions() -> list[dict[str, Any]]:
    """返回全部工具的 OpenAI function calling 定义。"""
    return [tool.to_openai() for tool in TA_TOOLS]


def get_tool(name: str) -> TaTool | None:
    """按名称取工具。"""
    return _TOOLS_BY_NAME.get(name)
