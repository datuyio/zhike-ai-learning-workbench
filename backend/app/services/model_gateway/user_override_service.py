"""学生端个人模型覆盖配置的读写与运行时配置转换。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, encrypt_secret
from app.models import User, UserModelOverride
from app.schemas.model_gateway import ModelProviderUpsert, UserModelOverrideUpsert
from app.services.model_gateway.runtime_types import GatewayProviderConfig


class UserModelOverrideService:
    """管理单个用户的模型覆盖配置。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _user_id(self, user_external_id: str):
        user = self.db.execute(select(User).where(User.external_id == user_external_id)).scalar_one_or_none()
        return user.id if user else None

    def _override(self, user_external_id: str) -> UserModelOverride | None:
        user_id = self._user_id(user_external_id)
        if not user_id:
            return None
        return self.db.execute(
            select(UserModelOverride).where(UserModelOverride.user_id == user_id)
        ).scalar_one_or_none()

    def get_override(self, user_external_id: str) -> dict:
        override = self._override(user_external_id)
        if not override:
            return {
                "provider": None,
                "base_url": None,
                "chat_model": None,
                "embedding_model": None,
                "enabled": False,
                "key_configured": False,
            }
        return {
            "provider": override.provider,
            "base_url": override.base_url,
            "chat_model": override.chat_model,
            "embedding_model": override.embedding_model,
            "enabled": override.enabled,
            "key_configured": bool(override.api_key_encrypted),
        }

    def upsert_override(self, user_external_id: str, payload: UserModelOverrideUpsert) -> dict:
        user_id = self._user_id(user_external_id)
        if not user_id:
            raise ValueError("用户不存在或登录状态已失效")
        override = self._override(user_external_id)
        if override is None:
            override = UserModelOverride(user_id=user_id, provider=payload.provider)
            self.db.add(override)
        override.provider = payload.provider
        override.base_url = payload.base_url
        override.chat_model = payload.chat_model
        override.embedding_model = payload.embedding_model
        override.enabled = payload.enabled
        if payload.clear_api_key:
            override.api_key_encrypted = None
        elif payload.api_key:
            override.api_key_encrypted = encrypt_secret(payload.api_key)
        self.db.commit()
        self.db.refresh(override)
        return self.get_override(user_external_id)

    def delete_override(self, user_external_id: str) -> bool:
        override = self._override(user_external_id)
        if not override:
            return False
        self.db.delete(override)
        self.db.commit()
        return True

    def as_gateway_config(self, user_external_id: str) -> GatewayProviderConfig | None:
        """把已启用的个人覆盖转换为聊天网关可用的运行时配置。"""
        override = self._override(user_external_id)
        if not override or not override.enabled or not override.provider or not override.chat_model:
            return None
        api_key = decrypt_secret(override.api_key_encrypted)
        if not api_key and override.provider != "ollama":
            return None
        return GatewayProviderConfig(
            id=None,
            provider=override.provider,
            display_name=override.provider,
            provider_type="chat",
            base_url=override.base_url or "",
            api_key=api_key,
            key_source="user_override",
            protocol="openai_compatible",
            chat_model=override.chat_model,
            embedding_model=override.embedding_model,
            vision_model=None,
            image_model=None,
            embedding_dimension=None,
            max_batch_size=10,
            rate_limit_rps=None,
            supports_stream=True,
            supports_json_mode=True,
            priority=0,
            is_active=True,
            is_default=False,
        )

    def build_test_payload(self, user_external_id: str) -> ModelProviderUpsert | None:
        override = self._override(user_external_id)
        if not override or not override.provider or not override.chat_model:
            return None
        return ModelProviderUpsert(
            provider=override.provider,
            display_name=override.provider,
            provider_type="chat",
            base_url=override.base_url,
            protocol="openai_compatible",
            api_key=decrypt_secret(override.api_key_encrypted),
            chat_model=override.chat_model,
            supports_stream=True,
        )
