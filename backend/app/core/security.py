import hmac
import base64
import secrets
from hashlib import sha256

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


_password_hasher = PasswordHasher()


def mask_secret(value: str, visible: int = 4) -> str:
    """把敏感值脱敏为可展示文本。

    参数:
        value: 原始敏感值。
        visible: 保留展示的前缀字符数量。

    返回:
        脱敏后的字符串。
    """
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return value[:visible] + "*" * (len(value) - visible)


def _fernet() -> Fernet:
    digest = sha256(settings.ENCRYPTION_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str | None) -> str | None:
    """使用项目加密密钥加密第三方凭证。

    参数:
        value: 明文凭证或已经加密的 fernet 值。

    返回:
        带 `fernet:` 前缀的密文；空值返回 None。
    """
    if not value:
        return None
    if value.startswith("fernet:"):
        return value
    token = _fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"fernet:{token}"


def decrypt_secret(value: str | None) -> str | None:
    """解密第三方凭证。

    参数:
        value: 明文凭证、空值或带 `fernet:` 前缀的密文。

    返回:
        解密后的明文；密文无效或空值时返回 None。
    """
    if not value:
        return None
    if not value.startswith("fernet:"):
        return value
    try:
        return _fernet().decrypt(value.removeprefix("fernet:").encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def content_hash(content: str) -> str:
    """计算文本内容的 SHA-256 哈希，用于去重和幂等比对。"""
    return sha256(content.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """使用 Argon2id 生成密码哈希。

    参数:
        password: 用户提交的明文密码。

    返回:
        Argon2id 哈希字符串，可直接持久化到用户表。
    """
    return _password_hasher.hash(password)


def _verify_legacy_sha256_password(password: str, stored_hash: str) -> bool:
    """兼容早期 HMAC-SHA256 密码哈希，便于老账号平滑登录。"""
    try:
        algorithm, salt, expected = stored_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "sha256":
        return False
    actual = hmac.new(settings.JWT_SECRET_KEY.encode("utf-8"), f"{salt}:{password}".encode("utf-8"), sha256).hexdigest()
    return hmac.compare_digest(actual, expected)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    # 如果是 bcrypt 格式（以 $2b$ 开头），使用 bcrypt 验证
    if hashed_password.startswith('$2b$'):
        import bcrypt
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception:
            return False
    # 否则使用 Argon2
    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except Exception:
        return False

def issue_session_token() -> str:
    """签发随机会话令牌，明文只返回给当前登录响应。"""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """计算会话令牌哈希，避免在数据库中保存明文 token。"""
    return sha256(token.encode("utf-8")).hexdigest()
