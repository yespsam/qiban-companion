# 栖伴随身小盒子部署草案

目标：把栖伴后端、语音、记忆和手机聊天入口装进一台可随身携带的小主机。手机、桌面壁纸、后续外壳都只作为前端入口，核心伴侣服务常驻在盒子里。

## 推荐硬件

优先级从体验到便携：

1. 迷你 N100 / N150 主机，16GB 内存，256GB SSD  
   适合跑 Ollama、Edge TTS、faster-whisper base/small，体验最稳。

2. Orange Pi 5 / Raspberry Pi 5，8GB 内存以上  
   适合轻量模型、Piper 离线 TTS、faster-whisper tiny/base。

3. 旧安卓手机或随身 Wi-Fi 主机  
   更适合当前端或热点，不建议承担完整本地推理。

## 盒子里常驻的服务

```bash
cd /path/to/ai-companion/project
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-core.txt
pip install edge-tts
python run.py --ui web --host 0.0.0.0 --port 8766
```

手机端访问：

```text
http://盒子IP:8766
```

如果继续使用 `companion-mobile-demo/index.html`，在语音设置里把服务器填成：

```text
http://盒子IP:8766
```

## 离线与联网

联网优先方案：

- LLM：Ollama 或 llama.cpp
- TTS：edge-tts
- STT：faster-whisper
- 优点：中文声音自然，调试简单。

离线优先方案：

- LLM：Ollama 小模型，或 llama.cpp GGUF
- TTS：Piper
- STT：faster-whisper tiny/base
- 优点：无网可用；缺点是声音拟真度低于联网 TTS。

专属声音方案：

- `tts_engine: clone`
- 启动 GPT-SoVITS / CosyVoice 兼容服务
- 通过 `/api/voice/upload?target=female_companion` 或 `/api/voice/upload?target=male_companion` 上传参考音频

## 开机自启方向

Linux 小盒子可以用 systemd：

```ini
[Unit]
Description=Qiban Companion
After=network-online.target

[Service]
WorkingDirectory=/opt/qiban/ai-companion/project
ExecStart=/opt/qiban/ai-companion/project/.venv/bin/python run.py --ui web --host 0.0.0.0 --port 8766
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## 端口约定

- `8766`：栖伴后端和 Web 控制台
- `8765`：手机静态 demo 调试
- `9880`：GPT-SoVITS / 克隆 TTS 兼容 API

## 下一步硬件化清单

- 给盒子加麦克风和扬声器
- 安装 `sounddevice faster-whisper webrtcvad`
- 做一个局域网设备发现页面，手机自动找到盒子 IP
- 给 3D 桌面壁纸打包 Electron/Tauri
- 把手机聊天入口做成 PWA，添加到主屏幕
