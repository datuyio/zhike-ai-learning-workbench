"""给演示批改记录补作业分数（雷达图 homework 维度数据）

Revision ID: 0056_seed_ta_homework_scores
Revises: 0055_ta_portal_p1
Create Date: 2026-08-06 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0056_seed_ta_homework_scores"
down_revision = "0055_ta_portal_p1"
branch_labels = None
depends_on = None

# 待补分的记录：按固定 student_id + title 定位（title 供核对）；student_id 来自 0046 种子
_HOMEWORK_SCORES = [
    ("a0000000-0000-4000-8000-000000000101", "第三章作业：反向传播推导", 85),
    ("a0000000-0000-4000-8000-000000000103", "注意力机制计算题", 92),
    ("a0000000-0000-4000-8000-000000000105", "训练集划分实践", 78),
]


def upgrade() -> None:
    """把 3 条仍为 pending 的批改记录置为 graded 并填分（幂等：不覆盖已有分数）。"""
    bind = op.get_bind()
    for student_id, title, score in _HOMEWORK_SCORES:
        bind.execute(
            sa.text(
                """
                UPDATE ta_grading_records
                SET status = 'graded',
                    score = :score,
                    grader_type = 'ai_assisted',
                    ai_comment = '作业质量评分（演示种子数据）',
                    feedback = '{"issues": [], "source": "seed"}'::jsonb,
                    updated_at = NOW()
                WHERE student_id = :student_id
                  AND title = :title
                  AND status = 'pending'
                """
            ),
            {"student_id": student_id, "title": title, "score": score},
        )


def downgrade() -> None:
    """回滚：把本迁移置为 graded 的记录还原为 pending。"""
    bind = op.get_bind()
    for student_id, title, _ in _HOMEWORK_SCORES:
        bind.execute(
            sa.text(
                """
                UPDATE ta_grading_records
                SET status = 'pending',
                    score = NULL,
                    grader_type = 'ai_assisted',
                    ai_comment = NULL,
                    feedback = NULL,
                    updated_at = NOW()
                WHERE student_id = :student_id AND title = :title
                """
            ),
            {"student_id": student_id, "title": title},
        )
