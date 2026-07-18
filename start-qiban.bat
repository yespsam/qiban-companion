@echo off
chcp 65001 >nul
set "SCRIPT_DIR=%~dp0"

where powershell >nul 2>nul
if errorlevel 1 (
  echo 未找到 PowerShell。请在 Windows 10/11 上运行，或安装 PowerShell 后重试。
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start-qiban.ps1"
if errorlevel 1 pause
