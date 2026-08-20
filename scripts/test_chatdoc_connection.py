"""读取 backend/.env 中的 ChatDoc 凭据并测试讯飞接口连通性。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path


BACKEND_ENV = Path(__file__).resolve().parents[1] / "backend" / ".env"


def load_chatdoc_env() -> None:
    """把 ChatDoc 相关环境变量载入当前进程，避免重复明文传参。"""
    if not BACKEND_ENV.exists():
        return
    for line in BACKEND_ENV.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.startswith("IFLYTEK_CHATDOC_"):
            os.environ[key] = value.strip()


async def main() -> None:
    """调用 ChatDoc 文件列表接口验证鉴权。"""
    load_chatdoc_env()
    from app.services.knowledge.iflytek.client import IflytekChatDocClient

    app_id = os.getenv("IFLYTEK_CHATDOC_APP_ID", "")
    api_secret = os.getenv("IFLYTEK_CHATDOC_API_SECRET", "")
    client = IflytekChatDocClient(app_id=app_id, api_secret=api_secret)
    result = await client.probe_connection()
    total = result.get("total")
    items = result.get("list") or result.get("records") or []
    print(f"连接成功：AppId={app_id[:4]}****，总文件数={total}，首屏条数={len(items)}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001 - 测试脚本统一输出错误摘要
        print(f"连接失败：{type(exc).__name__}: {exc}")
        raise SystemExit(1)
