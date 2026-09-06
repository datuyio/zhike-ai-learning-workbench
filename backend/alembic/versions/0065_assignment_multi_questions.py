"""作业支持多题（题目快照表）、提交 answers 与客观题自动判分。

1. 新建 ta_assignment_questions：作业题目快照（布置时从题库复制，保证内容稳定）；
2. ta_submissions 增加 answers JSONB（多题作答 {question_id: 作答}，兼容旧单题 answer 文本）；
3. ta_grading_records 增加 objective_score（多题作业中客观题自动判分得分，供 AI 批改主观部分时汇总）；
4. 题库补种多选题与填空题种子，使「单选 / 多选 / 判断 / 填空」四类客观题型都有题可选。

Revision ID: 0065_assignment_multi_questions
Revises: 0064_assignment_question_type
"""
import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0065_assignment_multi_questions"
down_revision = "0064_assignment_question_type"
branch_labels = None
depends_on = None

# 本地测试题库补充题目：多选题 5 道 + 填空题 5 道（与 0062 的单选题/判断题构成四类客观题型）
LOCAL_TEST_QUESTIONS = [
    # (题型, 题干, 选项, 答案, 分值)
    ("multiple_choice", "下列哪些激活函数属于非线性函数？",
     ["A. Sigmoid", "B. ReLU", "C. 恒等函数", "D. Tanh"], "A,B,D", 10),
    ("multiple_choice", "下列哪些措施可以有效缓解过拟合？",
     ["A. 增加训练数据", "B. 使用 Dropout", "C. 增大模型参数", "D. L2 正则化"], "A,B,D", 10),
    ("multiple_choice", "卷积神经网络中常用的池化操作包括？",
     ["A. 最大池化", "B. 平均池化", "C. 全局池化", "D. 注意力池化"], "A,B,C", 10),
    ("multiple_choice", "下列哪些属于梯度下降的变体优化器？",
     ["A. SGD", "B. Momentum", "C. Adam", "D. 最小二乘"], "A,B,C", 10),
    ("multiple_choice", "自然语言处理中常见的词嵌入方法包括？",
     ["A. Word2Vec", "B. GloVe", "C. One-Hot 编码", "D. 注意力机制"], "A,B,C", 10),
    ("blank", "深度学习中最常用的反向传播算法依据的数学法则是____法则。", None, "链式", 5),
    ("blank", "用于缓解梯度消失问题的最常用激活函数是____。", None, "ReLU", 5),
    ("blank", "卷积层中输出特征图每个元素对应的输入区域大小称为____。", None, "感受野", 5),
    ("blank", "Adam 优化器融合了 Momentum 与____两种方法的优点。", None, "RMSProp", 5),
    ("blank", "训练时随机失活部分神经元以防止过拟合的技术称为____。", None, "Dropout", 5),
]


def _stable_uuid(prompt: str) -> str:
    """按题干生成确定性 UUID，保证迁移幂等（ON CONFLICT DO NOTHING）。"""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ta-question-bank:{prompt}"))


def upgrade() -> None:
    """建作业题目快照表、扩展提交/批改字段并补种题库题目。"""
    op.create_table(
        "ta_assignment_questions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", sa.UUID(as_uuid=True), sa.ForeignKey("ta_assignments.id"), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("question_type", sa.String(30), nullable=False, server_default="single_choice"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("answer", sa.String(50), nullable=True, comment="客观题标准答案，主观题为空"),
        sa.Column("score", sa.Float(), nullable=False, server_default="10"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("ta_submissions", sa.Column("answers", sa.JSON(), nullable=True, comment="多题作答 {question_id: 作答}，单题提交为空"))
    op.add_column("ta_grading_records", sa.Column("objective_score", sa.Float(), nullable=True, comment="多题作业中客观题自动判分得分"))

    bind = op.get_bind()
    course_id = bind.execute(
        sa.text("SELECT id FROM courses ORDER BY created_at LIMIT 1")
    ).scalar()
    for question_type, prompt, options, answer, score in LOCAL_TEST_QUESTIONS:
        bind.execute(
            sa.text(
                """
                INSERT INTO ta_question_bank (id, course_id, question_type, prompt, options, answer, score, source, created_at, updated_at)
                VALUES (:id, :course_id, :question_type, :prompt, :options, :answer, :score, 'local_test', NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": _stable_uuid(prompt),
                "course_id": course_id,
                "question_type": question_type,
                "prompt": prompt,
                "options": json.dumps(options, ensure_ascii=False) if options else None,
                "answer": answer,
                "score": score,
            },
        )


def downgrade() -> None:
    """回滚删除新增表与列。"""
    op.drop_column("ta_grading_records", "objective_score")
    op.drop_column("ta_submissions", "answers")
    op.drop_table("ta_assignment_questions")
