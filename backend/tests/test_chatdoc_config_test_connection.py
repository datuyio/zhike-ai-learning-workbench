"""验证新增供应商草稿的“测试连接”能正确解析预置模板。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.chatdoc_config import ChatdocConfigUpsert
from app.services.knowledge.iflytek.config_service import ChatdocConfigService


def test_draft_test_connection_uses_preset_template_key() -> None:
    """随机实例 key 必须通过 preset_template_key 找到讯飞模板。"""
    db = MagicMock()
    service = ChatdocConfigService(db)
    service._row = MagicMock(return_value=None)
    service._record_test = MagicMock(return_value={"status": "recorded"})
    draft = ChatdocConfigUpsert(
        integration_key="iflytek-chatdoc-verify-001",
        preset_template_key="iflytek-chatdoc",
        app_id="test-app-id",
        api_secret="test-api-secret",
        base_url="https://chatdoc.xfyun.cn",
        is_active=True,
    )

    async def run() -> None:
        with patch("app.services.knowledge.iflytek.config_service.IflytekChatDocClient") as client_cls:
            client_cls.return_value.probe_connection = AsyncMock()
            await service._test_connection_impl(
                key=draft.integration_key,
                draft=draft,
                actor_external_id="test-user",
                persist_result=False,
            )
            client_cls.assert_called_once_with(app_id="test-app-id", api_secret="test-api-secret")

    asyncio.run(run())
    service._record_test.assert_called_once()
    message = service._record_test.call_args.kwargs["message"]
    assert "未知接入模板" not in message
