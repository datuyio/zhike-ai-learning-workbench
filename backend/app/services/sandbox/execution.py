from __future__ import annotations

import logging
import re

import httpx

from app.core.config import settings
from app.schemas.sandbox import SandboxExecuteResponse, SandboxLanguage

logger = logging.getLogger(__name__)

# 危险 import 模块黑名单：禁止访问文件系统、网络、子进程、系统调用等
# 这些模块在 Pyodide 中本身受限，但静态拦截可在转发前快速失败并给出明确提示
_BLOCKED_IMPORTS: tuple[str, ...] = (
    "os",
    "sys",
    "subprocess",
    "socket",
    "http",
    "urllib",
    "requests",
    "ctypes",
    "multiprocessing",
    "threading",
    "signal",
    "shutil",
    "pathlib",
    "glob",
    "pickle",
    "marshal",
    "webbrowser",
    "asyncio.subprocess",
)

# 匹配 import 语句中的顶层模块名，用于黑名单比对
_IMPORT_PATTERN = re.compile(
    r"^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    re.MULTILINE,
)


class SandboxValidationError(Exception):
    """代码静态安全校验失败时抛出。

    message 描述具体违规原因，路由层据此返回 400。
    """


def validate_code(code: str) -> None:
    """对用户代码做静态安全校验。

    校验内容包括：
    - 代码长度不超过配置上限，防止超大负载压垮微服务；
    - 不含黑名单模块的 import，防止越权访问系统资源。

    参数:
        code: 用户提交的源代码字符串。

    异常:
        SandboxValidationError: 任一校验未通过时抛出。
    """
    if len(code.encode("utf-8")) > settings.SANDBOX_MAX_CODE_BYTES:
        raise SandboxValidationError(
            f"代码体积超过上限（{settings.SANDBOX_MAX_CODE_BYTES // 1024} KB）"
        )

    matched_modules = {match.group(1) for match in _IMPORT_PATTERN.finditer(code)}
    blocked = matched_modules & set(_BLOCKED_IMPORTS)
    if blocked:
        raise SandboxValidationError(
            f"代码中存在被禁止的模块：{', '.join(sorted(blocked))}"
        )


async def execute_code(code: str, language: SandboxLanguage) -> SandboxExecuteResponse:
    """转发代码到 Node + Pyodide 沙箱微服务执行并返回结果。

    调用前需先通过 validate_code 静态校验。
    超时由 SANDBOX_EXECUTION_TIMEOUT_SECONDS 控制，超时返回超时错误而非抛异常，
    便于前端直接展示错误信息。

    参数:
        code: 已通过静态校验的源代码字符串。
        language: 执行语言，当前仅支持 python。

    返回:
        SandboxExecuteResponse: 执行结果，含输出、错误和耗时。

    异常:
        SandboxValidationError: 当语言暂不支持时抛出。
        httpx.HTTPError: 当微服务不可达时抛出，由路由层捕获转为 503。
    """
    if language != SandboxLanguage.PYTHON:
        raise SandboxValidationError(f"暂不支持的语言：{language.value}")

    payload = {"code": code, "language": language.value}
    timeout = httpx.Timeout(settings.SANDBOX_EXECUTION_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{settings.SANDBOX_SERVICE_URL}/execute",
                json=payload,
            )
    except httpx.ReadTimeout as exc:
        logger.warning("沙箱执行超时 user_code_hash=%s", _code_hash(code))
        return SandboxExecuteResponse(
            language=language,
            output="",
            error=f"执行超时（{settings.SANDBOX_EXECUTION_TIMEOUT_SECONDS:.0f} 秒）",
            execution_time_ms=int(settings.SANDBOX_EXECUTION_TIMEOUT_SECONDS * 1000),
        )

    if resp.status_code != 200:
        logger.warning(
            "沙箱微服务返回非 200 status=%s body=%s",
            resp.status_code,
            resp.text[:500],
        )
        raise SandboxValidationError("沙箱微服务执行失败，请稍后重试")

    data = resp.json()
    return SandboxExecuteResponse(
        language=language,
        output=str(data.get("output", "")),
        error=str(data.get("error", "")),
        execution_time_ms=int(data.get("execution_time_ms", 0)),
    )


def _code_hash(code: str) -> str:
    """生成代码短哈希用于日志，避免日志泄露完整用户代码。"""
    import hashlib

    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]
