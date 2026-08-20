from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ReportDimensionScore(BaseModel):
    """评估报告中的单个维度评分项。"""

    key: str = Field(description="维度标识，如 knowledge_mastery / assessment_performance")
    name: str = Field(description="维度中文名称，如'知识掌握度'")
    score: int = Field(ge=0, le=100, description="该维度评分 0-100")
    level: str = Field(description="等级：优秀 / 良好 / 中等 / 待加强")
    description: str = Field(description="评分说明，简述评分依据")


class ReportTrendPoint(BaseModel):
    """进步趋势中的单个数据点。"""

    label: str = Field(description="时间标签，如'第 1 周'或'2026-08-01'")
    score: int = Field(ge=0, le=100, description="该时间点的平均得分")
    metric: str = Field(description="指标名称，如'测验平均分'")


class LearningReportResponse(BaseModel):
    """学习效果评估报告的完整响应。"""

    user_id: str = Field(description="用户 external_id 或 UUID 字符串")
    course_id: str | None = Field(default=None, description="课程 ID（如有）")
    course_title: str | None = Field(default=None, description="课程标题（如有）")
    overall_score: int = Field(ge=0, le=100, description="总体评分 0-100")
    overall_level: str = Field(description="总体等级：优秀 / 良好 / 中等 / 待加强")
    dimensions: list[ReportDimensionScore] = Field(default_factory=list, description="各维度评分列表")
    progress_trend: list[ReportTrendPoint] = Field(default_factory=list, description="进步趋势数据点")
    weak_points: list[str] = Field(default_factory=list, description="薄弱知识点/维度列表")
    recommendations: list[str] = Field(default_factory=list, description="改进建议列表")
    assessment_count: int = Field(default=0, description="参与测评次数")
    event_count: int = Field(default=0, description="学习行为事件总数")
    generated_at: datetime = Field(description="报告生成时间")