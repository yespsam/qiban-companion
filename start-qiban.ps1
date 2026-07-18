$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "ai-companion\project"
$RunDir = Join-Path $Root ".run"
$StaticPort = if ($env:QIBAN_STATIC_PORT) { [int]$env:QIBAN_STATIC_PORT } else { 8765 }
$ApiPort = if ($env:QIBAN_API_PORT) { [int]$env:QIBAN_API_PORT } else { 8766 }
$BindHost = if ($env:QIBAN_HOST) { $env:QIBAN_HOST } else { "127.0.0.1" }

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

function Invoke-BasePython {
  param([string[]]$Args)
  if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 @Args
  } else {
    & python @Args
  }
}

function Stop-Port {
  param([int]$Port)
  try {
    $processIds = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $processIds) {
      if ($processId -and $processId -ne $PID) {
        Write-Host "重启 $Port 端口上的旧服务..."
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
      }
    }
  } catch {
  }
}

function Wait-Http {
  param([string]$Url)
  for ($i = 0; $i -lt 90; $i++) {
    try {
      $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
      if ($response.StatusCode -lt 500) { return }
    } catch {
    }
    Start-Sleep -Milliseconds 500
  }
  throw "等待服务超时：$Url"
}

function Test-PythonImports {
  param([string]$PythonExe)
  & $PythonExe -c "import yaml, fastapi, uvicorn, edge_tts" *> $null
  return $LASTEXITCODE -eq 0
}

function Stop-QibanProcesses {
  param($BackendProcess, $StaticProcess)
  foreach ($process in @($BackendProcess, $StaticProcess)) {
    if ($process -and -not $process.HasExited) {
      Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
  }
}

Write-Host "栖伴正在启动..."

try {
  Invoke-BasePython @("--version")
  if ($LASTEXITCODE -ne 0) { throw "Python 不可用" }
} catch {
  Write-Host "未找到 Python。请先安装 Python 3.10+，并勾选 Add python.exe to PATH。"
  exit 1
}

if ($env:QIBAN_REUSE_PORTS -ne "1") {
  Stop-Port $ApiPort
  Stop-Port $StaticPort
}

$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  Push-Location $Backend
  Invoke-BasePython @("-m", "venv", ".venv")
  Pop-Location
}

if (-not (Test-PythonImports $VenvPython)) {
  Push-Location $Backend
  & $VenvPython -m pip install -U pip
  & $VenvPython -m pip install -r requirements-core.txt edge-tts
  Pop-Location
}

$backendOut = Join-Path $RunDir "backend.log"
$backendErr = Join-Path $RunDir "backend.err.log"
$staticOut = Join-Path $RunDir "static.log"
$staticErr = Join-Path $RunDir "static.err.log"

$oldPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = $Backend
$backendProcess = Start-Process -FilePath $VenvPython `
  -ArgumentList @("run.py", "--ui", "web", "--host", $BindHost, "--port", "$ApiPort") `
  -WorkingDirectory $Backend `
  -RedirectStandardOutput $backendOut `
  -RedirectStandardError $backendErr `
  -PassThru
$env:PYTHONPATH = $oldPythonPath

try {
  Wait-Http "http://$BindHost`:$ApiPort/api/state"

  $staticProcess = Start-Process -FilePath $VenvPython `
    -ArgumentList @("-m", "http.server", "$StaticPort", "--bind", $BindHost) `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $staticOut `
    -RedirectStandardError $staticErr `
    -PassThru

  Wait-Http "http://$BindHost`:$StaticPort/"

  $mobileUrl = "http://$BindHost`:$StaticPort/companion-mobile-demo/"
  $wallpaperUrl = "http://$BindHost`:$StaticPort/desktop-wallpaper/?voice=1"
  $consoleUrl = "http://$BindHost`:$ApiPort/"

  Write-Host "手机聊天: $mobileUrl"
  Write-Host "3D 角色:  $wallpaperUrl"
  Write-Host "控制台:   $consoleUrl"
  Start-Process $mobileUrl
  Start-Process $wallpaperUrl

  Read-Host "保持此窗口打开即可持续运行。按 Enter 停止栖伴"
  Stop-QibanProcesses $backendProcess $staticProcess
} catch {
  Write-Host "启动失败：$($_.Exception.Message)"
  if (Test-Path $backendErr) {
    Write-Host "后端日志最后几行："
    Get-Content $backendErr -Tail 20
  }
  Stop-QibanProcesses $backendProcess $staticProcess
  exit 1
}
