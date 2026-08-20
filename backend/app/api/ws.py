from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import uuid4

import redis.asyncio as redis
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.deps import ensure_course_access
from app.core.rate_limit import RateLimitExceeded, check_chat_rate_limit
from app.core.tracing import get_trace_id, reset_trace_id, set_trace_id
from app.core.ws_auth import authenticate_websocket
from app.core.ws_utils import ws_close, ws_send_json
from app.schemas.ai import AiMessageRequest
from app.services.agent.workflow import AgentWorkflow, is_general_learning
from app.services.ai.orchestrator import AiOrchestratorService
from app.services.onboarding.service import OnboardingService
from app.services.resource.progress_events import redis_progress_configured, resource_task_progress_channel
from app.services.resource.repository import ResourceRepository

ws_router = APIRouter()
workflow = AgentWorkflow()
orchestrator = AiOrchestratorService(workflow)
logger = logging.getLogger(__name__)

_TERMINAL_RESOURCE_STATUSES = {"completed", "succeeded", "failed", "cancelled", "not_found"}


def _normalize_ai_ws_payload(raw_payload: Any) -> dict[str, Any] | None:
    """校验 AI WebSocket 输入帧必须是 JSON 对象，避免非对象负载落入兜底异常。"""

    if isinstance(raw_payload, dict):
        return raw_payload
    return None


def _resource_progress_payload(task: dict | None, task_id: str) -> dict:
    """把资源任务快照转换为前端实时进度事件。"""
    if not task:
        return {
            "type": "resource_generation_progress",
            "event": "resource_task_status",
            "task_id": task_id,
            "status": "not_found",
            "progress": 0,
        }
    return {"type": "resource_generation_progress", "event": "resource_task_status", **task}


def _is_terminal_resource_status(status: str | None) -> bool:
    """判断资源生成任务是否已进入终态。"""
    return (status or "") in _TERMINAL_RESOURCE_STATUSES


@ws_router.websocket("/ai/{conversation_id}")
async def ai_stream(websocket: WebSocket, conversation_id: str) -> None:
    """课程 AI 对话实时流。

    客户端连接 `/ws/ai/new` 或 `/ws/ai/{conversation_id}` 后，应在收到
    `auth_required` 时发送 `auth` 帧，再发送 ChatRequest JSON 负载。
    """
    db = SessionLocal()
    current_user = None
    last_payload: AiMessageRequest | None = None
    active_trace_id: str | None = None
    try:
        current_user = await authenticate_websocket(websocket, db)
        if not current_user:
            return

        while True:
            raw_payload = _normalize_ai_ws_payload(await websocket.receive_json())
            if raw_payload is None:
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "validation_error",
                        "message": "WebSocket 消息必须是 JSON 对象",
                    }
                )
                continue
            if raw_payload.get("type") == "stop":
                await websocket.send_json({"type": "stopped", "conversation_id": conversation_id})
                continue

            if conversation_id != "new" and not raw_payload.get("conversation_id"):
                raw_payload["conversation_id"] = conversation_id

            try:
                payload = AiMessageRequest(**raw_payload)
            except ValidationError as exc:
                await websocket.send_json({"type": "error", "message": exc.errors()})
                continue
            last_payload = payload

            if payload.mode == "course_rag_qa" and (payload.learning_scope == "general" or not payload.course_id):
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "course_required",
                        "message": "请选择课程后使用课程资料问答",
                    }
                )
                continue

            if payload.learning_scope == "course" or payload.course_id:
                try:
                    ensure_course_access(db, current_user, payload.course_id or "")
                except HTTPException as exc:
                    await websocket.send_json({"type": "error", "code": "forbidden", "message": exc.detail})
                    continue

            rate_key = payload.course_id if payload.learning_scope == "course" and payload.course_id else "general"
            try:
                check_chat_rate_limit(current_user.id, rate_key)
            except RateLimitExceeded as exc:
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "rate_limited",
                        "message": "AI 对话请求过于频繁",
                        "retry_after_seconds": exc.retry_after_seconds,
                    }
                )
                continue

            active_trace_id = str(raw_payload.get("trace_id") or f"ws_{uuid4().hex}")
            trace_token = set_trace_id(active_trace_id)
            try:
                # 引导模式分流：通用学习场景下，若携带 onboarding_history、force_onboarding
                # 或用户处于冷启动，则走 workflow.stream_chat 流式输出（含完整 onboarding 逻辑：
                # LLM 结构化返回、画像直写、onboarding_update、done.meta.onboarding）；
                # 否则保持原 handle_message 非流式路径，由意图路由分发到 chat/资源生成/资料问答。
                chat_request = payload.to_chat_request()
                should_stream_onboarding = is_general_learning(chat_request) and (
                    bool(chat_request.onboarding_history)
                    or bool(getattr(chat_request, "force_onboarding", False))
                    or OnboardingService(db).is_cold_start(current_user.id)
                )
                if should_stream_onboarding:
                    async for event in workflow.stream_chat(chat_request, db, current_user.id):
                        await websocket.send_json(jsonable_encoder(event))
                else:
                    response = await orchestrator.handle_message(payload, db, current_user.id)
                    await websocket.send_json({"type": "session_started", "conversation_id": response.conversation_id})
                    for trace_event in response.agent_trace:
                        await websocket.send_json(jsonable_encoder({"type": "agent_trace", "event": trace_event}))
                    await websocket.send_json({"type": "text_delta", "delta": response.answer})
                    if response.quality:
                        await websocket.send_json(jsonable_encoder({"type": "quality_update", "quality": response.quality}))
                    await websocket.send_json(
                        jsonable_encoder(
                            {
                                "type": "done",
                                "conversation_id": response.conversation_id,
                                "answer": response.answer,
                                "citations": response.citations,
                                "agent_trace": response.agent_trace,
                                "suggested_actions": response.suggested_actions,
                                "quality": response.quality,
                                "resource_task_id": response.resource_task_id,
                                "route": response.route,
                                "availability": response.availability,
                            }
                        )
                    )
            finally:
                reset_trace_id(trace_token)
    except WebSocketDisconnect:
        return
    except Exception as exc:  # pragma: no cover - WebSocket 会话的运行时防御兜底。
        logger.exception(
            "AI WebSocket 会话异常：conversation_id=%s user_id=%s course_id=%s mode=%s action_type=%s trace_id=%s exc_type=%s",
            conversation_id,
            getattr(current_user, "id", None),
            getattr(last_payload, "course_id", None),
            getattr(last_payload, "mode", None),
            getattr(last_payload, "action_type", None),
            active_trace_id or get_trace_id(),
            type(exc).__name__,
        )
        await ws_send_json(websocket, {"type": "error", "message": "AI 对话服务暂时异常，请稍后重试。"})
    finally:
        db.close()


