from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import CurrentUser
from app.core.security import hash_password, hash_token, issue_session_token, verify_password
from app.models import Session as UserSession
from app.models import User
from app.schemas.auth import AuthResponse, AuthUser, AuthUserResponse, LoginRequest, LogoutResponse, RegisterRequest, UpdateMeRequest


class AuthServiceError(Exception):
    """认证服务可预期业务异常基类。"""


class InvalidEmailError(AuthServiceError):
    """邮箱格式不符合平台账号要求。"""


class EmailAlreadyRegisteredError(AuthServiceError):
    """注册邮箱已经绑定了其他账号。"""


class InvalidCredentialsError(AuthServiceError):
    """登录凭据无效或账号不可用。"""


class CurrentUserNotFoundError(AuthServiceError):
    """当前登录态对应的用户记录不存在。"""


class InvalidDisplayNameError(AuthServiceError):
    """用户提交的显示名称为空或不合法。"""


def normalize_email(email: str) -> str:
    """标准化邮箱，避免大小写和首尾空格造成重复账号。"""
    return email.strip().lower()


def public_user(user: User) -> AuthUser:
    """把数据库用户模型转换为可返回给前端的公开用户信息。"""
    return AuthUser(id=user.external_id, name=user.display_name, role=user.role_code, email=user.email)


class AuthService:
    """封装注册、登录、资料更新和会话撤销的认证持久化逻辑。"""

    def __init__(self, db: Session) -> None:
        """保存当前请求使用的数据库会话。"""
        self.db = db

    def create_session(self, user: User, authorization: str | None = None) -> tuple[str, UserSession]:
        """为登录用户创建服务端会话。"""
        token = issue_session_token()
        session = UserSession(
            user_id=user.id,
            refresh_token_hash=hash_token(token),
            user_agent=authorization,
            ip_hash=None,
            revoked=False,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return token, session

    def register(self, payload: RegisterRequest, authorization: str | None = None) -> AuthResponse:
        """注册学生或教师账号并创建登录会话。"""
        email = normalize_email(payload.email)
        if "@" not in email:
            raise InvalidEmailError("邮箱格式不正确")
        if self.db.execute(select(User).where(User.email == email)).scalar_one_or_none():
            raise EmailAlreadyRegisteredError("该邮箱已注册")

        user = User(
            external_id=f"user_{uuid.uuid4().hex[:16]}",
            display_name=payload.name.strip(),
            email=email,
            password_hash=hash_password(payload.password),
            role_code=payload.role,
            status="active",
        )
        self.db.add(user)
        self.db.flush()
        token, _session = self.create_session(user, authorization)
        return AuthResponse(access_token=token, user=public_user(user))

    def login(self, payload: LoginRequest, authorization: str | None = None) -> AuthResponse:
        """校验邮箱密码并创建登录会话。"""
        # 兼容处理：如果 payload 是字符串，尝试解析为 LoginRequest
        if isinstance(payload, str):
            import json
            try:
                data = json.loads(payload)
                email = normalize_email(data.get('email', ''))
                password = data.get('password', '')
            except:
                email = normalize_email(payload)
                password = ''
        else:
            email = normalize_email(payload.email)
            password = payload.password

        user = self.db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        password_ok = settings.auth_skip_password_check_enabled or verify_password(password, user.password_hash if user else None)
        if not user or user.status != "active" or not password_ok:
            raise InvalidCredentialsError("邮箱或密码错误")

        if not settings.auth_skip_password_check_enabled and user.password_hash and user.password_hash.startswith("sha256$"):
            user.password_hash = hash_password(password)
            self.db.flush()

        token, _session = self.create_session(user, authorization)
        return AuthResponse(access_token=token, user=public_user(user))

    def update_current_user(self, payload: UpdateMeRequest, current_user: CurrentUser) -> AuthUserResponse:
        """更新当前登录用户可编辑的身份资料。"""
        display_name = payload.name.strip()
        if not display_name:
            raise InvalidDisplayNameError("显示名称不能为空")

        user = self.db.execute(select(User).where(User.external_id == current_user.id)).scalar_one_or_none()
        if not user:
            raise CurrentUserNotFoundError("当前账号不存在")

        user.display_name = display_name
        self.db.commit()
        self.db.refresh(user)
        return AuthUserResponse(user=public_user(user))

    def logout(self, authorization: str | None = None) -> LogoutResponse:
        """撤销当前会话令牌；缺少令牌时保持幂等成功。"""
        if not authorization or not authorization.lower().startswith("bearer "):
            return LogoutResponse(status="ok")
        token = authorization.split(" ", 1)[1].strip()
        row = self.db.execute(
            select(UserSession).where(UserSession.refresh_token_hash == hash_token(token), UserSession.revoked.is_(False))
        ).scalar_one_or_none()
        if row:
            row.revoked = True
            self.db.commit()
        return LogoutResponse(status="ok")