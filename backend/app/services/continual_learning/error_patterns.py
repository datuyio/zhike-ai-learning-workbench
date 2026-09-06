"""错误模式识别：自动收集学生常见错误，为教案生成提供历史易错点 TOP3。

数据来源有两路：一是批改记录中得分率低于 60% 的"真实错题"，按知识点
聚合出错次数；二是掌握度低于薄弱阈值的"潜在易错"学生数。两者加权排序
后输出 TOP3，供教案生成 prompt 注入与持续学习中心展示。
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import CourseConcept
from app.models.learning import ConceptMastery
from app.models.ta_class import TaClass
from app.models.ta_class_student import TaClassStudent
from app.models.ta_grading_record import TaGradingRecord

# 得分率低于该值视为一次"出错"样本
_WRONG_RATIO_THRESHOLD = 0.6
# 掌握度低于该值视为潜在易错学生
_WEAK_MASTERY_THRESHOLD = 60


def top_error_patterns(db: Session, class_id: uuid.UUID, top_n: int = 3) -> list[dict[str, Any]]:
    """聚合班级历史易错点并返回 TOP N，按出错强度降序。

    参数:
        db: 数据库会话。
        class_id: 班级内部 UUID。
        top_n: 返回的易错点数量，默认 3。

    返回:
        每项包含 concept_id、concept、wrong_count（低分批改次数）、
        weak_student_count（薄弱学生数）、score（综合强度）、samples
        （典型错题标题）与面向教案的提示文案。
    """
    cls = db.get(TaClass, class_id)
    if cls is None:
        return []
    student_ids = [
        m.student_id
        for m in db.execute(select(TaClassStudent).where(TaClassStudent.class_id == class_id)).scalars()
    ]
    if not student_ids:
        return []

    # 第一路：批改记录中的真实错题（得分率 < 0.6 且已批改）
    record_stmt = select(TaGradingRecord).where(
        TaGradingRecord.class_id == class_id,
        TaGradingRecord.status == "graded",
        TaGradingRecord.concept_id.isnot(None),
    )
    records = db.execute(record_stmt).scalars().all()
    wrong_count: dict[Any, int] = {}
    samples: dict[Any, list[str]] = {}
    for r in records:
        if r.score is None or not r.total_score:
            continue
        if r.score / r.total_score >= _WRONG_RATIO_THRESHOLD:
            continue
        wrong_count[r.concept_id] = wrong_count.get(r.concept_id, 0) + 1
        samples.setdefault(r.concept_id, [])
        if len(samples[r.concept_id]) < 3 and r.title not in samples[r.concept_id]:
            samples[r.concept_id].append(r.title)

    # 第二路：掌握度薄弱学生数（潜在易错人群）
    mastery_stmt = select(ConceptMastery).where(ConceptMastery.user_id.in_(student_ids))
    if cls.course_id:
        mastery_stmt = mastery_stmt.where(ConceptMastery.course_id == cls.course_id)
    weak_count: dict[Any, int] = {}
    for row in db.execute(mastery_stmt).scalars():
        if (row.mastery or 0) < _WEAK_MASTERY_THRESHOLD:
            weak_count[row.concept_id] = weak_count.get(row.concept_id, 0) + 1

    concept_ids = set(wrong_count) | set(weak_count)
    if not concept_ids:
        return []
    titles = {
        c.id: c.title
        for c in db.execute(select(CourseConcept).where(CourseConcept.id.in_(concept_ids))).scalars()
    }

    patterns = []
    for cid in concept_ids:
        wc = wrong_count.get(cid, 0)
        wsc = weak_count.get(cid, 0)
        if wc == 0 and wsc == 0:
            continue
        # 综合强度：真实错题权重更高，薄弱人数作为潜在风险补充
        score = wc * 2 + wsc
        patterns.append({
            "concept_id": str(cid),
            "concept": titles.get(cid, "未知知识点"),
            "wrong_count": wc,
            "weak_student_count": wsc,
            "score": score,
            "samples": samples.get(cid, []),
            "tip": f"历史数据显示「{titles.get(cid, '该知识点')}」为学生高频出错点，教案中应设计针对性讲解与变式练习。",
        })
    patterns.sort(key=lambda item: item["score"], reverse=True)
    return patterns[:top_n]
