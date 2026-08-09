from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class PushItemDTO(BaseModel):
    """自适应推送中的单个推荐项。"""

    rule_type: str = Field(description="规则来源：profile_driven / assessment_driven / time_driven")
    rule_label: str = Field(description="规则的中文说明，如'掌握度低于阈值'")
    priority: int = Field(default=50, ge=0, le=100, description="推送优先级 0-100，越高越紧急")
    title: str = Field(description="推送标题")
    description: str = Field(description="推送说明/理由")
    resource_id: str | None = Field(default=None, description="关联的资源 ID（如有）")
    resource_title: str | None = Field(default=None, description="关联的资源标题")
    resource_type: str | None = Field(default=None, description="资源类型")
    concept_id: str | None = Field(default=None, description="关联的知识点 ID")
    concept_title: str | None = Field(default=None, description="知识点标题")
    current_score: int | None = Field(default=None, description="当前掌握度/评分值")
    threshold: int | None = Field(default=None, description="触发阈值")
    last_active_at: datetime | None = Field(default=None, description="最近一次学习时间（时间驱动规则使用）")


class PushListResponse(BaseModel):
    """自适应推送列表响应。"""

    items: list[PushItemDTO] = Field(default_factory=list)
    total: int = 0