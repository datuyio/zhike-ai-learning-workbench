"""助教端 AI Agent 对话的请求与响应模型。

教师端 Agent 是有身份、能聊天、能布置任务的智能体：
- 课程知识问答基于本地知识库检索，低置信度拒答（零幻觉）；
- 业务查询/写操作通过工具调用完成，写操作先返回待确认（pending_confirmation），
  由教师确认后执行。
复用学习端 Citation、AgentTraceEvent、ChatQuality 契约，保证前端渲染一致。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.ai import AgentTraceEvent, ChatQuality
from app.schemas.common import Citation


class TaAgentMessageRequest(BaseModel):
    """教师端 Agent 单轮对话请求。"""

    message: str = Field(..., min_length=1, max_length=4000, description="教师提问内容")
    course_id: str | None = Field(default=None, description="课程 slug 或 UUID；知识库检索时指定课程")
    conversation_id: str | None = Field(default=None, description="会话 ID；缺省时后端新建")
    require_citations: bool | None = Field(default=None, description="是否强制要求知识库引用；缺省按意图自动决定")


class TaAgentDataFact(BaseModel):
    """业务数据工具返回的一条可核验事实，前端可展示为数据卡片。"""

    label: str = Field(..., description="事实名称，如「班级学生数」")
    value: str = Field(..., description="事实值，如「23」")
    detail: str | None = Field(default=None, description="补充说明，如来源班级/作业名称")


class TaAgentPendingConfirmation(BaseModel):
    """待教师确认的写操作。"""

    confirmation_id: str = Field(..., description="待确认记录 id")
    tool: str = Field(..., description="工具名，如 create_assignment")
    summary: str = Field(..., description="待确认操作的一句话说明，如「布置作业《第1章练习》到 深度学习 01 班」")
    args: dict = Field(default_factory=dict, description="确认后执行的工具参数快照")


class TaAgentMessageResponse(BaseModel):
    """教师端 Agent 单轮对话响应。"""

    conversation_id: str
    answer: str
    citations: list[Citation] = Field(default_factory=list, description="知识库引用，零幻觉防线证据")
    data_facts: list[TaAgentDataFact] = Field(default_factory=list, description="业务数据工具返回的可核验事实")
    agent_trace: list[AgentTraceEvent] = Field(default_factory=list, description="Agent 执行步骤轨迹")
    quality: ChatQuality | None = None
    route: str = Field(default="ta_agent", description="实际执行的意图路由")
    refused: bool = Field(default=False, description="是否因证据不足拒答（零幻觉防线触发）")
    refusal_reason: str | None = Field(default=None, description="拒答原因：no_hit / low_confidence / unsafe")
    pending_confirmation: TaAgentPendingConfirmation | None = Field(default=None, description="待教师确认的写操作；无则为 None")


class TaAgentConfirmRequest(BaseModel):
    """教师确认/取消待执行写操作的请求。"""

    confirmation_id: str = Field(..., description="待确认记录 id")
    action: str = Field(..., pattern="^(confirm|cancel)$", description="confirm=执行，cancel=取消")


class TaAgentConfirmResponse(BaseModel):
    """确认操作结果。"""

    action: str
    executed: bool
    summary: str | None = None
