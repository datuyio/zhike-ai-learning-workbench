"""助教端演示种子数据

Revision ID: 0054_seed_ta_demo_data
Revises: 0053_ta_portal_integration
Create Date: 2026-08-05 00:00:00
"""
from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from argon2 import PasswordHasher

_password_hasher = PasswordHasher()

revision = "0054_seed_ta_demo_data"
down_revision = "0053_ta_portal_integration"
branch_labels = None
depends_on = None

# 固定 UUID 段落可重复执行；批改/事件等随机 UUID 数据段落在重复执行时会叠加
TA_USER_ID = "a0000000-0000-4000-8000-000000000001"
STUDENT_IDS = [
    "a0000000-0000-4000-8000-000000000101",
    "a0000000-0000-4000-8000-000000000102",
    "a0000000-0000-4000-8000-000000000103",
    "a0000000-0000-4000-8000-000000000104",
    "a0000000-0000-4000-8000-000000000105",
    "a0000000-0000-4000-8000-000000000106",
]
CLASS_IDS = [
    "b0000000-0000-4000-8000-000000000001",
    "b0000000-0000-4000-8000-000000000002",
]
ALERT_IDS = [
    "c0000000-0000-4000-8000-000000000001",
    "c0000000-0000-4000-8000-000000000002",
    "c0000000-0000-4000-8000-000000000003",
    "c0000000-0000-4000-8000-000000000004",
]


def _hash_password(password: str) -> str:
    """使用 Argon2id 生成演示账号密码哈希。"""
    return _password_hasher.hash(password)


