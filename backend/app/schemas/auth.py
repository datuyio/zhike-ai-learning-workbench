from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求参数。"""

    email: str
    password: str


class RegisterRequest(BaseModel):
    """注册请求参数；role 决定注册为学习端学生还是助教端教师。"""

    name: str = Field(min_length=1, max_length=120)
    email: str
    password: str = Field(min_length=8, max_length=128)
    role: Literal["student", "ta"] = "student"


class UpdateMeRequest(BaseModel):
    """当前登录用户可自行维护的身份资料。"""

    name: str = Field(min_length=1, max_length=120)


class AuthUser(BaseModel):
    """返回给前端的公开用户信息。"""

    id: str
    name: str
    role: str
    email: str | None = None


class AuthResponse(BaseModel):
    """登录或注册成功后的鉴权响应。"""

    access_token: str
    token_type: str = "bearer"
    user: AuthUser


class AuthUserResponse(BaseModel):
    """当前登录用户资料响应。"""

    user: AuthUser


class LogoutResponse(BaseModel):
    """退出登录响应。"""

    status: str
