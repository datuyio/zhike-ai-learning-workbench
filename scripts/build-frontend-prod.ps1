# 生产构建前端（Windows / PowerShell）
# 子路径前缀取自 frontend/.env.production 的 VITE_BASE_PATH（当前 /zhike/），产物输出到 frontend/dist/
$ErrorActionPreference = "Stop"
$frontend = Join-Path $PSScriptRoot "..\frontend"
Push-Location $frontend
try {
    corepack pnpm build
    Write-Host "构建完成: $frontend\dist"
} finally {
    Pop-Location
}
