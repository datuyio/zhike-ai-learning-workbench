"""助教端 AI Agent 对话路由。

对外暴露：
- ``POST /ta/agent/messages``：教师以自然语言对话，Agent 有身份、能聊天、能布置任务；
  写操作返回待确认（pending_confirmation），由教师确认后执行。
- ``POST /ta/agent/confirm``：教师确认/取消待执行的写操作。

仅 ta/admin 角色可访问；会话轮次写入 conversations 表用于历史回溯。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser, require_ta
from app.core.rate_limit import RateLimitExceeded, check_chat_rate_limit
from app.models import User
from app.schemas.ta_agent import (
    TaAgentConfirmRequest,
    TaAgentConfirmResponse,
    TaAgentMessageRequest,
    TaAgentMessageResponse,
)
from app.services.conversation.repository import ConversationRepository
from app.services.ta.agent import TaAgentOrchestratorService

router = APIRouter(prefix="/ta", tags=["ta-portal"])

logger = logging.getLogger(__name__)

agent_service = TaAgentOrchestratorService()


@router.post("/agent/messages", response_model=TaAgentMessageResponse)
async def ta_agent_messages(
    payload: TaAgentMessageRequest,
    current_user: CurrentUser = Depends(require_ta),
    db: Session = Depends(get_db),
) -> TaAgentMessageResponse:
    """处理教师端 Agent 对话消息：限流 → 编排 → 会话持久化。"""
    try:
        check_chat_rate_limit(current_user.id, "ta_agent")
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={"message": "AI 对话请求过于频繁", "scope": exc.scope, "retry_after_seconds": exc.retry_after_seconds},
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    response = await agent_service.handle_message(payload, db, current_user.id)
    _persist_ta_turn(db, current_user.id, payload, response)
    return response


@router.post("/agent/confirm", response_model=TaAgentConfirmResponse)
async def ta_agent_confirm(
    payload: TaAgentConfirmRequest,
    current_user: CurrentUser = Depends(require_ta),
    db: Session = Depends(get_db),
) -> TaAgentConfirmResponse:
    """教师确认/取消待执行的写操作（布置作业、创建测验、发布公告等）。"""
    try:
        result = await agent_service.execute_confirmation(
            db, current_user.id, payload.confirmation_id, payload.action
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TaAgentConfirmResponse(
        action=result["action"],
        executed=result["executed"],
        summary=result.get("summary"),
    )


def _persist_ta_turn(
    db: Session,
    user_external_id: str,
    payload: TaAgentMessageRequest,
    response: TaAgentMessageResponse,
) -> None:
    """把教师端 Agent 一轮对话写入通用会话，失败不影响主流程返回。"""
    try:
        repo = ConversationRepository(db)
        conversation = repo.get_or_create_general_conversation(
            user_external_id=user_external_id,
            conversation_id=response.conversation_id,
            title=payload.message[:120] if payload.message else None,
        )
        user = db.execute(select(User).where(User.external_id == user_external_id)).scalar_one_or_none()
        if user is None:
            return
        repo.append_message(conversation, "user", payload.message, {"scope": "ta_agent"})
        assistant_message = repo.append_message(
            conversation,
            "assistant",
            response.answer,
            {
                "scope": "ta_agent",
                "route": response.route,
                "refused": response.refused,
                "refusal_reason": response.refusal_reason,
                "model_meta": {},
            },
        )
        repo.append_citations(assistant_message, response.citations)
        repo.append_trace(conversation, assistant_message, response.agent_trace)
        repo.commit()
    except Exception:  # noqa: BLE001 - 会话持久化失败不应阻断回答返回
        logger.debug("教师端 Agent 会话持久化失败：trace 保留在响应中", exc_info=True)
        db.rollback()
