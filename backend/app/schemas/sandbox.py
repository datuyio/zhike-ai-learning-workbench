from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SandboxLanguage(str, Enum):
    """沙箱支持的编程语言。

    当前仅支持 Python，通过 Pyodide 在 Node 微服务中执行。
    新增语言时在此枚举扩展，并在前端与沙箱微服务同步支持。
    """

    PYTHON = "python"


class SandboxExecuteRequest(BaseModel):
    """代码沙箱执行请求。

    code 为用户提交的源代码字符串，language 限定可执行语言。
    服务端会先做静态安全校验，再转发到 Node + Pyodide 微服务执行。
    """

    code: str = Field(..., min_length=1, description="待执行的源代码，不能为空")
    language: SandboxLanguage = Field(default=SandboxLanguage.PYTHON, description="编程语言，当前仅支持 python")


class SandboxExecuteResponse(BaseModel):
    """代码沙箱执行结果。

    output 为标准输出合并内容，error 为标准错误或异常信息，
    execution_time 为微服务侧实际执行耗时（毫秒）。
    """

    language: SandboxLanguage = Field(..., description="本次执行的语言")
    output: str = Field(default="", description="标准输出内容")
    error: str = Field(default="", description="标准错误或运行异常信息")
    execution_time_ms: int = Field(..., ge=0, description="微服务侧执行耗时（毫秒）")
