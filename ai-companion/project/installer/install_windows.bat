@echo off
REM ============================================================
REM  栖伴 一键安装脚本（Windows 10/11）
REM  前置条件：已安装 Python 3.10+（勾选 Add to PATH）
REM  用法：双击运行，或在项目根目录执行 installer\install_windows.bat
REM ============================================================
setlocal
cd /d "%~dp0\.."

echo [1/5] check Python...
where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install 3.10+ from https://www.python.org with "Add to PATH".
    pause
    exit /b 1
)

echo [2/5] create venv .venv ...
python -m venv .venv
call .venv\Scripts\activate.bat

echo [3/5] install core deps...
python -m pip install --upgrade pip
pip install -r requirements-core.txt

echo [4/5] hardware detect / tier recommend...
python core\hardware_detect.py

set /p VOICE=Install voice components (STT/TTS/VAD, large)? [y/N]:
if /i "%VOICE%"=="y" (
    pip install faster-whisper edge-tts sounddevice webrtcvad
)

set /p DL=Download local model now? [y/N]:
if /i "%DL%"=="y" (
    python installer\download_model.py
)

echo [5/5] Done!
echo.
echo Start: python run.py --ui web
echo Open http://127.0.0.1:7860 in browser
echo Tip: set llm_backend to llamacpp or ollama in config\settings.yaml for real model
pause
