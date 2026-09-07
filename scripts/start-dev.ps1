# 一键启动智课未来开发环境（后端 8001 + 前端 5173 + 代码沙箱 8003）
# 用法：在项目根目录执行 powershell -ExecutionPolicy Bypass -File scripts/start-dev.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "logs"

function Test-PortListening([int]$Port) {
    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Test-PythonRunnable([string]$PythonPath) {
    if (-not (Test-Path $PythonPath)) {
        return $false
    }
    & $PythonPath --version *> $null
    return $LASTEXITCODE -eq 0
}

function Resolve-BackendPython {
    $candidates = @(
        (Join-Path $Root "backend\.venv\Scripts\python.exe"),
        (Join-Path $Root "backend\venv\Scripts\python.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-PythonRunnable $candidate) {
            return $candidate
        }
    }
    return $null
}

function Get-CommandPath([string[]]$Names) {
    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) {
            return $command.Source
        }
    }
    return $null
}

Write-Host "==> 检查环境..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not (Test-Path (Join-Path $Root ".env"))) {
    Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env")
    Write-Warning "未找到 .env，已从 .env.example 复制。请按需填写模型 API Key。"
}

# 检查数据库端口（本机 PostgreSQL 默认 5432）
if (-not (Test-PortListening 5432)) {
    $postgresService = Get-Service "*postgres*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($postgresService -and $postgresService.Status -ne "Running") {
        Write-Host "检测到 PostgreSQL 服务 $($postgresService.Name)，尝试启动..." -ForegroundColor Yellow
        Start-Service $postgresService.Name
        Start-Sleep -Seconds 3
    }
}
if (-not (Test-PortListening 5432)) {
    Write-Error "PostgreSQL(5432) 未监听。请先安装并启动 PostgreSQL 16/17，或启动 docker compose 中的 postgres 服务。"
}

# 检查后端虚拟环境
$venvPython = Resolve-BackendPython
if (-not $venvPython) {
    Write-Error "未找到可运行的后端 Python 虚拟环境。请先运行：powershell -ExecutionPolicy Bypass -File scripts/install-deps.ps1"
}

# 检查前端依赖
if (-not (Test-Path (Join-Path $Root "frontend\node_modules"))) {
    Write-Error "未找到前端依赖 node_modules`n请先运行 scripts/install-deps.ps1 安装依赖。"
}

$corepack = Get-CommandPath -Names @("corepack.cmd", "corepack.exe", "corepack")
if (-not $corepack) {
    Write-Error "未找到 corepack，请先安装 Node.js 16.10+。"
}
$env:COREPACK_HOME = Join-Path $Root ".cache\corepack"
New-Item -ItemType Directory -Force -Path $env:COREPACK_HOME | Out-Null

# 启动前先执行迁移，确保管理员种子账号和最新表结构可用。
Write-Host "==> 同步数据库迁移..." -ForegroundColor Cyan
Push-Location (Join-Path $Root "backend")
try {
    & $venvPython -m alembic upgrade head
} finally {
    Pop-Location
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
    $backendLog = Join-Path $LogDir "backend.log"
    $backendCommand = "& `"$venvPython`" `"run_dev.py`" *> `"$backendLog`""
    Start-Process powershell -WorkingDirectory (Join-Path $Root "backend") -WindowStyle Hidden `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand)
}

# 启动前端
if (Test-PortListening 5173) {
    Write-Host "前端端口 5173 已被占用，可能已在运行，跳过启动。" -ForegroundColor Yellow
} else {
    Write-Host "==> 启动前端 (http://localhost:5173)" -ForegroundColor Green
    $frontendLog = Join-Path $LogDir "frontend.log"
    $frontendCommand = "& `"$corepack`" pnpm dev --host 0.0.0.0 *> `"$frontendLog`""
    Start-Process powershell -WorkingDirectory (Join-Path $Root "frontend") -WindowStyle Hidden `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand)
}

Write-Host ""
Write-Host "智课未来开发环境启动完成：" -ForegroundColor Green
Write-Host "  前端页面: http://localhost:5173" -ForegroundColor White
Write-Host "  后端 API: http://localhost:8001" -ForegroundColor White
Write-Host "  代码沙箱: http://127.0.0.1:8003/health" -ForegroundColor White
Write-Host "  API 文档: http://localhost:8001/docs" -ForegroundColor White
Write-Host "  后端日志: logs/backend.log" -ForegroundColor White
Write-Host "  前端日志: logs/frontend.log" -ForegroundColor White
