from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.core.config import settings
from app.core.deps import CurrentUser, get_current_user
from app.schemas.sandbox import SandboxExecuteRequest, SandboxExecuteResponse
from app.services.sandbox.execution import (
    SandboxValidationError,
    execute_code,
    validate_code,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/execute", response_model=SandboxExecuteResponse, summary="执行代码沙箱")
async def execute_sandbox(
    payload: SandboxExecuteRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> SandboxExecuteResponse:
    """执行用户提交的代码。

    先做静态安全校验拦截危险模块与动态调用，再转发到 Node + Pyodide
    沙箱微服务执行。校验失败返回 400，微服务不可达返回 503，便于前端
    明确区分用户输入问题和基础设施问题。
    """
    try:
        validate_code(payload.code)
    except SandboxValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        return await execute_code(payload.code, payload.language)
    except SandboxValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        logger.exception("沙箱微服务不可达 service_url=%s", settings.SANDBOX_SERVICE_URL)
        raise HTTPException(status_code=503, detail="代码沙箱服务暂不可用，请稍后重试")