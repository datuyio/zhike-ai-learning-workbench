"""持续学习服务包：遗忘风险预测、错误模式识别、AI 反馈闭环、进化日志与画像趋势。

该包是"持续学习与遗忘风险预测"独创亮点的核心实现：系统通过分析学习事件
频率与掌握度变化趋势，主动预测知识遗忘风险并向教师给出干预建议；同时把
教师对 AI 输出的评分反馈、风险模型重算与易错点更新沉淀为可视化进化日志，
形成"数据 → 预测 → 干预 → 反馈 → 进化"的闭环。
"""

from app.services.continual_learning.error_patterns import top_error_patterns
from app.services.continual_learning.evolution_log import list_evolution, record_evolution
from app.services.continual_learning.feedback_loop import (
    calibration_hints,
    feedback_summary,
    record_feedback,
)
from app.services.continual_learning.forgetting_risk import compute_forgetting_risk
from app.services.continual_learning.profile_trends import profile_trend_series

__all__ = [
    "compute_forgetting_risk",
    "top_error_patterns",
    "record_feedback",
    "feedback_summary",
    "calibration_hints",
    "record_evolution",
    "list_evolution",
    "profile_trend_series",
]
