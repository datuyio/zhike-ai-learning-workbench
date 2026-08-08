from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# 学习行为事件类型枚举，与 StudentLearningEvent 模型注释保持一致
LearningEventType = Literal["chat", "quiz", "resource_view", "code_run", "lesson_complete"]

# 聚合统计维度：按天 / 按周 / 按课程
LearningEventDimension = Literal["day", "week", "course"]


class LearningEventCreate(BaseModel):
    """学生学习行为事件采集请求体。

    字段映射说明（任务清单 → 现有表）：
    - user_id：不由前端传入，统一从登录态解析为 users.id 后写入 student_id；
    - event_data：写入 event_metadata(JSONB)；
    - session_id：合并进 event_metadata.session_id，不单独建列。
    """

    course_id: str | None = Field(default=None, description="事件关联课程 ID，可为空表示跨课程事件")
    event_type: LearningEventType = Field(description="事件类型：chat/quiz/resource_view/code_run/lesson_complete")
    event_data: dict[str, Any] | None = Field(default=None, description="事件元数据载荷，写入 event_metadata")
    session_id: str | None = Field(default=None, max_length=128, description="学习会话标识，合并进 event_metadata")


class LearningEventOut(BaseModel):
    """采集成功后返回的事件记录。"""

    id: str
    student_id: str
    course_id: str | None = None
    event_type: str
    event_metadata: dict[str, Any] | None = None
    created_at: datetime


class LearningEventStatsBucket(BaseModel):
    """单个聚合桶：某个时间/课程维度下的事件统计。"""

    key: str = Field(description="桶标识：日期(YYYY-MM-DD)、周起始日期或课程 ID")
    total: int = Field(description="该桶内事件总数")
    by_type: dict[str, int] = Field(default_factory=dict, description="按事件类型拆分的计数")


class LearningEventStatsOut(BaseModel):
    """学习行为事件聚合统计响应。"""

    dimension: LearningEventDimension
    student_id: str
    course_id: str | None = None
    range_start: datetime | None = None
    range_end: datetime | None = None
    buckets: list[LearningEventStatsBucket] = Field(default_factory=list)
    total: int = 0
