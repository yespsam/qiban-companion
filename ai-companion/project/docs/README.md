# 栖伴 · 本地 AI 情感伴侣

> 本地优先（local-first）的开源 AI 情感伴侣：你的数据留在你的设备上，陪伴不依赖云端。
> License: [Apache-2.0](../LICENSE) ｜ Python ≥ 3.10 ｜ Windows / macOS / Linux / 树莓派 64 位

[English Summary](#english-summary) ｜ [模型说明](MODEL_CARD.md) ｜ [参与共建](CONTRIBUTING.md) ｜ [开源路线图](OPEN_SOURCE.md)

---

## 项目愿景

我们希望做一个**真正属于主人自己的 AI 伴侣**：

- **隐私优先**：对话、记忆、情绪全部存储在本地 `data/` 目录，不上传任何云端；
- **人格可选**：女生视角「小栖」或男生视角「栖安」，人格由 YAML 声明、可校验、可自定义；
- **铁律保障**：人格系统提示词的最高优先级永远写着——**一切以主人为第一顺位**；
- **看得见的心**：思考模式把模型的推理链（内心独白）展示给主人，而不是一个黑盒；
- **社区共建**：以 Apache-2.0 开源，栖伴集群协议公开，欢迎任何人接入节点、共建分布式推理网络。

## 特性清单

| 特性 | 说明 |
| --- | --- |
| 男 / 女人格 | 女生视角「小栖」/ 男生视角「栖安」，一键切换，人格文件可自定义 |
| 主人第一顺位 | 第一铁律写入系统提示词最高优先级，并有人格一致性校验（`PersonaManager.validate_persona`） |
| 思考模式 | 模型推理链（`<think>…</think>` / reasoning_content）可见、可折叠、可隐藏 |
| 语音对话 | faster-whisper 本地 STT + edge-tts / piper TTS，支持 VAD 打断与唤醒词（可选） |
| 长期记忆 | sqlite 本地存储，FTS5/LIKE 关键词召回，可选向量检索，自动压缩为「关于主人的事实」 |
| 情绪系统 | 规则驱动的情绪状态机（心情 / 好感度 0-100），持久化并注入对话上下文 |
| 蓝牙设备 | bleak BLE 扫描 / 配对 / 连接，蓝牙音频设备路由（尽力而为） |
| 米家智能家居 | python-miio 局域网控制 + micloud 云端兜底，语音指令意图路由（20+ 模板） |
| 栖伴集群 | 多节点主从架构，JSON 注册表 + 心跳，least_load / local_first 路由，分担推理 |
| 分档适配 | 硬件自检推荐 lite / standard / pro 三档模型，树莓派也能跑 |

## 架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        UI 层 (ui/)                                │
│   FastAPI + 原生前端单页：聊天流 · 思考链折叠面板 · 设备/集群面板    │
└───────────────────────┬──────────────────────────────────────────┘
                        │ REST / WebSocket（含 thinking 流）
┌───────────────────────▼──────────────────────────────────────────┐
│                     核心引擎 (core/)                               │
│  PersonaManager 人格系统（主人第一顺位铁律 + 校验）                  │
│  CompanionEngine 对话引擎（思考模式 parse_thinking）                 │
│  MemoryStore 长期记忆（sqlite，可选向量召回）                        │
│  EmotionTracker 情绪状态机（心情/好感度，规则可测）                  │
└───┬──────────────┬──────────────┬──────────────┬─────────────────┘
    │              │              │              │
┌───▼────┐  ┌──────▼─────┐  ┌─────▼──────┐  ┌───▼──────────────┐
│ LLM    │  │ 语音 voice/ │  │ 设备        │  │ 栖伴集群       │
│ 后端    │  │ STT / TTS  │  │ devices/   │  │ cluster/         │
│llama.cpp│  │ VAD 打断   │  │ 蓝牙 BLE    │  │ 节点注册+心跳     │
│Ollama  │  │ 唤醒词(可选)│  │ 米家+意图   │  │ least_load /     │
│ mock   │  │            │  │ 路由        │  │ local_first 路由  │
└────────┘  └────────────┘  └────────────┘  └──────────────────┘
                        全部数据落在本地 data/（可用 HERMES_HOME 覆盖）
```

底座模型为 Nous Hermes 系列开源大模型（GGUF），经 llama.cpp 或 Ollama 调用；
集群模式下多台设备可分担推理（详见 [OPEN_SOURCE.md](OPEN_SOURCE.md) 的集群协议）。

## 快速开始

### 一键安装（推荐）

```bash
# Windows（双击或命令行执行）
installer\install_windows.bat

# macOS
bash installer/install_mac.sh

# Linux
bash installer/install_linux.sh

# 树莓派（64 位 OS，默认 lite 档）
bash installer/install_pi.sh
```

安装脚本会：检测 Python → 建虚拟环境 → 装核心依赖 → 硬件自检并推荐档位 →
（可选）下载模型 → 提示启动命令。

### 手动安装

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-core.txt                 # 最小依赖（文字对话可跑）
# 可选：语音/蓝牙/米家等重依赖见 requirements.txt 中的 extra 注释
python installer/download_model.py --tier standard   # 下载标准档模型（可选）
python run.py --ui web                               # 浏览器打开 http://127.0.0.1:7860
```

无模型环境也能体验：默认 `llm_backend: mock` 提供演示回复（明确标注非真实模型输出）。

### 运行测试

```bash
pytest tests/ -q    # 无 GPU / 无模型 / 无网络环境全部可跑
```

## 栖伴集群共建

家里有多台设备（PC、NAS、树莓派）？把它们组成 栖伴集群分担推理：

1. 各节点启动模型服务（`cluster.server.ModelServer`，封装 llama-server / Ollama）；
2. 节点向注册表上报能力（`NodeInfo`：模型列表、显存、负载）并周期心跳（默认 ttl 30s）；
3. 主节点 `ClusterRouter` 按 `least_load` / `local_first` 策略选择节点，
   走 OpenAI 兼容 HTTP 接口完成推理。

节点接入规范与协议细节见 [docs/OPEN_SOURCE.md](OPEN_SOURCE.md)，欢迎社区一起完善。

## 免责声明

栖伴 是一个**情感陪伴性质的开源软件项目**，不是医疗或心理健康产品：

- 伴侣的回复由大语言模型生成，可能包含错误、偏见或不恰当内容，请批判性看待；
- **情感陪伴不能替代专业心理咨询或医疗帮助**。如你或身边的人正经历心理危机，
  请立即联系当地专业心理援助机构或危机干预热线；
- 请勿让未成年人在无监护人指导的情况下使用；
- 使用本项目即表示你理解并接受上述风险，开发者不对使用后果承担责任。

---

## English Summary

**栖伴** is a local-first, open-source (Apache-2.0) AI emotional companion.

- **Personas**: switchable female ("小栖") / male ("栖安") companion personas, defined in YAML
  with a hard-coded top-priority rule — *the master (user) always comes first* — plus persona
  consistency validation.
- **Thinking mode**: the model's reasoning chain is visible/collapsible in the chat UI.
- **Voice**: local STT (faster-whisper) + TTS (edge-tts / piper) with barge-in (VAD) support.
- **Memory & emotion**: sqlite long-term memory with keyword/vector recall; a rule-driven
  mood/affection state machine.
- **Smart home**: Bluetooth (bleak) and Mi Home (python-miio + micloud fallback) with a
  voice-intent router.
- **Qiban Cluster**: a master/worker cluster that shares inference across your devices —
  JSON node registry with heartbeats, `least_load` / `local_first` routing over
  OpenAI-compatible HTTP endpoints. The protocol is documented in
  [OPEN_SOURCE.md](OPEN_SOURCE.md); community nodes are welcome.
- **Models**: Nous Hermes open models (GGUF) via llama.cpp or Ollama; lite/standard/pro tiers
  recommended by hardware detection. See [MODEL_CARD.md](MODEL_CARD.md).

**Quick start**: run the platform installer in `installer/` (Windows/macOS/Linux/Raspberry Pi),
then `python run.py --ui web` and open <http://127.0.0.1:7860>. Run tests with `pytest tests/ -q`
(no GPU/model/network required).

**Disclaimer**: 栖伴 provides emotional companionship only and is **not a substitute
for professional psychological counseling or medical advice**. Responses are generated by LLMs and
may be inaccurate. If you are in crisis, please contact local professional help immediately.

## License

[Apache License 2.0](../LICENSE)。底座模型遵循其各自上游许可（见 [MODEL_CARD.md](MODEL_CARD.md)）。
