from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.rate_limit import RateLimitExceeded, check_sandbox_rate_limit
from app.schemas.sandbox import SandboxExecuteRequest, SandboxExecuteResponse
from app.services.sandbox.execution import (
    SandboxValidationError,
    execute_code,
    validate_code,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/execute", response_model=SandboxExecuteResponse)
async def execute_sandbox_code(
    payload: SandboxExecuteRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SandboxExecuteResponse:
    """执行用户提交的代码并返回运行结果。

    流程：登录鉴权 → 分钟级限流 → 静态安全校验 → 转发到 Node + Pyodide 微服务。
    代码在 Pyodide WASM 沙箱中隔离执行，超时与危险模块均被拦截。
    """
    try:
        check_sandbox_rate_limit(current_user.id)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "代码执行请求过于频繁，请稍后再试",
                "scope": exc.scope,
                "retry_after_seconds": exc.retry_after_seconds,
            },
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    try:
        validate_code(payload.code)
    except SandboxValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        result = await execute_code(payload.code, payload.language)
    except httpx.HTTPError as exc:
        logger.warning("沙箱微服务不可达: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="代码沙箱服务暂不可用，请稍后重试",
        ) from exc
    except SandboxValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return result
