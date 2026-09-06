#!/usr/bin/env bash
# 生产构建前端（Linux / macOS）
# 子路径前缀取自 frontend/.env.production 的 VITE_BASE_PATH（当前 /zhike/），产物输出到 frontend/dist/
set -euo pipefail
cd "$(dirname "$0")/../frontend"
pnpm build
echo "构建完成: $(pwd)/dist"
