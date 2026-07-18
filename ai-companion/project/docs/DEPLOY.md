# 部署指南（DEPLOY）

栖伴 支持 Windows / macOS / Linux / 树莓派。核心思路：**一套代码，四平台安装脚本，硬件自检自动推荐模型档位**。

## 一、快速开始（各平台）

| 平台 | 命令 |
|---|---|
| Windows | 双击 `installer\install_windows.bat` |
| macOS | `bash installer/install_mac.sh` |
| Linux | `bash installer/install_linux.sh` |
| 树莓派 | `bash installer/install_pi.sh`（默认 lite 档） |

安装脚本会依次：创建 venv → 安装核心依赖 → 硬件自检推荐档位 → 可选安装语音/蓝牙/米家组件 → 可选下载模型。

启动：
```bash
python run.py --ui web          # Web 控制台，浏览器打开 http://127.0.0.1:7860
python run.py --ui cli          # 终端纯文字对话（无模型时自动用 mock 后端演示）
```

## 二、模型档位（硬件自检自动推荐）

| 档位 | 适用硬件 | 模型 | 体积 |
|---|---|---|---|
| lite | 纯 CPU / 树莓派 | 1.7B Q4（可换任意 Hermes 微调小模型） | ~1GB |
| standard | 8GB 显存 / 16GB 内存 | Hermes-3-Llama-3.1-8B Q4_K_M | ~4.9GB |
| pro | 16GB+ 显存 | Hermes-3-Llama-3.1-8B Q8 | ~8.5GB |

后端二选一（`config/settings.yaml` 的 `llm_backend`）：
- `llamacpp`：本地 llama.cpp / llama-server，加载 `installer/download_model.py` 下载的 GGUF；
- `ollama`：`ollama pull hermes3:8b && ollama serve`，引擎自动走 Ollama API；
- `mock`：无模型兜底（演示/测试用，回复为内置模板）。

## 三、语音对话

1. 安装语音组件（安装脚本中选 y，或手动 `pip install faster-whisper edge-tts sounddevice webrtcvad`）。
2. `settings.yaml`：`voice_enabled: true`。
3. 默认 edge-tts（在线、免 GPU、拟真度高）；离线场景切 `tts_engine: piper` 并配置本地模型。
4. 男/女伴侣音色由人格文件 `config/personas/*.yaml` 的 `voice.edge_tts_voice` 决定，可自由更换任意 edge-tts 中文音色。

## 四、蓝牙

`pip install bleak` 后 `bluetooth_enabled: true`。Web 控制台右侧设备面板可扫描/配对 BLE 设备；蓝牙音箱/耳机音频路由为分平台尽力而为（Linux 依赖 bluez）。

## 五、米家智能家居

1. `pip install python-miio`，`mihome_enabled: true`。
2. LAN 模式：与设备同局域网，token 获取方式见 python-miio 文档；云端模式（`mihome_mode: cloud`）使用小米账号拉取设备列表。
3. 语音/文字指令直达：「把客厅的灯打开」「空调调到 26 度」——由 `devices/intent.py` 路由，别名可在 `data/mihome_devices.json` 配置。

## 六、栖伴集群（多机分担推理）

- 主机：`cluster_enabled: true, cluster_role: master`；
- 分机：`cluster_role: worker`，启动后自动上报能力（CPU/显存/模型）并心跳；
- 路由策略：`least_load`（默认）/ `local_first`，见 `cluster/router.py`；
- 节点接入规范与共建路线图见 `docs/OPEN_SOURCE.md`。

## 七、常见问题

- **无 GPU 能跑吗**：能。mock 后端开箱即演示；lite 档 1.7B 模型纯 CPU 可用；标准档以上建议 N 卡。
- **首次回复慢**：llama.cpp 首次加载模型需读盘，后续常驻内存。
- **数据存哪**：全部在 `data/` 目录（记忆 sqlite、情绪状态、设备缓存、模型），删除即重置。
