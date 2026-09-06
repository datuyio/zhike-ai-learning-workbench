# 页面预览模式：只启动前端，并强制使用 Mock 数据。
# 用法：在项目根目录执行 powershell -ExecutionPolicy Bypass -File scripts/start-frontend-mock.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "logs"

function Test-PortListening([int]$Port) {
    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
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

Write-Host "==> 启动智课未来页面预览模式..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not (Test-Path (Join-Path $Root "frontend\node_modules"))) {
    Write-Error "未找到前端依赖 node_modules，请先运行 scripts/install-deps.ps1。"
}

$corepack = Get-CommandPath -Names @("corepack.cmd", "corepack.exe", "corepack")
if (-not $corepack) {
    Write-Error "未找到 corepack，请先安装 Node.js 16.10+。"
}

$env:COREPACK_HOME = Join-Path $Root ".cache\corepack"
$env:COREPACK_NPM_REGISTRY = "https://registry.npmmirror.com"
New-Item -ItemType Directory -Force -Path $env:COREPACK_HOME | Out-Null

if (Test-PortListening 5173) {
    Write-Host "前端端口 5173 已在运行，直接访问即可。" -ForegroundColor Yellow
} else {
    $frontendLog = Join-Path $LogDir "frontend-mock.log"
    $frontendCommand = "set VITE_USE_MOCKS=true&& set COREPACK_HOME=$env:COREPACK_HOME&& `"$corepack`" pnpm dev --host 0.0.0.0 > `"$frontendLog`" 2>&1"
    Start-Process cmd.exe -WorkingDirectory (Join-Path $Root "frontend") -WindowStyle Hidden `
        -ArgumentList @("/d", "/s", "/c", $frontendCommand)
}

Write-Host ""
Write-Host "页面预览已启动：" -ForegroundColor Green
Write-Host "  登录页: http://localhost:5173/login?mock=1" -ForegroundColor White
Write-Host "  学生工作台: http://localhost:5173/dashboard?mock=1" -ForegroundColor White
Write-Host "  管理后台: http://localhost:5173/admin/knowledge-base?mock=1" -ForegroundColor White
Write-Host "  前端日志: logs/frontend-mock.log" -ForegroundColor White