async def _listen_resource_progress_pubsub(
    websocket: WebSocket,
    task_id: str,
    pubsub: redis.client.PubSub,
) -> bool:
    """监听 Redis 任务进度频道，任务进入终态时返回 True。"""
    while True:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if not message or message.get("type") != "message":
            await asyncio.sleep(0.05)
            continue
        raw_data = message.get("data")
        try:
            payload = json.loads(raw_data)
        except (TypeError, json.JSONDecodeError):
            raw_text = raw_data if isinstance(raw_data, str) else repr(raw_data)
            logger.debug(
                "资源任务进度 Redis 消息解析失败，已跳过坏包：task_id=%s message_type=%s data_length=%s data_preview=%s",
                task_id,
                message.get("type"),
                len(raw_text),
                raw_text[:200],
                exc_info=True,
            )
            continue
        await websocket.send_json(payload)
        if _is_terminal_resource_status(payload.get("status")):
            return True


async def _poll_resource_progress_db(
    websocket: WebSocket,
    task_id: str,
    user_external_id: str,
    *,
    is_admin: bool,
    interval_seconds: float = 2.0,
) -> None:
    """Redis pub/sub 不可用时，通过数据库轮询资源生成进度。"""
    db = SessionLocal()
    try:
        while True:
            try:
                task = ResourceRepository(db).get_generation_task(task_id, user_external_id, is_admin=is_admin)
            except PermissionError:
                await websocket.send_json({"type": "error", "code": "forbidden", "message": "无权订阅该资源生成任务"})
                return
            await websocket.send_json(_resource_progress_payload(task, task_id))
            if not task or _is_terminal_resource_status(task.get("status")):
                return
            await asyncio.sleep(interval_seconds)
    finally:
        db.close()


@ws_router.websocket("/resources/{task_id}")
async def resource_generation_progress(websocket: WebSocket, task_id: str) -> None:
    """推送资源生成进度；Redis 不可用时退回数据库轮询。"""
    db = SessionLocal()
    current_user = None
    try:
        current_user = await authenticate_websocket(websocket, db)
        if not current_user:
            return
        try:
            task = ResourceRepository(db).get_generation_task(
                task_id,
                current_user.id,
                is_admin=current_user.role == "admin",
            )
        except PermissionError:
            await websocket.send_json({"type": "error", "code": "forbidden", "message": "无权订阅该资源生成任务"})
            await ws_close(websocket, code=4403, reason="forbidden")
            return
        await websocket.send_json(_resource_progress_payload(task, task_id))
        if not task or _is_terminal_resource_status(task.get("status")):
            return
    finally:
        db.close()

    if not redis_progress_configured():
        await _poll_resource_progress_db(
            websocket,
            task_id,
            current_user.id,
            is_admin=current_user.role == "admin",
        )
        return

    redis_client: redis.Redis | None = None
    pubsub: redis.client.PubSub | None = None
    try:
        redis_client = redis.from_url(settings.VALKEY_URL, decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(resource_task_progress_channel(task_id))
        finished = await _listen_resource_progress_pubsub(websocket, task_id, pubsub)
        if finished:
            return
    except WebSocketDisconnect:
        return
    except Exception as exc:
        logger.warning(
            "资源任务进度 Redis 推送不可用，退回数据库轮询：task_id=%s user_id=%s is_admin=%s trace_id=%s exc_type=%s",
            task_id,
            getattr(current_user, "id", None),
            bool(current_user and current_user.role == "admin"),
            get_trace_id(),
            type(exc).__name__,
            exc_info=True,
        )
        if current_user is None:
            return
        await _poll_resource_progress_db(
            websocket,
            task_id,
            current_user.id,
            is_admin=current_user.role == "admin",
        )
        return
    finally:
        if pubsub is not None:
            try:
                await pubsub.unsubscribe(resource_task_progress_channel(task_id))
                await pubsub.close()
            except Exception:
                logger.debug("关闭资源任务 Redis pubsub 失败：task_id=%s", task_id, exc_info=True)
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                logger.debug("关闭资源任务 Redis 客户端失败：task_id=%s", task_id, exc_info=True)
