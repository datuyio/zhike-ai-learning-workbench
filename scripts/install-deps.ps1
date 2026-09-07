# 使用国内镜像安装前后端依赖（前端：淘宝 npmmirror；后端：清华 PyPI）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Get-CommandPath([string[]]$Names) {
  foreach ($name in $Names) {
    $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) {
      return $command.Source
    }
  }
  return $null
}

function Get-Python312Command {
  $pythonLauncher = Get-CommandPath -Names @("py.exe", "py")
  if ($pythonLauncher) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
      & $pythonLauncher -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" *> $null
      $probeExitCode = $LASTEXITCODE
    } finally {
      $ErrorActionPreference = $previousPreference
    }
    if ($probeExitCode -eq 0) {
      return @{ Command = $pythonLauncher; Args = @("-3.12") }
    }
  }

  $python = Get-CommandPath -Names @("python.exe", "python")
  if ($python) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
      & $python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" *> $null
      $probeExitCode = $LASTEXITCODE
    } finally {
      $ErrorActionPreference = $previousPreference
    }
    if ($probeExitCode -eq 0) {
      return @{ Command = $python; Args = @() }
    }
  }

  return $null
}

function Invoke-Python([hashtable]$PythonCommand, [string[]]$Arguments) {
  $command = $PythonCommand["Command"]
  $baseArgs = $PythonCommand["Args"]
  & $command @($baseArgs + $Arguments)
}

Write-Host "==> Backend: 检查 Python 3.12" -ForegroundColor Cyan
$pythonCommand = Get-Python312Command
if (-not $pythonCommand) {
  throw "未找到 Python 3.12。请安装 Python 3.12 后重新运行本脚本；项目后端要求 3.12.x。"
}

Write-Host "==> Frontend: corepack + pnpm install" -ForegroundColor Cyan
$corepack = Get-CommandPath -Names @("corepack.cmd", "corepack.exe", "corepack")
if (-not $corepack) {
  throw "未找到 corepack，请先安装 Node.js 16.10+。"
}
$env:COREPACK_HOME = Join-Path $Root ".cache\corepack"
$env:COREPACK_NPM_REGISTRY = "https://registry.npmmirror.com"
New-Item -ItemType Directory -Force -Path $env:COREPACK_HOME | Out-Null
Push-Location (Join-Path $Root "frontend")
try {
  & $corepack prepare pnpm@11.9.0 --activate
  if ($LASTEXITCODE -ne 0) {
    throw "pnpm 准备失败，请检查网络或 npm 镜像访问。"
  }
  & $corepack pnpm install
  if ($LASTEXITCODE -ne 0) {
    throw "前端依赖安装失败。"
  }
} finally {
  Pop-Location
}

Write-Host "==> Backend: 创建/修复 .venv 并安装依赖" -ForegroundColor Cyan
$backendDir = Join-Path $Root "backend"
$venvDir = Join-Path $backendDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
  Invoke-Python -PythonCommand $pythonCommand -Arguments @("-m", "venv", $venvDir)
}

$env:PIP_CONFIG_FILE = Join-Path $backendDir "pip.conf"
Push-Location $backendDir
try {
  & $venvPython -m pip install -U pip
  if ($LASTEXITCODE -ne 0) {
    throw "pip 自升级失败。"
  }
  & $venvPython -m pip install -r requirements.txt
  if ($LASTEXITCODE -ne 0) {
    throw "后端依赖安装失败。"
  }
} finally {
  Pop-Location
  Remove-Item Env:PIP_CONFIG_FILE -ErrorAction SilentlyContinue
}

Write-Host "依赖安装完成。" -ForegroundColor Green
