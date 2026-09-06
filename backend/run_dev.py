"""本地开发启动（Windows 友好：限制 reload 目录、防抖，减少 WatchFiles 连续重载崩溃）。"""
from __future__ import annotations

import sys

import uvicorn

from app.core.config import load_project_env

# 开发入口同样注入 .env，保证 reload 主进程环境完整
load_project_env()

if __name__ == "__main__":
    reload_delay = 1.0 if sys.platform == "win32" else 0.5
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        reload_dirs=["."],
        reload_delay=reload_delay,
        reload_includes=["*.py", "*.yaml", "*.yml", "*.toml", "*.env", "*.json"],
        reload_excludes=[
            "*.pyc",
            "*.log",
            "__pycache__",
            "__pycache__/*",
            ".venv",
            ".venv/*",
            "venv",
            "venv/*",
            ".pytest_cache",
            ".pytest_cache/*",
            ".pytest-deps",
            ".pytest-deps/*",
            ".pytest-runtime-cache",
            ".pytest-runtime-cache/*",
            ".pytest-runtime-tmp",
            ".pytest-runtime-tmp/*",
            ".pytest-tmp",
            ".pytest-tmp/*",
            "storage",
            "storage/*",
            "alembic/versions/__pycache__",
            "alembic/versions/__pycache__/*",
            "tests",
            "tests/*",
        ],
    )
