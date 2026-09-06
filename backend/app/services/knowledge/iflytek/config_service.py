from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.models import AdminAuditLog, RagIntegrationConfig, User
from app.schemas.chatdoc_config import ChatdocConfigUpsert
from app.services.knowledge.iflytek.client import IflytekChatDocClient, IflytekChatDocError
from app.services.knowledge.integration_templates import (
    get_template,
    list_integration_templates,
    normalize_template_key,
    template_key_for_rag_backend,
)
from app.services.knowledge.iflytek.pipeline_config import (
    parse_pipeline_config_json,
    serialize_pipeline_config_json,
    wiki_filter_score_from_pipeline,
)
from app.services.knowledge.iflytek.vendor_quota import (
    ChatdocVendorQuotaNotReadyError,
    ChatdocVendorQuotaService,
    try_get_quota_view,
)
from app.services.knowledge.rag_env_credentials import (
    credential_env_var_name,
    has_env_credentials,
    merge_db_and_env_credentials,
    resolve_app_id_and_secret,
    wiki_filter_default_from_template,
)

logger = logging.getLogger(__name__)

# 兼容既有数据行和测试用例。
INTEGRATION_KEY = "iflytek_chatdoc"
ACTIVE_SELECTION_KEY = "_active_selection"
LEGACY_KEY_ALIASES = {
    "iflytek_chatdoc": "iflytek-chatdoc",
    "iflytek-chatdoc": "iflytek-chatdoc",
}


