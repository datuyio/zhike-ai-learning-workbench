#!/usr/bin/env bash
set -euo pipefail

echo "启动智课未来开发环境"
echo "1) backend:  cd backend && uvicorn app.main:app --reload --port 8001"
echo "2) frontend: cd frontend && pnpm dev"
