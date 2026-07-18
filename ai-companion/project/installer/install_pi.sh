#!/bin/bash
# ============================================================
#  栖伴 一键安装脚本（树莓派 4B/5，64 位 Raspberry Pi OS）
#  默认使用 lite 档位（1.7B 小模型 Q4），语音重依赖可选装
#  用法：bash installer/install_pi.sh
# ============================================================
set -e
cd "$(dirname "$0")/.."

echo "[1/5] 检测环境（树莓派建议使用 64 位系统）..."
command -v python3 >/dev/null || { sudo apt update && sudo apt install -y python3; }

echo "[2/5] 创建虚拟环境 .venv ..."
sudo apt install -y python3-venv || true
python3 -m venv .venv
source .venv/bin/activate

echo "[3/5] 安装核心依赖..."
pip install --upgrade pip -q
pip install -r requirements-core.txt

echo "[4/5] 强制使用 lite 档位..."
python3 - <<'PY'
import re
p = "config/settings.yaml"
s = open(p, encoding="utf-8").read()
s = re.sub(r"^tier:.*$", "tier: lite", s, flags=re.M)
s = re.sub(r"^model_id:.*$", "model_id: hermes-lite", s, flags=re.M)
open(p, "w", encoding="utf-8").write(s)
print("已写入 lite 档位")
PY

read -p "是否安装语音组件（树莓派上 STT 较慢，edge-tts 推荐）？[y/N] " VOICE
if [[ "$VOICE" =~ ^[Yy]$ ]]; then
    sudo apt install -y portaudio19-dev ffmpeg || true
    pip install edge-tts sounddevice webrtcvad
    read -p "同时安装本地 STT（faster-whisper，Pi 上较慢）？[y/N] " STT
    [[ "$STT" =~ ^[Yy]$ ]] && pip install faster-whisper
fi

read -p "是否现在下载 lite 档模型（约 1GB）？[y/N] " DL
if [[ "$DL" =~ ^[Yy]$ ]]; then
    python3 installer/download_model.py --tier lite
fi

echo "[5/5] 安装完成！"
echo "启动方式：python run.py --ui web --host 0.0.0.0"
echo "同一局域网手机/电脑浏览器打开 http://树莓派IP:7860"