class ChatdocConfigService:
    """管理 ChatDoc 接入配置、凭证解析和连接测试。

    参数：
        db: SQLAlchemy 数据库会话，用于读取和写入接入配置、审计日志及测试状态。

    副作用：
        部分方法会写入配置行、审计日志或连接测试结果，并可能提交当前数据库事务。

    失败模式：
        模板不存在、凭证缺失、数据库写入失败或供应商接口异常时，公开方法会抛出异常或返回失败视图。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def _row(self, integration_key: str | None = None) -> RagIntegrationConfig | None:
        key = self._storage_key(integration_key)
        row = self.db.execute(
            select(RagIntegrationConfig).where(RagIntegrationConfig.integration_key == key)
        ).scalar_one_or_none()
        if row is not None:
            return row
        legacy_key = self._legacy_storage_key(integration_key)
        if legacy_key and legacy_key != key:
            return self.db.execute(
                select(RagIntegrationConfig).where(RagIntegrationConfig.integration_key == legacy_key)
            ).scalar_one_or_none()
        return None

    def _ensure_row(
        self,
        integration_key: str | None = None,
        *,
        preset_template_key: str | None = None,
    ) -> RagIntegrationConfig:
        row = self._row(integration_key)
        if row is None:
            preset = preset_template_key or (
                self._preset_key_for_instance(integration_key) if integration_key else None
            )
            template = get_template(preset) if preset else None
            wiki_default = wiki_filter_default_from_template(template)
            row = RagIntegrationConfig(
                integration_key=self._storage_key(integration_key),
                preset_template_key=preset if preset and integration_key else None,
                wiki_filter_score=wiki_default,
                is_active=True,
            )
            self.db.add(row)
            self.db.flush()
        return row

    def _storage_key(self, integration_key: str | None) -> str:
        if not integration_key or integration_key == ACTIVE_SELECTION_KEY:
            return ACTIVE_SELECTION_KEY if integration_key == ACTIVE_SELECTION_KEY else normalize_template_key(integration_key)
        return normalize_template_key(integration_key)

    def _legacy_storage_key(self, integration_key: str | None) -> str | None:
        normalized = normalize_template_key(integration_key)
        if normalized == "iflytek-chatdoc":
            return INTEGRATION_KEY
        return None

    def active_template_key(self) -> str:
        """返回当前启用的接入实例 key。

        参数：
            无。

        返回：
            当前激活选择记录中的接入实例 key；未配置时返回项目 RAG 后端对应的默认模板 key。

        副作用与失败模式：
            仅查询数据库，不修改状态；数据库查询失败时由 SQLAlchemy 抛出异常。
        """
        selection = self._row(ACTIVE_SELECTION_KEY)
        if selection and (selection.app_id or "").strip():
            return normalize_template_key(selection.app_id)
        return template_key_for_rag_backend(settings.RAG_BACKEND)

    def set_active_template_key(self, template_key: str) -> None:
        """记录当前启用的接入实例。

        参数：
            template_key: 要设为激活状态的接入实例 key，表示 integration_key 而非预置模板 key。

        返回：
            None。

        副作用与失败模式：
            会创建或更新激活选择记录并 flush 当前数据库会话；数据库写入失败时由 SQLAlchemy 抛出异常。
        """
        row = self._ensure_row(ACTIVE_SELECTION_KEY)
        row.app_id = template_key.strip()
        self.db.flush()

    def _preset_key_for_instance(self, instance_key: str) -> str:
        row = self._row(instance_key)
        if row and (row.preset_template_key or "").strip():
            return normalize_template_key(row.preset_template_key)
        return normalize_template_key(instance_key)

    def pipeline_config(self, instance_key: str | None = None) -> dict | None:
        """读取指定接入实例的流水线配置。

        参数：
            instance_key: 接入实例 key；为空时使用当前激活实例。

        返回：
            解析后的流水线配置字典；未配置或记录不存在时返回 None。

        副作用与失败模式：
            仅查询数据库，不修改状态；配置 JSON 解析失败时由解析函数处理或抛出异常。
        """
        key = (instance_key or self.active_template_key()).strip()
        row = self._row(key)
        if not row or not row.pipeline_config_json:
            return None
        return parse_pipeline_config_json(row.pipeline_config_json)

    def wiki_filter_score(self, instance_key: str | None = None) -> float:
        """计算指定接入实例的知识库召回过滤分数。

        参数：
            instance_key: 接入实例 key；为空时使用当前激活实例。

        返回：
            合并模板默认值、数据库配置和流水线配置后的过滤分数。

        副作用与失败模式：
            仅查询数据库和本地模板，不修改状态；配置解析失败时可能抛出异常。
        """
        key = (instance_key or self.active_template_key()).strip()
        row = self._row(key)
        base: float
        if row and row.wiki_filter_score is not None:
            base = float(row.wiki_filter_score)
        else:
            preset_key = self._preset_key_for_instance(key)
            base = wiki_filter_default_from_template(get_template(preset_key))
        pipeline = self.pipeline_config(key)
        return wiki_filter_score_from_pipeline(pipeline, base)

    def _merged_credentials(self, instance_key: str) -> tuple:
        preset_key = self._preset_key_for_instance(instance_key)
        template = get_template(preset_key)
        row = self._row(instance_key)
        db_app_id = ""
        db_secret = ""
        db_base_url = ""
        if row and row.is_active:
            db_app_id = (row.app_id or "").strip()
            if row.api_secret_encrypted:
                db_secret = (decrypt_secret(row.api_secret_encrypted) or "").strip()
            if row.base_url:
                db_base_url = row.base_url.strip()
        merged = merge_db_and_env_credentials(
            template,
            app_id=db_app_id,
            api_secret=db_secret,
            base_url=db_base_url,
        )
        return template, merged, resolve_app_id_and_secret(template, merged)

    def resolve_credentials(self, instance_key: str | None = None) -> tuple[str, str]:
        """解析指定接入实例的有效 AppId 与 APISecret。

        参数：
            instance_key: 接入实例 key；为空时使用当前激活实例。

        返回：
            二元组，依次为有效 AppId 和 APISecret；未配置时返回空字符串。

        副作用与失败模式：
            仅读取数据库、环境变量和本地模板；密文解密或数据库读取失败时可能抛出异常。
        """
        key = (instance_key or self.active_template_key() or "").strip()
        _template, _merged, (app_id, api_secret) = self._merged_credentials(key)
        return app_id, api_secret

    def credential_source(self, instance_key: str | None = None) -> str:
        """判断指定接入实例当前使用的凭证来源。

        参数：
            instance_key: 接入实例 key；为空时使用当前激活实例。

        返回：
            "database"、"environment" 或 "none"，分别表示管理端存储、环境变量或未配置。

        副作用与失败模式：
            仅读取配置和模板，不修改状态；密文解密或数据库读取失败时可能抛出异常。
        """
        key = (instance_key or self.active_template_key() or "").strip()
        preset_key = self._preset_key_for_instance(key)
        template = get_template(preset_key)
        row = self._row(key)
        if row and row.is_active:
            has_db_app = bool((row.app_id or "").strip())
            has_db_secret = bool(row.api_secret_encrypted and decrypt_secret(row.api_secret_encrypted))
            if has_db_app or has_db_secret:
                return "database"
        if template and has_env_credentials(template):
            return "environment"
        return "none"

    def get_admin_view(self, instance_key: str | None = None) -> dict:
        """构造管理端展示所需的 ChatDoc 接入配置视图。

        参数：
            instance_key: 接入实例 key；为空时使用当前激活实例。

        返回：
            包含模板信息、有效凭证状态、流水线配置、连接测试状态和供应商余量的字典。

        副作用与失败模式：
            会读取数据库、模板和可能的余量表，不提交事务；数据库、解密或配置解析失败时可能抛出异常。
        """
        active_key = self.active_template_key()
        key = (instance_key or active_key or "").strip() or active_key
        preset_key = self._preset_key_for_instance(key)
        template = get_template(preset_key)
        if template is None:
            template = get_template(active_key)
            preset_key = active_key if template else preset_key
        row = self._row(key)
        app_id, api_secret = self.resolve_credentials(key)
        configured = bool(app_id and api_secret)
        masked = mask_secret(api_secret) if api_secret else ""
        db_app = (row.app_id or "").strip() if row else ""
        has_db_secret = bool(row and row.api_secret_encrypted)
        wiki_default = wiki_filter_default_from_template(template)
        quota_view = try_get_quota_view(self.db, key) if self.supports_vendor_quota(key) else None
        display_label = (row.display_label or "").strip() if row and row.display_label else ""
        return {
            "integration_key": key,
            "active_integration_key": active_key,
            "template_key": preset_key,
            "template_label": display_label or (template.label if template else key),
            "template_available": template.available if template else False,
            "rag_backend": template.rag_backend if template else settings.RAG_BACKEND,
            "app_id": db_app or None,
            "base_url": (row.base_url or "").strip() if row and row.base_url else None,
            "effective_app_id": app_id or None,
            "api_secret_masked": masked or None,
            "has_stored_secret": has_db_secret,
            "configured": configured,
            "admin_configured": self.credential_source(key) == "database",
            "credential_source": self.credential_source(key),
            "wiki_filter_score": float(
                row.wiki_filter_score if row and row.wiki_filter_score is not None else wiki_default
            ),
            "pipeline_config_json": parse_pipeline_config_json(row.pipeline_config_json)
            if row and row.pipeline_config_json
            else None,
            "icon_file": (row.icon_file or "").strip() if row and row.icon_file else None,
            "is_active": row.is_active if row else True,
            "last_test_status": row.last_test_status if row else None,
            "last_test_message": row.last_test_message if row else None,
            "last_tested_at": row.last_tested_at.isoformat() if row and row.last_tested_at else None,
            "env_fallback_hint": template.env_fallback_hint if template else "",
            "credential_env_vars": {
                field.key: credential_env_var_name(template.env_prefix, field.key, field)
                for field in template.credential_fields
                if credential_env_var_name(template.env_prefix, field.key, field)
            }
            if template
            else {},
            "docs_url": template.docs_url if template else None,
            "available_templates": [
                {
                    "key": item.key,
                    "label": item.label,
                    "rag_backend": item.rag_backend,
                    "available": item.available,
                }
                for item in list_integration_templates().items
            ],
            "vendor_quota": quota_view.model_dump() if quota_view else None,
        }

    def list_gateway_instances(self) -> dict:
        """列出已加入网关列表的接入实例。

        参数：
            无。

        返回：
            包含实例列表、数量和当前激活实例 key 的字典。

        副作用与失败模式：
            仅查询数据库并复用管理视图构造逻辑；数据库或视图构造失败时可能抛出异常。
        """
        active_key = self.active_template_key()
        rows = self.db.execute(
            select(RagIntegrationConfig).where(
                RagIntegrationConfig.integration_key != ACTIVE_SELECTION_KEY,
                RagIntegrationConfig.gateway_listed.is_(True),
            )
        ).scalars().all()
        items: list[dict] = []
        for row in rows:
            view = self.get_admin_view(row.integration_key)
            view["gateway_listed"] = True
            items.append(view)
        return {
            "items": items,
            "total": len(items),
            "active_integration_key": active_key,
        }

    def register_gateway_integration(
        self,
        template_key: str,
        *,
        actor_external_id: str | None = None,
    ) -> dict:
        """将模板注册为可在网关中使用的接入实例。

        参数：
            template_key: 要注册的模板或实例 key。
            actor_external_id: 执行操作的外部用户标识，用于记录审计信息。

        返回：
            包含注册状态和管理端视图的字典。

        副作用与失败模式：
            会创建或更新配置行、初始化供应商余量行、写入审计日志并提交事务；模板不存在时抛出 ValueError。
        """
        key = normalize_template_key(template_key)
        template = get_template(key)
        if template is None:
            raise ValueError(f"未知接入模板：{key}")
        row = self._ensure_row(key)
        already = bool(row.gateway_listed)
        row.gateway_listed = True
        if actor_external_id:
            row.updated_by_external_id = actor_external_id
        if self.supports_vendor_quota(key):
            try:
                ChatdocVendorQuotaService(self.db).ensure_for_integration(key)
            except ChatdocVendorQuotaNotReadyError:
                logger.debug("ChatDoc 供应商余量表未就绪，跳过模板配额初始化：template_key=%s", key, exc_info=True)
            except Exception:
                logger.warning(
                    "初始化 ChatDoc 供应商配额失败，管理端供应商余量可能缺少初始记录：template_key=%s",
                    key,
                    exc_info=True,
                )
        self._audit(
            actor_external_id,
            {"template_key": key, "registered": True, "already_listed": already},
        )
        self.db.commit()
        status = "already_registered" if already else "registered"
        return {**{"status": status}, **self.get_admin_view(key)}

    def upsert(self, payload: ChatdocConfigUpsert, *, actor_external_id: str | None = None) -> dict:
        """新增或更新 ChatDoc 接入实例配置。

        参数：
            payload: 管理端提交的接入配置，包含模板、凭证、展示名称、流水线配置和激活状态。
            actor_external_id: 执行操作的外部用户标识，用于记录审计信息。

        返回：
            包含保存状态和更新后管理端视图的字典。

        副作用与失败模式：
            会写入配置、加密保存密钥、记录审计日志并提交事务；缺少 integration_key 或模板不存在时抛出 ValueError。
        """
        instance_key = (payload.integration_key or "").strip()
        if not instance_key:
            raise ValueError("integration_key is required")
        preset_key = normalize_template_key(payload.preset_template_key or instance_key)
        template = get_template(preset_key)
        if template is None:
            raise ValueError(f"未知接入模板：{preset_key}")
        row = self._ensure_row(instance_key, preset_template_key=preset_key)
        row.preset_template_key = preset_key
        row.gateway_listed = True
        if payload.display_label is not None:
            row.display_label = payload.display_label.strip() or None
        if payload.app_id is not None:
            row.app_id = payload.app_id.strip() or None
        if payload.base_url is not None:
            row.base_url = payload.base_url.strip() or None
        if payload.clear_api_secret:
            row.api_secret_encrypted = None
        elif payload.api_secret:
            row.api_secret_encrypted = encrypt_secret(payload.api_secret.strip())
        if payload.wiki_filter_score is not None:
            row.wiki_filter_score = payload.wiki_filter_score
        if payload.pipeline_config_json is not None:
            row.pipeline_config_json = serialize_pipeline_config_json(payload.pipeline_config_json)
        if payload.is_active is not None:
            row.is_active = payload.is_active
        if payload.icon_file is not None:
            row.icon_file = payload.icon_file.strip() or None
        if payload.set_active:
            self.set_active_template_key(instance_key)
        if actor_external_id:
            row.updated_by_external_id = actor_external_id
        self._audit(
            actor_external_id,
            {
                "integration_key": instance_key,
                "preset_template_key": preset_key,
                "app_id": row.app_id,
                "has_secret": bool(row.api_secret_encrypted),
            },
        )
        self.db.commit()
        return {"status": "saved", **self.get_admin_view(instance_key)}

    def delete_config(self, instance_key: str, *, actor_external_id: str | None = None) -> dict:
        """删除指定接入实例的配置记录。

        参数：
            instance_key: 要删除的接入实例 key。
            actor_external_id: 执行操作的外部用户标识，用于记录审计信息。

        返回：
            包含删除状态、是否实际删除和删除后管理端视图的字典。

        副作用与失败模式：
            会删除匹配的新旧存储 key 配置行、可选写入审计日志并提交事务；删除激活选择记录时抛出 ValueError。
        """
        key = (instance_key or "").strip()
        if not key or key == ACTIVE_SELECTION_KEY:
            raise ValueError("不能删除当前激活选择记录")
        removed = False
        for storage_key in {key, self._legacy_storage_key(key)}:
            if not storage_key:
                continue
            row = self.db.execute(
                select(RagIntegrationConfig).where(RagIntegrationConfig.integration_key == storage_key)
            ).scalar_one_or_none()
            if row is not None:
                self.db.delete(row)
                removed = True
        if actor_external_id:
            self._audit(actor_external_id, {"template_key": key, "deleted": removed})
        self.db.commit()
        return {"status": "deleted", "removed": removed, **self.get_admin_view(key)}

    def _resolve_credentials_for_test(
        self,
        instance_key: str,
        draft: ChatdocConfigUpsert | None = None,
    ) -> tuple[str, str]:
        preset_key = self._preset_key_for_instance(instance_key)
        if draft is not None and draft.preset_template_key:
            preset_key = normalize_template_key(draft.preset_template_key)
        template = get_template(preset_key)
        row = self._row(instance_key)
        db_app_id = ""
        db_secret = ""

        if draft is not None and draft.app_id is not None:
            db_app_id = draft.app_id.strip()
        elif row:
            db_app_id = (row.app_id or "").strip()

        if draft is not None and draft.clear_api_secret:
            db_secret = ""
        elif draft is not None and draft.api_secret:
            db_secret = draft.api_secret.strip()
        elif row and row.api_secret_encrypted:
            db_secret = (decrypt_secret(row.api_secret_encrypted) or "").strip()

        merged = merge_db_and_env_credentials(template, app_id=db_app_id, api_secret=db_secret)
        return resolve_app_id_and_secret(template, merged)

    async def test_connection(
        self,
        *,
        actor_external_id: str | None = None,
        template_key: str | None = None,
        draft: ChatdocConfigUpsert | None = None,
    ) -> dict:
        """测试指定或草稿接入实例的 ChatDoc 连接。

        参数：
            actor_external_id: 执行测试的外部用户标识，用于持久化测试结果时记录操作者。
            template_key: 要测试的模板或实例 key；draft 未指定实例时使用该值。
            draft: 未保存的草稿配置，用于测试临时凭证且默认不持久化测试结果。

        返回：
            包含测试状态、提示消息和管理端视图的字典。

        副作用与失败模式：
            会调用供应商探测接口；非草稿测试会写入测试结果。异常会回滚事务并转换为失败响应。
        """
        if draft and draft.integration_key:
            key = normalize_template_key(draft.integration_key)
        elif template_key:
            key = normalize_template_key(template_key)
        else:
            key = self.active_template_key()
        persist_result = draft is None
        try:
            return await self._test_connection_impl(
                key=key,
                draft=draft,
                actor_external_id=actor_external_id,
                persist_result=persist_result,
            )
        except Exception as exc:  # pragma: no cover - 异常会转换为管理端连接测试结果。
            self.db.rollback()
            message = str(exc).strip() or "连接测试失败"
            logger.warning(
                "ChatDoc 连接测试执行失败，将返回失败视图：template_key=%s actor=%s persist_result=%s",
                key,
                actor_external_id,
                persist_result,
                exc_info=True,
            )
            return self._test_failure_payload(
                key,
                message,
                actor_external_id=actor_external_id,
                persist=False,
            )

    async def _test_connection_impl(
        self,
        *,
        key: str,
        draft: ChatdocConfigUpsert | None,
        actor_external_id: str | None,
        persist_result: bool,
    ) -> dict:
        preset_key = self._preset_key_for_instance(key)
        if draft is not None and draft.preset_template_key:
            preset_key = normalize_template_key(draft.preset_template_key)
        template = get_template(preset_key)
        if template is None:
            return self._record_test(
                template_key=key,
                status="failed",
                message=f"未知接入模板：{preset_key}",
                actor_external_id=actor_external_id,
                persist=persist_result,
            )
        if not template.available:
            hint = str((template.meta_json or {}).get("coming_soon_hint") or "该模板后端尚未接入。")
            return self._record_test(
                template_key=key,
                status="failed",
                message=hint,
                actor_external_id=actor_external_id,
                persist=persist_result,
            )
        if template.rag_backend != "iflytek_chatdoc":
            return self._record_test(
                template_key=key,
                status="failed",
                message="当前仅支持讯飞 ChatDoc 模板的连接测试。",
                actor_external_id=actor_external_id,
                persist=persist_result,
            )
        app_id, api_secret = self._resolve_credentials_for_test(key, draft)
        client = IflytekChatDocClient(app_id=app_id, api_secret=api_secret)
        if not client.configured:
            return self._record_test(
                template_key=key,
                status="failed",
                message="AppId 或 APISecret 未配置（管理端与 .env 均为空）",
                actor_external_id=actor_external_id,
                persist=persist_result,
            )
        try:
            await client.probe_connection()
            outcome = ("passed", "讯飞 ChatDoc 鉴权通过，文件列表接口可用")
        except IflytekChatDocError as exc:
            outcome = ("failed", exc.vendor_raw)
        return self._record_test(
            status=outcome[0],
            message=outcome[1],
            actor_external_id=actor_external_id,
            template_key=key,
            persist=persist_result,
        )

    def _safe_get_admin_view(self, template_key: str) -> dict:
        try:
            return dict(self.get_admin_view(template_key))
        except Exception as exc:  # pragma: no cover - 数据库或视图失败时保持测试 API 可用。
            logger.warning(
                "读取 ChatDoc 管理视图失败，将返回最小兜底视图：template_key=%s",
                template_key,
                exc_info=True,
            )
            template = get_template(template_key)
            return {
                "integration_key": template_key,
                "template_key": template_key,
                "template_label": template.label if template else template_key,
                "template_available": template.available if template else False,
                "rag_backend": template.rag_backend if template else settings.RAG_BACKEND,
                "configured": False,
                "credential_source": "none",
                "has_stored_secret": False,
                "is_active": True,
                "env_fallback_hint": template.env_fallback_hint if template else "",
                "view_error": str(exc),
            }

    def _test_failure_payload(
        self,
        template_key: str,
        message: str,
        *,
        actor_external_id: str | None = None,
        persist: bool = False,
    ) -> dict:
        key = normalize_template_key(template_key)
        tested_at = datetime.now(timezone.utc)
        if persist:
            try:
                row = self._ensure_row(key)
                row.last_test_status = "failed"
                row.last_test_message = message[:2000]
                row.last_tested_at = tested_at
                if actor_external_id:
                    row.updated_by_external_id = actor_external_id
                self.db.commit()
            except Exception:
                logger.warning(
                    "记录 ChatDoc 连接测试失败状态失败：template_key=%s actor=%s",
                    key,
                    actor_external_id,
                    exc_info=True,
                )
                self.db.rollback()
        view = self._safe_get_admin_view(key)
        view["last_test_status"] = "failed"
        view["last_test_message"] = message
        view["last_tested_at"] = tested_at.isoformat()
        return {"status": "failed", "message": message, **view}

    def build_test_failure_payload(
        self,
        template_key: str,
        message: str,
        *,
        actor_external_id: str | None = None,
        persist: bool = False,
    ) -> dict:
        """构造 ChatDoc 连接测试失败响应。

        参数：
            template_key: 发生失败的模板或实例 key。
            message: 返回给管理端的失败说明。
            actor_external_id: 执行操作的外部用户标识，用于可选持久化时记录操作者。
            persist: 是否把失败状态写入数据库。

        返回：
            包含失败状态、失败消息和管理端兜底视图的字典。

        副作用与失败模式：
            persist 为 True 时会尝试写入连接测试失败状态；写入失败会回滚并继续返回兜底失败视图。
        """
        return self._test_failure_payload(
            template_key,
            message,
            actor_external_id=actor_external_id,
            persist=persist,
        )

    def _record_test(
        self,
        *,
        status: str,
        message: str,
        actor_external_id: str | None,
        template_key: str | None = None,
        persist: bool = True,
    ) -> dict:
        key = normalize_template_key(template_key) if template_key else self.active_template_key()
        tested_at = datetime.now(timezone.utc)
        if persist:
            try:
                row = self._ensure_row(key)
                row.last_test_status = status
                row.last_test_message = message[:2000]
                row.last_tested_at = tested_at
                if actor_external_id:
                    row.updated_by_external_id = actor_external_id
                self.db.commit()
            except Exception as exc:
                self.db.rollback()
                logger.warning(
                    "保存 ChatDoc 连接测试结果失败：template_key=%s status=%s actor=%s",
                    key,
                    status,
                    actor_external_id,
                    exc_info=True,
                )
                return self._test_failure_payload(
                    key,
                    f"保存测试结果失败：{exc}",
                    actor_external_id=actor_external_id,
                    persist=False,
                )
        view = self._safe_get_admin_view(key)
        view["last_test_status"] = status
        view["last_test_message"] = message
        view["last_tested_at"] = tested_at.isoformat()
        return {"status": status, "message": message, **view}

    def _audit(self, actor_external_id: str | None, detail: dict) -> None:
        actor_id = None
        if actor_external_id:
            actor = self.db.execute(select(User).where(User.external_id == actor_external_id)).scalar_one_or_none()
            actor_id = actor.id if actor else None
        self.db.add(
            AdminAuditLog(
                actor_user_id=actor_id,
                action="chatdoc_config.update",
                target_type="rag_integration",
                target_id=detail.get("template_key", self.active_template_key()),
                detail_json=detail,
            )
        )

    def supports_vendor_quota(self, instance_key: str | None) -> bool:
        """判断指定接入实例是否支持讯飞 ChatDoc 套餐余量。

        参数：
            instance_key: 接入实例 key；为空时使用当前激活实例。

        返回：
            支持供应商余量展示时返回 True，否则返回 False。

        副作用与失败模式：
            仅读取模板和配置，不修改状态；数据库读取失败时可能抛出异常。
        """
        preset_key = self._preset_key_for_instance(instance_key or self.active_template_key())
        template = get_template(preset_key)
        return template is not None and template.rag_backend == "iflytek_chatdoc"
