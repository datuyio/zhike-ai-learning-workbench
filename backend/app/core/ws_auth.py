from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.core.deps import CurrentUser, resolve_user_from_token
from app.core.ws_utils import ws_close, ws_send_json
from sqlalchemy.orm import Session

WS_CLOSE_UNAUTHORIZED = 4401


def _normalize_auth_payload(raw_payload: Any) -> dict[str, Any] | None:
    """校验 WebSocket 鉴权帧必须是 JSON 对象。"""

    if isinstance(raw_payload, dict):
        return raw_payload
    return None


async def _reject_websocket(websocket: WebSocket, message: str) -> None:
    """发送 WebSocket 鉴权失败消息并关闭连接。"""
    if websocket.client_state == WebSocketState.CONNECTING:
        await websocket.accept()
    await ws_send_json(
        websocket,
        {"type": "auth_failed", "code": "unauthorized", "message": message},
    )
    await ws_close(websocket, code=WS_CLOSE_UNAUTHORIZED, reason="unauthorized")


async def authenticate_websocket(websocket: WebSocket, db: Session) -> CurrentUser | None:
    """完成 WebSocket 鉴权，优先使用连接后的 auth 帧，兼容旧版 query token。"""
    query_token = (websocket.query_params.get("token") or "").strip()
    if query_token:
        current_user = resolve_user_from_token(db, query_token)
        if not current_user:
            await _reject_websocket(websocket, "登录状态已失效，请重新登录")
            return None
        if websocket.client_state == WebSocketState.CONNECTING:
            await websocket.accept()
        await ws_send_json(websocket, {"type": "auth_ok"})
        return current_user

    if websocket.client_state == WebSocketState.CONNECTING:
        await websocket.accept()
    await ws_send_json(websocket, {"type": "auth_required"})

    try:
        raw_payload = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
    except WebSocketDisconnect:
        return None
    except TimeoutError:
        await _reject_websocket(websocket, "鉴权超时，请重新连接")
        return None

    auth_payload = _normalize_auth_payload(raw_payload)
    if not auth_payload or auth_payload.get("type") != "auth":
        await _reject_websocket(websocket, "请先登录")
        return None

    token = str(auth_payload.get("token") or "").strip()
    if not token:
        await _reject_websocket(websocket, "请先登录")
        return None

    current_user = resolve_user_from_token(db, token)
    if not current_user:
        await _reject_websocket(websocket, "登录状态已失效，请重新登录")
        return None

    await websocket.send_json({"type": "auth_ok"})
    return current_user
