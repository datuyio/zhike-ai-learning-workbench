"""新增本地测试题库表并种入深度学习演示题目。

Revision ID: 0062_ta_question_bank
Revises: 0061_class_invite_code
"""
import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0062_ta_question_bank"
down_revision = "0061_class_invite_code"
branch_labels = None
depends_on = None

# 本地测试题库（深度学习课程演示题）：单选题 10 道 + 判断题 6 道
LOCAL_TEST_QUESTIONS = [
    # (题型, 题干, 选项, 答案, 分值)
    ("single_choice", "反向传播算法中，梯度是通过什么规则逐层传播的？",
     ["A. 加法法则", "B. 链式法则", "C. 乘法交换律", "D. 贝叶斯法则"], "B", 10),
    ("single_choice", "以下哪个激活函数能有效缓解梯度消失问题？",
     ["A. Sigmoid", "B. Tanh", "C. ReLU", "D. Softmax"], "C", 10),
    ("single_choice", "训练集误差很低、验证集误差偏高，最可能的原因是？",
     ["A. 欠拟合", "B. 模型过拟合", "C. 学习率过大", "D. 训练数据过多"], "B", 10),
    ("single_choice", "卷积层中「感受野」指的是？",
     ["A. 输出特征图上每个元素对应的输入区域大小", "B. 卷积核的个数", "C. 池化窗口大小", "D. 全连接层的维度"], "A", 10),
    ("single_choice", "Adam 优化器同时借鉴了哪两种优化方法的优点？",
     ["A. SGD 与 AdaGrad", "B. Momentum 与 RMSProp", "C. 牛顿法与拟牛顿法", "D. 批量梯度下降与在线学习"], "B", 10),
    ("single_choice", "循环神经网络（RNN）最擅长的数据类型是？",
     ["A. 图像", "B. 序列", "C. 点云", "D. 表格"], "B", 10),
    ("single_choice", "Dropout 防止过拟合的机制是？",
     ["A. 降低学习率", "B. 训练时随机失活部分神经元", "C. 增加隐藏层数量", "D. 减少训练数据"], "B", 10),
    ("single_choice", "注意力机制的核心作用是？",
     ["A. 忽略全部输入", "B. 让模型聚焦输入中更重要的部分", "C. 加速反向传播", "D. 替代损失函数"], "B", 10),
    ("single_choice", "数据增强（如随机裁剪、旋转）的主要作用是？",
     ["A. 增加模型参数量", "B. 扩充训练数据多样性、提升泛化能力", "C. 压缩模型体积", "D. 加快推理速度"], "B", 10),
    ("single_choice", "交叉熵损失通常用于哪类任务？",
     ["A. 回归任务", "B. 分类任务", "C. 聚类任务", "D. 降维任务"], "B", 10),
    ("true_false", "ReLU 激活函数在输入为负数时输出为 0。", None, "T", 5),
    ("true_false", "增大 batch size 一定会提高模型准确率。", None, "F", 5),
    ("true_false", "卷积神经网络天然具有平移不变性的归纳偏置。", None, "T", 5),
    ("true_false", "L2 正则化会使权重趋向于更小的值。", None, "T", 5),
    ("true_false", "训练轮数越多，模型泛化能力一定越强。", None, "F", 5),
    ("true_false", "注意力机制最早主要应用于机器翻译领域。", None, "T", 5),
]


def _stable_uuid(prompt: str) -> str:
    """按题干生成确定性 UUID，保证迁移幂等（ON CONFLICT DO NOTHING）。"""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ta-question-bank:{prompt}"))


def upgrade() -> None:
    """建题库表并种入本地测试题库题目（绑定演示课程）。"""
    op.create_table(
        "ta_question_bank",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id", sa.UUID(as_uuid=True), sa.ForeignKey("courses.id"), nullable=True),
        sa.Column("question_type", sa.String(30), nullable=False, server_default="single_choice"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("answer", sa.String(20), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="10"),
        sa.Column("source", sa.String(30), nullable=False, server_default="local_test"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        if_not_exists=True,
    )
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
    """回滚时删除题库表。"""
    op.drop_table("ta_question_bank", if_exists=True)
