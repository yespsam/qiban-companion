#!/bin/bash
# ============================================================
#  栖伴 一键安装脚本（macOS 12+，Intel/Apple Silicon）
#  前置条件：python3 >= 3.10（建议 brew install python@3.12）
#  用法：bash installer/install_mac.sh
# ============================================================
set -e
cd "$(dirname "$0")/.."

echo "[1/5] 检测 Python..."
command -v python3 >/dev/null || { echo "未找到 python3，请先 brew install python@3.12"; exit 1; }

echo "[2/5] 创建虚拟环境 .venv ..."
python3 -m venv .venv
source .venv/bin/activate

echo "[3/5] 安装核心依赖..."
pip install --upgrade pip -q
pip install -r requirements-core.txt

echo "[4/5] 硬件自检与模型档位推荐..."
python3 core/hardware_detect.py || true

read -p "是否安装语音对话组件（STT/TTS/VAD）？[y/N] " VOICE
if [[ "$VOICE" =~ ^[Yy]$ ]]; then
    pip install faster-whisper edge-tts sounddevice webrtcvad
fi

read -p "是否现在下载本地模型？[y/N] " DL
if [[ "$DL" =~ ^[Yy]$ ]]; then
    python3 installer/download_model.py
fi

echo "[5/5] 安装完成！"
echo ""
echo "启动方式：python run.py --ui web"
echo "然后浏览器打开 http://127.0.0.1:7860"
echo "提示：在 config/settings.yaml 中把 llm_backend 改为 llamacpp 或 ollama 即可使用真实模型"
