from __future__ import annotations

import ast
import logging
import re

import httpx

from app.core.config import settings
from app.schemas.sandbox import SandboxExecuteResponse, SandboxLanguage

logger = logging.getLogger(__name__)

# 危险 import 模块黑名单：禁止访问文件系统、网络、子进程、系统调用等。
# 这些模块在 Pyodide WASM 沙箱中本身受限，静态拦截可在转发前快速失败并给出明确提示。
_BLOCKED_IMPORTS: frozenset[str] = frozenset(
    {
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
    }
)

# 危险动态入口黑名单：这些内建函数与属性是绕过 import 黑名单的主要途径，
# 静态阶段直接拦截，给用户明确反馈。
# 注意：Python 动态语言特性意味着仍可能构造出绕过静态检查的写法
# （如 getattr(builtins, "__import__")(...)），本层不保证绝对阻断，
# 最终安全边界由 Pyodide 的 WASM 隔离兜底（无宿主文件系统/网络访问）。
_BLOCKED_NAMES: frozenset[str] = frozenset(
    {
        "__import__",  # 动态导入入口，直接绕过 import 黑名单
        "exec",  # 执行任意字符串，可在字符串内藏 import
        "eval",
        "compile",
        "open",  # 文件读写入口
        "breakpoint",
        "globals",
        "locals",
        "vars",
        "getattr",  # 可 getattr(builtins, "__import__") 间接调用
        "setattr",
        "delattr",
    }
)

# 危险模块的属性访问也拦：如 importlib.import_module、builtins.__import__
# 通过匹配 Attribute 访问链的属性名实现
_BLOCKED_ATTRS: frozenset[str] = frozenset(
    {
        "import_module",  # importlib.import_module
        "__import__",  # builtins.__import__
        "__builtins__",
    }
)

# AST 解析失败时（语法错误的代码）退回正则兜底，避免漏放可执行的危险片段。
# 兜底正则只拦行首 import/from 的黑名单模块，动态绕过由沙箱 WASM 兜底。
_IMPORT_FALLBACK_PATTERN = re.compile(
    r"^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    re.MULTILINE,
)


class SandboxValidationError(Exception):
    """代码静态安全校验失败时抛出。

    message 描述具体违规原因，路由层据此返回 400。
    """


def _blocked_imports_from_ast(tree: ast.AST) -> list[str]:
    """从 AST 中提取所有 import 语句涉及的模块名，返回命中黑名单的列表。

    覆盖 import os / import os as o / from os import x / from os.path import x
    等所有写法，只看被导入的顶层模块名。
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _BLOCKED_IMPORTS:
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top in _BLOCKED_IMPORTS:
                    found.append(node.module)
    return found


def _blocked_calls_from_ast(tree: ast.AST) -> list[str]:
    """从 AST 中提取对危险内建函数的直接调用。

    覆盖 __import__("os")、exec(...)、eval(...)、open(...) 等直接调用写法。
    注意：经变量赋值后再调用（f=open; f(...)）不在本层覆盖范围，
    最终由 Pyodide WASM 隔离兜底。
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # 直接名称调用：__import__(...)、open(...)
            if isinstance(func, ast.Name) and func.id in _BLOCKED_NAMES:
                found.append(func.id)
    return found


def _blocked_attrs_from_ast(tree: ast.AST) -> list[str]:
    """从 AST 中提取对危险属性的访问。

    覆盖 importlib.import_module、builtins.__import__ 等属性访问链。
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _BLOCKED_ATTRS:
            found.append(node.attr)
    return found


def validate_code(code: str) -> None:
    """对用户代码做静态安全校验。

    本层定位为「基于 Pyodide/WASM 隔离 + 静态检查限制危险操作」，
    而非绝对安全沙箱：Python 动态特性可构造绕过静态检查的写法，
    最终安全边界由 Pyodide 的 WASM 隔离兜底（无宿主文件系统/网络访问）。

    校验内容：
    - 代码长度不超过配置上限，防止超大负载压垮微服务；
    - 拦截黑名单模块的 import（含 as 别名、from import 等所有写法）；
    - 拦截危险动态入口的直接调用：__import__/exec/eval/compile/open 等；
    - 拦截危险属性访问：importlib.import_module、builtins.__import__ 等；
    - AST 解析失败时退回正则兜底，语法错误代码不阻断（交由沙箱返回真实错误）。

    参数:
        code: 用户提交的源代码字符串。

    异常:
        SandboxValidationError: 任一校验未通过时抛出。
    """
    if len(code.encode("utf-8")) > settings.SANDBOX_MAX_CODE_BYTES:
        raise SandboxValidationError(
            f"代码体积超过上限（{settings.SANDBOX_MAX_CODE_BYTES // 1024} KB）"
        )

    try:
        tree = ast.parse(code)
    except SyntaxError:
        # 语法错误的代码不会被执行，但可能有可执行片段（被 try 包裹等），
        # 用正则兜底拦行首 import 黑名单模块，其余放行让沙箱返回真实语法错误
        matched = {m.group(1) for m in _IMPORT_FALLBACK_PATTERN.finditer(code)}
        blocked = matched & _BLOCKED_IMPORTS
        if blocked:
            raise SandboxValidationError(
                f"代码中存在被禁止的模块：{', '.join(sorted(blocked))}"
            )
        return

    violations: list[str] = []
    blocked_imports = _blocked_imports_from_ast(tree)
    if blocked_imports:
        violations.append(
            f"禁止导入模块：{', '.join(sorted(set(blocked_imports)))}"
        )
    blocked_calls = _blocked_calls_from_ast(tree)
    if blocked_calls:
        violations.append(
            f"禁止调用危险函数：{', '.join(sorted(set(blocked_calls)))}"
        )
    blocked_attrs = _blocked_attrs_from_ast(tree)
    if blocked_attrs:
        violations.append(
            f"禁止访问危险属性：{', '.join(sorted(set(blocked_attrs)))}"
        )
    if violations:
        raise SandboxValidationError("；".join(violations))


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
