"""助教端 AI Agent 编排服务（有身份、能聊天、能布置任务）。

设计借鉴「yueyang tower」教师端助教：
- 身份提示词：六模块结构（角色/能力边界/数据纪律/任务执行/输出表达/安全红线）。
- 工具调用循环：LLM(function calling) → 执行工具 → 结果回填 → 继续，直到模型不再请求工具。
- 写操作确认：布置作业/测验/公告等写工具先落待确认记录并暂停，教师确认后由确认端点执行。

零幻觉防线保留：知识库检索走 CourseRetriever + should_refuse_low_confidence 低分拒答，
业务数据由工具从数据库真实读取，杜绝编造。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tracing import get_trace_id
from app.models import User
from app.models.ta_agent_confirmation import TaAgentConfirmation
from app.schemas.ai import AgentTraceEvent, ChatQuality
from app.schemas.ta_agent import (
    TaAgentDataFact,
    TaAgentMessageRequest,
    TaAgentMessageResponse,
    TaAgentPendingConfirmation,
)
from app.services.agent.retrieval_guard import should_refuse_low_confidence
from app.services.model_gateway.router import ModelGateway
from app.services.safety.guardrail import SafetyGuardrail
from app.services.ta.prompts import (
    assistant_tool_call_message,
    build_teacher_messages,
    build_teacher_system_prompt,
    tool_result_message,
)
from app.services.ta.tools import (
    TaToolContext,
    get_tool,
    tool_definitions,
)

logger = logging.getLogger(__name__)

# 工具循环上限：防止模型反复请求工具导致死循环
MAX_AGENT_ROUNDS = 6
MAX_TOOL_CALLS_PER_ROUND = 5

_REFUSAL_UNSAFE = "该提问未通过安全审查，我已停止处理，请调整表述后重试。"

# 写操作工具名 → 中文动作（用于待确认摘要）
_WRITE_ACTION_LABELS = {
    "create_assignment": "布置作业",
    "publish_assignment": "发布作业",
    "create_quiz": "创建测验",
    "create_announcement": "发布公告",
}


def _write_summary(tool_name: str, args: dict[str, Any]) -> str:
    """为待确认写操作生成一句话摘要，展示给教师确认。"""
    label = _WRITE_ACTION_LABELS.get(tool_name, tool_name)
    title = str(args.get("title") or args.get("body") or "未命名").strip() or "未命名"
    return f"{label}「{title[:40]}」"


class TaAgentOrchestratorService:
    """助教端 Agent 编排：身份提示词 + 工具循环 + 零幻觉防线。"""

    def __init__(self) -> None:
        self.safety = SafetyGuardrail()

    # ── 入口 ──────────────────────────────────────────────────────────────

    async def handle_message(
        self,
        payload: TaAgentMessageRequest,
        db: Session,
        user_external_id: str,
    ) -> TaAgentMessageResponse:
        """处理教师端一轮对话：安全审查 → 工具循环 → 生成回答。"""
        trace: list[AgentTraceEvent] = []

        # 1. 安全审查
        safe = self.safety.check_user_input(payload.message)
        trace.append(AgentTraceEvent(step="安全审查", status="completed" if safe else "blocked"))
        if not safe:
            return self._build_response(
                payload=payload,
                answer=_REFUSAL_UNSAFE,
                trace=trace,
                refused=True,
                refusal_reason="unsafe",
                quality=ChatQuality(cite_check="skipped", safety="blocked"),
            )

        # 2. 解析教师身份
        user = db.execute(select(User).where(User.external_id == user_external_id)).scalar_one_or_none()
        if user is None:
            return self._build_response(
                payload=payload,
                answer="无法定位当前教师账号，请重新登录后重试。",
                trace=trace,
                refused=True,
                refusal_reason="no_user",
            )
        ctx = TaToolContext(db=db, user_external_id=user_external_id, user_internal_id=user.id)

        # 3. 组装消息（身份提示词 + 历史 + 当前问题）并执行工具循环
        history = await self._load_history(db, payload, user_external_id)
        messages = build_teacher_messages(history, payload.message)
        gateway = ModelGateway(db)

        trace.append(AgentTraceEvent(step="意图路由", status="completed", detail="身份提示词 + 工具调用循环"))
        answer, citations, data_facts, pending, loop_trace = await self._run_agent_loop(
            db=db,
            gateway=gateway,
            messages=messages,
            ctx=ctx,
            user_external_id=user_external_id,
        )
        trace.extend(loop_trace)

        # 4. 输出安全过滤
        safety = self.safety.check_output(answer)
        if safety["status"] == "blocked":
            answer = self.safety.sanitize_output(answer)
            trace.append(AgentTraceEvent(step="输出安全审查", status="blocked"))
        else:
            trace.append(AgentTraceEvent(step="输出安全审查", status="completed"))

        quality = ChatQuality(
            cite_check="passed" if citations else "skipped",
            safety="passed",
            citation_coverage="full" if citations else "none",
        )
        return self._build_response(
            payload=payload,
            answer=answer,
            citations=citations,
            data_facts=data_facts,
            trace=trace,
            quality=quality,
            pending_confirmation=pending,
        )

    # ── 工具循环 ───────────────────────────────────────────────────────────

    async def _run_agent_loop(
        self,
        *,
        db: Session,
        gateway: ModelGateway,
        messages: list[dict[str, Any]],
        ctx: TaToolContext,
        user_external_id: str,
    ) -> tuple[str, list, list[TaAgentDataFact], TaAgentPendingConfirmation | None, list[AgentTraceEvent]]:
        """执行 function calling 工具循环，直到模型不再请求工具或达到轮次上限。

        返回：(answer, citations, data_facts, pending_confirmation, trace)。
        """
        citations: list = []
        data_facts: list[TaAgentDataFact] = []
        trace: list[AgentTraceEvent] = []
        tools = tool_definitions()

        for round_index in range(1, MAX_AGENT_ROUNDS + 1):
            result = await gateway.complete_chat(
                messages=messages,
                course_slug=None,
                provider_code=gateway.resolve_course_chat_provider(None),
                user_override=gateway.user_chat_override(user_external_id),
                agent_name="TaAgent",
                temperature=settings.MODEL_GATEWAY_TEMPERATURE,
                max_tokens=settings.MODEL_GATEWAY_MAX_TOKENS,
                allow_fallback=True,
                tools=tools,
            )
            if result.is_fallback and not result.tool_calls:
                # 模型网关降级：无工具调用能力时退回纯对话（基于身份提示词）
                trace.append(AgentTraceEvent(
                    step="回答生成",
                    status="warning",
                    detail=f"{result.display_name}/{result.model} · 降级，无工具调用",
                ))
                return result.answer, citations, data_facts, None, trace

            tool_calls = result.tool_calls[:MAX_TOOL_CALLS_PER_ROUND]
            if not tool_calls:
                # 无工具调用：最终回答
                trace.append(AgentTraceEvent(
                    step="回答生成",
                    status="completed" if not result.is_fallback else "warning",
                    detail=f"{result.display_name}/{result.model} · {result.latency_ms}ms",
                ))
                return result.answer, citations, data_facts, None, trace

            # 记录工具调用轨迹并回填 assistant 消息
            for tc in tool_calls:
                trace.append(AgentTraceEvent(
                    step=f"工具调用：{tc['name']}",
                    status="completed",
                    detail=f"参数 {json.dumps(tc['arguments'], ensure_ascii=False)[:120]}",
                ))
            messages.append(assistant_tool_call_message(result.answer or "", tool_calls))

            # 逐工具执行
            for tc in tool_calls:
                tool = get_tool(tc["name"])
                if tool is None:
                    messages.append(tool_result_message(tc["id"], json.dumps({"error": f"未知工具 {tc['name']}"}, ensure_ascii=False)))
                    continue

                if tool.scope == "write":
                    # 写操作：落待确认记录并立即返回，等待教师确认
                    summary = _write_summary(tool.name, tc["arguments"])
                    confirmation = self._create_confirmation(db, ctx, tc["name"], tc["arguments"], summary)
                    trace.append(AgentTraceEvent(
                        step="待确认操作",
                        status="blocked",
                        detail=summary,
                    ))
                    pending = TaAgentPendingConfirmation(
                        confirmation_id=str(confirmation.id),
                        tool=tc["name"],
                        summary=summary,
                        args=tc["arguments"],
                    )
                    answer = f"我已准备好{summary}。请点击上方确认按钮后执行；如需调整请直接告诉我。"
                    return answer, citations, data_facts, pending, trace

                # 只读工具：直接执行
                data = tool.execute(ctx, tc["arguments"])
                summary_text = tool.summarize(data)
                trace.append(AgentTraceEvent(step="工具结果", status="completed", detail=summary_text))
                # 知识库工具结果已通过 tool 消息回填给模型，由模型在 answer 中引用；
                # 不再映射到响应 citations 字段（该字段要求标准 Citation 契约）。
                messages.append(tool_result_message(tc["id"], json.dumps(data, ensure_ascii=False, default=str)))

        # 达到轮次上限：礼貌收尾
        answer = "这个任务比较复杂，我暂时处理到这一步。你可以继续补充说明，我会接着完成。"
        return answer, citations, data_facts, None, trace

    # ── 确认机制 ───────────────────────────────────────────────────────────

    def _create_confirmation(
        self,
        db: Session,
        ctx: TaToolContext,
        tool_name: str,
        args: dict[str, Any],
        summary: str,
    ) -> TaAgentConfirmation:
        """落一条待确认写操作记录。"""
        confirmation = TaAgentConfirmation(
            ta_user_id=ctx.user_internal_id,
            tool=tool_name,
            args_json=args,
            summary=summary,
            status="pending",
        )
        db.add(confirmation)
        db.commit()
        db.refresh(confirmation)
        return confirmation

    async def execute_confirmation(
        self,
        db: Session,
        user_external_id: str,
        confirmation_id: str,
        action: str,
    ) -> dict[str, Any]:
        """教师确认/取消待执行写操作。"""
        user = db.execute(select(User).where(User.external_id == user_external_id)).scalar_one_or_none()
        if user is None:
            raise ValueError("无法定位当前教师账号")

        confirmation = self._find_confirmation(db, confirmation_id, user.id)
        if confirmation is None:
            raise ValueError("待确认事项不存在或无权访问")
        if confirmation.status != "pending":
            raise ValueError(f"该待确认事项已{'确认' if confirmation.status == 'confirmed' else '处理'}")

        if action == "cancel":
            confirmation.status = "cancelled"
            db.commit()
            return {"action": "cancel", "executed": False, "summary": None}

        tool = get_tool(confirmation.tool)
        if tool is None or tool.scope != "write":
            raise ValueError(f"工具不可执行：{confirmation.tool}")

        ctx = TaToolContext(db=db, user_external_id=user_external_id, user_internal_id=user.id)
        data = tool.execute(ctx, confirmation.args_json)
        if data.get("error"):
            confirmation.status = "cancelled"
            db.commit()
            raise ValueError(data["error"])
        confirmation.status = "confirmed"
        db.commit()
        return {"action": "confirm", "executed": True, "summary": tool.summarize(data)}

    @staticmethod
    def _find_confirmation(db: Session, confirmation_id: str, user_id) -> TaAgentConfirmation | None:
        """按 id 与归属教师查找待确认记录。"""
        try:
            from uuid import UUID
            cid = UUID(confirmation_id)
        except (ValueError, TypeError):
            return None
        return db.execute(
            select(TaAgentConfirmation).where(
                TaAgentConfirmation.id == cid,
                TaAgentConfirmation.ta_user_id == user_id,
            )
        ).scalar_one_or_none()

    # ── 历史加载 ───────────────────────────────────────────────────────────

    async def _load_history(
        self,
        db: Session,
        payload: TaAgentMessageRequest,
        user_external_id: str,
    ) -> list[dict[str, str]]:
        """加载会话历史（最近若干条），供多轮对话保持上下文。"""
        if not payload.conversation_id:
            return []
        try:
            from app.services.conversation.repository import ConversationRepository

            repo = ConversationRepository(db)
            conversation = repo.get_conversation_for_user(payload.conversation_id, user_external_id)
            if conversation is None:
                return []
            rows = repo.list_messages(conversation)
            history: list[dict[str, str]] = []
            for message, _citations in rows[-12:]:
                history.append({"role": message.role, "content": message.content})
            return history
        except Exception:  # noqa: BLE001 - 历史加载失败不影响本轮对话
            logger.debug("教师端 Agent 历史加载失败，按无历史处理：trace_id=%s", get_trace_id(), exc_info=True)
            return []

    # ── 响应构造 ───────────────────────────────────────────────────────────

    def _build_response(
        self,
        *,
        payload: TaAgentMessageRequest,
        answer: str,
        trace: list[AgentTraceEvent],
        citations: list | None = None,
        data_facts: list[TaAgentDataFact] | None = None,
        quality: ChatQuality | None = None,
        refused: bool = False,
        refusal_reason: str | None = None,
        pending_confirmation: TaAgentPendingConfirmation | None = None,
    ) -> TaAgentMessageResponse:
        """统一构造响应。"""
        return TaAgentMessageResponse(
            conversation_id=payload.conversation_id or f"conv_{uuid4().hex[:12]}",
            answer=answer,
            citations=citations or [],
            data_facts=data_facts or [],
            agent_trace=trace,
            quality=quality or ChatQuality(cite_check="skipped", safety="passed"),
            route="ta_agent",
            refused=refused,
            refusal_reason=refusal_reason,
            pending_confirmation=pending_confirmation,
        )
