"""对比 ChatDoc 鉴权头字段名，定位 405 Invalid Signature 的根因。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx


BACKEND_ENV = Path(__file__).resolve().parents[1] / "backend" / ".env"


def load_chatdoc_env() -> None:
    """把 ChatDoc 相关环境变量载入当前进程。"""
    if not BACKEND_ENV.exists():
        return
    for line in BACKEND_ENV.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.startswith("IFLYTEK_CHATDOC_"):
            os.environ[key] = value.strip()


async def probe_once(headers: dict[str, str], method: str) -> tuple[int, str]:
    """按给定请求头发起一次文件列表请求。"""
    url = "https://chatdoc.xfyun.cn/openapi/v1/file/list"
    headers = {**headers, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=20) as client:
        if method == "POST":
            response = await client.post(url, headers=headers, json={"currentPage": 1, "pageSize": 1})
        else:
            response = await client.get(url, headers=headers)
    return response.status_code, response.text[:200]


async def main() -> None:
    """对比官方 timeStamp 与项目 timestamp 两种字段名。"""
    load_chatdoc_env()
    from app.services.knowledge.iflytek.chatdoc_auth import chatdoc_auth_headers

    app_id = os.getenv("IFLYTEK_CHATDOC_APP_ID", "")
    api_secret = os.getenv("IFLYTEK_CHATDOC_API_SECRET", "")
    base = chatdoc_auth_headers(app_id, api_secret)
    official = {"appId": base["appId"], "timeStamp": base["timestamp"], "signature": base["signature"]}
    legacy = dict(base)

    for label, headers, method in [
        ("官方 timeStamp POST", official, "POST"),
        ("项目 timestamp POST", legacy, "POST"),
        ("官方 timeStamp GET", official, "GET"),
        ("项目 timestamp GET", legacy, "GET"),
    ]:
        status, body = await probe_once(headers, method)
        print(f"{label}: HTTP {status} {body}")


if __name__ == "__main__":
    asyncio.run(main())