def upgrade() -> None:
    """插入助教端演示数据：助教账号、学生、班级、批改记录、预警、学习事件与掌握度。

    课程/知识点从已有真实数据中选取（子查询），保证外键完整。
    """
    bind = op.get_bind()
    password = os.getenv("SEED_TA_PASSWORD") or "ta123456"
    execute = lambda sql, **params: bind.execute(sa.text(sql), params)

    # 1) 助教账号（role_code='ta' 满足 require_ta 校验）
    execute(
        """
        INSERT INTO users (id, external_id, display_name, email, role_code, status, password_hash, created_at, updated_at)
        VALUES (:id, 'ta-demo', '助教小智', 'ta@example.edu.cn', 'ta', 'active', :password_hash, NOW(), NOW())
        ON CONFLICT (id) DO NOTHING
        """,
        id=TA_USER_ID,
        password_hash=_hash_password(password),
    )
    # 2) 学生账号
    student_names = ["李华", "王明", "张伟", "刘洋", "陈静", "赵磊"]
    for index, (student_id, name) in enumerate(zip(STUDENT_IDS, student_names, strict=True)):
        execute(
            """
            INSERT INTO users (id, external_id, display_name, email, role_code, status, created_at, updated_at)
            VALUES (:id, :external_id, :name, :email, 'student', 'active', NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
            """,
            id=student_id,
            external_id=f"ta-demo-student-{index + 1}",
            name=name,
            email=f"student{index + 1}@example.edu.cn",
        )
    # 3) 班级（course_id 取演示环境已有课程）
    course_id = bind.execute(sa.text("SELECT id FROM courses ORDER BY created_at LIMIT 1")).scalar()
    for index, class_id in enumerate(CLASS_IDS):
        execute(
            """
            INSERT INTO ta_classes (id, name, description, course_id, ta_user_id, is_active, created_at, updated_at)
            VALUES (:id, :name, :description, :course_id, :ta_user_id, true, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
            """,
            id=class_id,
            name=f"深度学习 0{index + 1} 班",
            description="助教端演示班级",
            course_id=course_id,
            ta_user_id=TA_USER_ID,
        )
    # 4) 班级-学生关系（前 3 名进 1 班，后 3 名进 2 班）
    for index, student_id in enumerate(STUDENT_IDS):
        execute(
            """
            INSERT INTO ta_class_students (id, class_id, student_id, joined_at)
            VALUES (gen_random_uuid(), :class_id, :student_id, NOW() - INTERVAL '20 days')
            ON CONFLICT DO NOTHING
            """,
            class_id=CLASS_IDS[index // 3],
            student_id=student_id,
        )
    # 5) 批改记录（6 条 pending，含学生提交内容）
    pending_titles = ["第三章作业：反向传播推导", "卷积网络结构简答题", "注意力机制计算题", "梯度消失问题分析", "训练集划分实践", "模型评估指标简答"]
    for index, (student_id, title) in enumerate(zip(STUDENT_IDS, pending_titles, strict=True)):
        execute(
            """
            INSERT INTO ta_grading_records (id, title, student_id, course_id, class_id, grader_type, question_type, total_score, student_answer, status, created_at, updated_at)
            VALUES (gen_random_uuid(), :title, :student_id, :course_id, :class_id, 'ai_assisted', 'short_answer', 100, :answer, 'pending', NOW() - INTERVAL '2 days', NOW() - INTERVAL '2 days')
            """,
            title=title,
            student_id=student_id,
            course_id=course_id,
            class_id=CLASS_IDS[index // 3],
            answer=f"学生对「{title}」的作答：结合课堂内容梳理了核心概念，给出了推导过程与示例，部分细节尚待完善。",
        )
    # 6) 预警记录（3 条未处理 + 1 条已处理，覆盖高中低严重度）
    alert_rows = [
        ("c0000000-0000-4000-8000-000000000001", STUDENT_IDS[5], CLASS_IDS[1], "inactive", "high", "学生长期未学习：近 10 天无学习事件"),
        ("c0000000-0000-4000-8000-000000000002", STUDENT_IDS[1], CLASS_IDS[0], "score_drop", "medium", "近期测评得分连续下降"),
        ("c0000000-0000-4000-8000-000000000003", STUDENT_IDS[2], CLASS_IDS[0], "mastery_gap", "low", "知识点掌握度低于 60"),
        ("c0000000-0000-4000-8000-000000000004", STUDENT_IDS[4], CLASS_IDS[1], "score_drop", "medium", "作业提交质量波动（已处理）"),
    ]
    for alert_id, student_id, class_id, alert_type, severity, title in alert_rows:
        resolved = alert_id == ALERT_IDS[3]
        execute(
            """
            INSERT INTO ta_alert_records (id, student_id, class_id, course_id, alert_type, severity, title, description, resolved, resolved_at, created_at)
            VALUES (:id, :student_id, :class_id, :course_id, :alert_type, :severity, :title, :description, :resolved, CASE WHEN :resolved THEN NOW() END, NOW() - INTERVAL '3 days')
            ON CONFLICT (id) DO NOTHING
            """,
            id=alert_id,
            student_id=student_id,
            class_id=class_id,
            course_id=course_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=title,
            resolved=resolved,
        )
    # 7) 学习事件（近 14 天分布，供活跃度趋势与个体画像使用）
    # 注：诊断接口（progress/activity-trend/学生画像）查询 learning_events 表，故种子插入该表而非已弃用的 student_learning_events
    event_types = ["chat", "quiz", "resource_view", "lesson_complete", "code_run"]
    for day_offset in range(14):
        for student_id in STUDENT_IDS:
            # 学生 6 与"近 10 天无学习事件"预警保持一致：最近 10 天不播事件
            if student_id == STUDENT_IDS[5] and day_offset < 10:
                continue
            execute(
                """
                INSERT INTO learning_events (id, course_id, user_id, event_type, evidence_json, created_at, updated_at)
                VALUES (gen_random_uuid(), :course_id, :user_id, :event_type, '{}'::jsonb, NOW() - (:day_offset * INTERVAL '1 day') - (:hour * INTERVAL '1 hour'), NOW() - (:day_offset * INTERVAL '1 day') - (:hour * INTERVAL '1 hour'))
                """,
                course_id=course_id,
                user_id=student_id,
                event_type=event_types[day_offset % len(event_types)],
                day_offset=day_offset,
                hour=day_offset % 8 + 9,
            )
    # 8) 概念掌握度（供 weak-points / progress / 学生画像聚合）
    concepts = bind.execute(sa.text("SELECT id FROM course_concepts ORDER BY recommended_order LIMIT 8")).scalars().all()
    for student_index, student_id in enumerate(STUDENT_IDS):
        for concept_index, concept_id in enumerate(concepts):
            mastery = max(20, 95 - (student_index * 7) - (concept_index * 5) % 40)
            execute(
                """
                INSERT INTO concept_mastery (id, course_id, user_id, concept_id, mastery, status, evidence_json)
                VALUES (gen_random_uuid(), :course_id, :user_id, :concept_id, :mastery, 'active', '[]'::jsonb)
                ON CONFLICT (course_id, user_id, concept_id) DO UPDATE SET mastery = EXCLUDED.mastery
                """,
                course_id=course_id,
                user_id=student_id,
                concept_id=concept_id,
                mastery=mastery,
            )


def downgrade() -> None:
    """回滚：删除种子用户与助教端演示数据。"""
    bind = op.get_bind()
    student_ids = tuple(STUDENT_IDS)
    class_ids = tuple(CLASS_IDS)
    alert_ids = tuple(ALERT_IDS)
    user_ids = tuple([TA_USER_ID, *STUDENT_IDS])

    # IN 列表参数需显式 expanding，text() 不会自动展开元组
    def delete(sql: str, ids: tuple) -> None:
        bind.execute(
            sa.text(sql).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": ids},
        )

    delete("DELETE FROM learning_events WHERE user_id IN :ids", student_ids)
    delete("DELETE FROM ta_grading_records WHERE student_id IN :ids", student_ids)
    delete("DELETE FROM ta_alert_records WHERE id IN :ids", alert_ids)
    delete("DELETE FROM ta_class_students WHERE class_id IN :ids", class_ids)
    delete("DELETE FROM ta_classes WHERE id IN :ids", class_ids)
    delete("DELETE FROM concept_mastery WHERE user_id IN :ids", student_ids)
    delete("DELETE FROM users WHERE id IN :ids", user_ids)
