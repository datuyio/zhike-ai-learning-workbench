# 一键启动智课工坊开发环境（后端 8001 + 前端 5173 + 代码沙箱 8003）
# 用法：在项目根目录执行 powershell -ExecutionPolicy Bypass -File scripts/start-dev.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Test-PortListening([int]$Port) {
    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

Write-Host "==> 检查环境..." -ForegroundColor Cyan

# 检查数据库端口（本机 PostgreSQL 默认 5432）
if (-not (Test-PortListening 5432)) {
    Write-Warning "PostgreSQL(5432) 未监听。请先启动本机 PostgreSQL 服务，再运行本脚本。"
    Write-Host "  可尝试命令：Start-Service postgresql-x64-17" -ForegroundColor Yellow
}

# 检查后端虚拟环境
$venvPython = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "未找到后端虚拟环境：$venvPython`n请先运行 scripts/install-deps.ps1 安装依赖。"
}

# 检查前端依赖
if (-not (Test-Path (Join-Path $Root "frontend\node_modules"))) {
    Write-Error "未找到前端依赖 node_modules`n请先运行 scripts/install-deps.ps1 安装依赖。"
}

# 检查代码沙箱依赖与启动状态，有依赖时自动拉起 8003 微服务
$sandboxDir = Join-Path $Root "backend\sandbox-service"
if (-not (Test-Path (Join-Path $sandboxDir "node_modules"))) {
    Write-Warning "代码沙箱依赖未安装，请先在 backend\sandbox-service 执行 npm install；本次跳过沙箱启动。"
} elseif (Test-PortListening 8003) {
    Write-Host "代码沙箱端口 8003 已被占用，可能已在运行，跳过启动。" -ForegroundColor Yellow
} else {
    Write-Host "==> 启动代码沙箱 (http://127.0.0.1:8003)" -ForegroundColor Green
    Start-Process node -WorkingDirectory $sandboxDir -ArgumentList "server.js" -WindowStyle Hidden
}

# 启动后端
if (Test-PortListening 8001) {
    Write-Host "后端端口 8001 已被占用，可能已在运行，跳过启动。" -ForegroundColor Yellow
} else {
    Write-Host "==> 启动后端 (http://localhost:8001)" -ForegroundColor Green
    Start-Process powershell -WorkingDirectory (Join-Path $Root "backend") `
        -ArgumentList @("-NoExit", "-Command", "& '.venv\Scripts\python.exe' 'run_dev.py'")
}

# 启动前端
if (Test-PortListening 5173) {
    Write-Host "前端端口 5173 已被占用，可能已在运行，跳过启动。" -ForegroundColor Yellow
} else {
    Write-Host "==> 启动前端 (http://localhost:5173)" -ForegroundColor Green
    Start-Process powershell -WorkingDirectory (Join-Path $Root "frontend") `
        -ArgumentList @("-NoExit", "-Command", "corepack pnpm dev")
}

Write-Host ""
Write-Host "智课工坊开发环境启动完成：" -ForegroundColor Green
Write-Host "  前端页面: http://localhost:5173" -ForegroundColor White
Write-Host "  后端 API: http://localhost:8001" -ForegroundColor White
Write-Host "  代码沙箱: http://127.0.0.1:8003/health" -ForegroundColor White
Write-Host "  API 文档: http://localhost:8001/docs" -ForegroundColor White
Write-Host "按 Ctrl+C 可在各自窗口中停止对应服务。" -ForegroundColor DarkGray
