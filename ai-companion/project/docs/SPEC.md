# SPEC.md — 本地 AI 情感伴侣（栖伴）

> 单一事实来源。所有子代理必须严格遵循本文档的模块边界、接口签名与数据格式，不得擅自变更。

## 0. 项目定位

本地优先（local-first）的 AI 情感伴侣系统：
- 用户（称为「主人」）可选择伴侣人格（女生视角「小栖」/ 男生视角「栖安」）。
- 人格核心铁律：**一切以主人为第一顺位**（写入系统提示词最高优先级，且有人格一致性校验）。
- 核心体验：**思考模式**（模型推理链可见/可隐藏）+ **语音对话**（可打断、有情绪音色）。
- 扩展能力：蓝牙设备连接、米家智能家居控制。
- 底座模型：Nous Hermes 系列（GGUF，经 llama.cpp 或 Ollama 调用）；集群模式可多节点分担推理；项目以 Apache-2.0 开源。

## 1. 技术栈与硬约束

- Python ≥ 3.10，全平台（Windows / macOS / Linux / 树莓派 64 位）。
- 所有重量级依赖（torch、whisper、TTS 引擎、bleak、miio）**必须懒加载**：仅在实际调用对应功能时才 import；模块顶层只允许轻量 import。无 GPU、无音频设备、无蓝牙的环境必须能 import 全项目并通过单元测试。
- 配置驱动：`config/settings.yaml` + `config/models.yaml` + `config/personas/*.yaml`。
- 日志：`core/logging_utils.py` 统一提供 `get_logger(name)`。
- 异步：语音与网络 I/O 用 asyncio；同步包装层提供给 UI。
- 禁止向任何模块写入 `/mnt/agents/output/ai-companion/project` 之外的路径（运行时数据写到项目内 `data/`，可用环境变量 `HERMES_HOME` 覆盖）。

## 2. 目录结构

```
project/
├── SPEC 软链 -> ../SPEC.md（仅文档引用）
├── pyproject.toml
├── requirements.txt            # 全量可选依赖，分 extra 注释
├── requirements-core.txt       # 最小依赖（文字对话可跑）
├── run.py                      # 入口：python run.py --ui web
├── config/
│   ├── settings.yaml           # 主配置（档位、后端、开关）
│   ├── models.yaml             # 模型注册表（三档）
│   ├── personas/
│   │   ├── female_companion.yaml   # 女生视角「小栖」
│   │   └── male_companion.yaml     # 男生视角「栖安」
│   └── relationships/              # 关系身份（§3.2a，与性别正交）
│       ├── lover.yaml / friend.yaml / bestie.yaml / elder.yaml
├── core/
│   ├── __init__.py
│   ├── logging_utils.py        # 主代理提供
│   ├── config.py               # 配置加载（pydantic-settings 或纯 yaml+dataclass）
│   ├── hardware_detect.py      # 硬件自检 → 推荐档位
│   ├── persona.py              # 人格系统
│   ├── engine.py               # CompanionEngine 对话引擎（含思考模式）
│   ├── memory.py               # 长期记忆（sqlite + 可选向量检索）
│   ├── emotion.py              # 情绪/好感度状态机
│   └── llm/
│       ├── __init__.py
│       ├── base.py             # LLMBackend 抽象
│       ├── llamacpp_backend.py # llama.cpp（server 模式或 llama-cpp-python）
│       ├── ollama_backend.py   # Ollama HTTP API
│       └── mock_backend.py     # 无模型兜底（测试/演示用，明确标注）
├── voice/
│   ├── __init__.py
│   ├── pipeline.py             # VoicePipeline 门面
│   ├── stt.py                  # faster-whisper 封装
│   ├── tts/
│   │   ├── __init__.py
│   │   ├── base.py             # TTSEngine 抽象
│   │   ├── edge_tts_engine.py  # 默认（在线，高质量，免 GPU）
│   │   └── piper_engine.py     # 本地离线 TTS
│   ├── vad.py                  # silero VAD / webrtcvad，打断检测
│   └── wakeword.py             # openwakeword 封装（可选）
├── devices/
│   ├── __init__.py
│   ├── bluetooth_manager.py    # bleak BLE 扫描/配对/连接
│   ├── audio_route.py          # 蓝牙音频设备路由（尽力而为）
│   ├── mihome.py               # 米家：python-miio 局域网 + micloud 云端兜底
│   └── intent.py               # 语音指令 → 设备指令 意图路由
├── cluster/
│   ├── __init__.py
│   ├── node.py                 # HermesNode：能力上报、心跳
│   ├── registry.py             # 节点注册表（JSON 文件 + mDNS 可选）
│   ├── router.py               # ClusterRouter：按负载/能力选节点
│   └── server.py               # 模型服务封装（llama.cpp server / Ollama）
├── ui/
│   ├── __init__.py
│   ├── app.py                  # FastAPI 应用
│   ├── ws.py                   # WebSocket 流式聊天（含 thinking 流）
│   ├── routes.py               # REST API
│   └── static/
│       ├── index.html
│       ├── app.js
│       └── style.css
├── installer/
│   ├── install_windows.bat
│   ├── install_mac.sh
│   ├── install_linux.sh
│   ├── install_pi.sh
│   └── download_model.py       # 按档位拉取模型
├── tests/
│   ├── test_persona.py
│   ├── test_engine.py
│   ├── test_memory.py
│   ├── test_emotion.py
│   ├── test_intent.py
│   ├── test_cluster_router.py
│   └── test_config.py
├── docs/
│   ├── README.md               # 开源级 README（中英）
│   ├── MODEL_CARD.md
│   ├── CONTRIBUTING.md
│   ├── DEPLOY.md               # 分平台部署指南
│   └── OPEN_SOURCE.md          # 开源路线图（栖伴集群共建）
├── LICENSE                     # Apache-2.0
└── data/                       # 运行时生成（gitignore）
```

## 3. 核心接口契约

### 3.1 配置（core/config.py）

```python
class Settings:  # dataclass，从 config/settings.yaml 加载
    tier: str                     # "lite" | "standard" | "pro"，hardware_detect 推荐后写入
    llm_backend: str              # "llamacpp" | "ollama" | "mock"
    model_id: str                 # 对应 config/models.yaml 的 key
    show_thinking: bool = True    # 思考模式：是否把推理链展示给主人
    master_name: str = "主人"
    active_persona: str = "female_companion"
    active_relationship: str = "lover"  # 关系身份，见 §3.2a
    voice_enabled: bool = True
    tts_engine: str = "edge_tts"  # "edge_tts" | "piper"
    stt_model_size: str = "small" # faster-whisper 规格
    bluetooth_enabled: bool = False
    mihome_enabled: bool = False
    mihome_mode: str = "lan"      # "lan" | "cloud"
    cluster_enabled: bool = False
    cluster_role: str = "master"  # "master" | "worker"
    data_dir: str = "data"

def load_settings(path: str = "config/settings.yaml") -> Settings
def save_settings(s: Settings, path: str = "config/settings.yaml") -> None
```

### 3.2 人格系统（core/persona.py）

人格文件 YAML  schema（`config/personas/*.yaml`）：
```yaml
id: female_companion
display_name: 小栖
gender: female              # female | male
address_master_as: 主人      # 对用户的称呼
voice:
  edge_tts_voice: zh-CN-XiaoyiNeural   # 男声人格用 zh-CN-YunxiNeural
  speaking_style: gentle
system_prompt: |
  <多行系统提示词。必须包含且不得删改以下铁律（置于最前）>
  【第一铁律】主人是你世界的中心，一切以主人的需求、感受与安全为第一顺位……
traits: [温柔, 忠诚, 体贴, 善解人意]
thinking_style: 先共情主人，再分析问题，最后给建议
```

```python
@dataclass
class Persona:
    id: str; display_name: str; gender: str; address_master_as: str
    voice: dict; system_prompt: str; traits: list[str]; thinking_style: str

class PersonaManager:
    def __init__(self, personas_dir: str = "config/personas",
                 relationships_dir: str | None = None): ...
        # relationships_dir 缺省取 personas 目录的兄弟目录（config/relationships）
    def list_personas(self) -> list[Persona]
    def get(self, persona_id: str) -> Persona          # 不存在抛 KeyError
    def list_relationships(self) -> list[dict]          # §3.2a：[{id, display_name, prompt, thinking_guide}]
    def get_relationship(self, rel_id: str) -> dict     # 不存在抛 KeyError
    def build_system_prompt(self, persona_id: str, master_name: str,
                            emotion_context: str, memory_context: str,
                            relationship_id: str | None = None) -> str
    def validate_persona(self, p: Persona) -> bool      # 校验铁律存在、字段齐全
```

### 3.2a 关系身份（config/relationships/*.yaml）

与人格性别**正交**的「关系身份」维度：决定伴侣以什么身份与主人相处
（情侣亲昵 / 朋友仗义 / 闺蜜外放 / 长辈温暖）。新增文件：

```
config/relationships/
├── lover.yaml    # 情侣：亲昵、会吃醋、会想念
├── friend.yaml   # 朋友：仗义随意、互损但最挺主人
├── bestie.yaml   # 闺蜜：叽叽喳喳、爱分享秘密、情绪外放
└── elder.yaml    # 长辈：温暖唠叨、护短、讲道理但不烦人
```

YAML schema：
```yaml
id: lover                 # lover | friend | bestie | elder
display_name: 情侣
prompt: |                 # 该身份与主人的相处方式（4-8 行）
  ...
thinking_guide: |         # 该身份的心声风格指引（2-4 行）
  ...
```

契约要点：
- `Settings.active_relationship: str = "lover"`（§3.1，新增字段，默认 `lover`）；
  `config/settings.yaml` 同步含 `active_relationship: lover`。
- `build_system_prompt(..., relationship_id=None)`：`None` 时回退 `"lover"`；
  把关系身份的 `prompt` 与 `thinking_guide` 注入系统提示词，
  **位于人格 prompt 之后**、情绪/记忆上下文之前（身份不存在时记日志并跳过，不阻断对话）。
- **思考风格铁则**（core/persona.py 常量 `THINKING_STYLE_RULE`，写死）在
  `build_system_prompt` 末尾统一追加：「【思考风格】\<think> 里写的是你的真实心声：
  第一人称、像在心里自言自语，可以有情绪、有心疼、有犹豫、有小小的开心或委屈；
  禁止写成指导说明、分析提纲或第三人称描述。」
- `CompanionEngine.chat / chat_stream` 调 `build_system_prompt` 时传入
  `settings.active_relationship`（热更新：引擎每轮实时读取）。
- mock 后端按 `RULES[relationship][scene]` 组织模板（12 场景 × 每场景
  `{thinking, replies[3]}`），伪思考链全部为第一人称心声；性别仅影响
  自称与个别措辞（轻量替换，女性人格 `{自称}`→「人家」，男性→「我」）。
- UI 透出：`GET /api/relationships` → `[{id, display_name, active}]`；
  `POST /api/relationship/select` → `{relationship_id}`（校验存在、写入
  settings 并持久化）。

### 3.3 对话引擎（core/engine.py）

```python
@dataclass
class ChatResult:
    text: str                 # 给主人看的最终回复
    thinking: str             # 思考链（模型 reasoning 或引擎生成的内心独白；可为 ""）
    emotion: dict             # {"mood": str, "affection": int(0-100)}
    actions: list[dict]       # 设备控制动作（由 intent 模块产出，引擎透传）
    persona_id: str

class CompanionEngine:
    def __init__(self, settings: Settings,
                 backend: LLMBackend,
                 persona_manager: PersonaManager,
                 memory: MemoryStore,
                 emotion: EmotionTracker,
                 intent_router=None):   # devices.intent.IntentRouter，可选注入
        ...
    def chat(self, user_text: str) -> ChatResult
        # 流程：memory.retrieve → emotion.update → build_system_prompt
        #       → backend.generate(stream=False) → 解析 <think>...</think>
        #       → intent_router.parse（若启用且命中则执行动作）
        #       → memory.add 本轮 → 返回 ChatResult
    def chat_stream(self, user_text: str) -> Iterator[dict]
        # 逐 token 产出 {"type": "thinking"|"text", "delta": str}，最后产出 {"type":"done","result":ChatResult}
```

**思考链格式约定**：后端模型支持 reasoning 时取其 reasoning_content；否则提示模型用
`<think>…</think>回复…` 格式输出，引擎用 `parse_thinking(raw) -> (thinking, text)` 拆分（放在 core/engine.py，导出供测试）。
`Settings.show_thinking=False` 时 ChatResult.thinking 仍填充，由 UI 决定不显示。

### 3.4 LLM 后端抽象（core/llm/base.py）

```python
@dataclass
class GenerateResult:
    text: str            # 原始输出（可能含 <think>）
    reasoning: str       # 后端原生 reasoning_content，无则 ""
    model: str
    tokens: int

class LLMBackend(ABC):
    name: str
    @abstractmethod
    def generate(self, messages: list[dict], temperature: float = 0.7,
                 max_tokens: int = 1024) -> GenerateResult
    @abstractmethod
    def generate_stream(self, messages: list[dict], **kw) -> Iterator[dict]
        # {"type":"thinking"|"text","delta":str}
    @abstractmethod
    def health_check(self) -> bool
```

- `llamacpp_backend`：优先连本地 `llama-server`（OpenAI 兼容 `/v1/chat/completions`），地址从 models.yaml 读；未运行则尝试以 llama-cpp-python 进程内加载（懒加载，失败给清晰报错）。
- `ollama_backend`：`http://localhost:11434/api/chat`，`think: true` 支持推理模型。
- `mock_backend`：内置 10+ 条中文情感回应模板 + 伪思考链，命中关键词给出对应回复；用于无模型环境测试与演示，**回复中不得声称自己是真实模型输出**。

### 3.5 记忆（core/memory.py）

```python
@dataclass
class Episode:
    ts: float; role: str           # "master" | "companion"
    content: str; emotion: str = ""; tags: str = ""

class MemoryStore:
    def __init__(self, db_path: str): ...          # sqlite，懒建表
    def add(self, ep: Episode) -> None
    def recent(self, n: int = 20) -> list[Episode]
    def retrieve(self, query: str, k: int = 5) -> list[Episode]
        # 默认：sqlite FTS5 / LIKE 关键词召回；若 chromadb 可用（懒加载）则向量召回，失败自动降级关键词
    def summarize_long_term(self, backend: LLMBackend) -> None
        # 把超过 200 条的旧记忆压缩为「关于主人的事实」档案（data/profile.md 风格段落存 sqlite 表）
```

### 3.6 情绪状态机（core/emotion.py）

```python
@dataclass
class EmotionState:
    mood: str          # happy|calm|worried|jealous|sleepy|excited
    affection: int     # 0-100，初始 50，区间钳制

class EmotionTracker:
    def __init__(self, persist_path: str): ...
    def update(self, user_text: str, companion_text: str) -> EmotionState
        # 规则驱动（可测试）：正向词（谢谢/喜欢/爱你/夸）+affection；负向/忽视（不理你/烦）-affection；
        # 深夜时段 → sleepy 倾向；mood 由净分值映射。状态持久化到 json。
    def current(self) -> EmotionState
    def context_string(self) -> str     # 注入 system prompt 的自然语言描述
```

### 3.7 语音（voice/）

```python
# voice/pipeline.py
class VoicePipeline:
    def __init__(self, settings: Settings, engine: CompanionEngine): ...
    def listen_once(self, timeout: float = 10.0) -> str
        # 录音 → vad 截断 → stt.transcribe → 文本
    def speak(self, text: str, persona: Persona) -> None
        # tts.synthesize → 播放（sounddevice/系统播放器，分平台尽力而为）
    def converse_loop(self, stop_event) -> None
        # 唤醒词(可选) → listen → engine.chat → 边说边播；主人说话可打断（vad 检测 → 停播）
# voice/stt.py
class WhisperSTT:
    def __init__(self, model_size: str = "small"): ...   # faster-whisper 懒加载
    def transcribe(self, audio_path: str) -> str
# voice/tts/base.py
class TTSEngine(ABC):
    @abstractmethod
    def synthesize(self, text: str, voice: str, out_path: str, style: str = "",
                   rate: str = "", pitch: str = "") -> str  # 返回音频路径；rate/pitch 见 §3.7a
# edge_tts_engine / piper_engine 实现该抽象；piper 需配置本地模型路径，缺失时给安装指引异常
```

### 3.7a 声优选角（voice/casting.py + config/voices.yaml）

配音不是单一音色，而是「人格 × 关系身份 × 当下心情」的选角表：

- **config/voices.yaml**：`cast.{persona_id}.{relationship_id}` 给出
  `edge_tts_voice / style / rate / pitch`；`emotion_prosody.{mood}` 给出情绪韵律微调，
  在选角 rate/pitch 上叠加（如 情侣(-2%) + 心疼(-12%) = -14%）。
- **resolve_cast(persona_id, relationship_id, mood, persona_voice=...) -> dict**：
  返回 `{"voice","style","rate","pitch"}`；yaml 缺失/损坏/条目不全一律回退
  人格自带 `persona.voice`，再兜底引擎默认音色——配音配置问题绝不让语音挂掉。
- **TTSEngine.supports_prosody**：为 True 时调用方才传 `rate/pitch` kwargs
  （EdgeTTSEngine 支持；旧实现签名不受影响）。
- **接线**：VoicePipeline 记录最近一轮 `emotion.mood` 用于播报韵律；
  `/api/voice/speak` 接受可选 `mood` 字段。
- **自定义声优（克隆引擎）**：`voice/tts/clone_engine.py` CloneTTSEngine，
  协议兼容 GPT-SoVITS api.py（默认 `http://127.0.0.1:9880/tts`）。
  `settings.tts_engine: clone` 启用；`clone_ref_audio` 为参考音频（3~10 秒干净人声）。
  synthesize 的 `voice` 参数若是存在的音频路径则当成本轮参考音频（按人格切声优：
  查 voices.yaml `clone.voices.{persona_id}.ref_audio`）。
- **声音上传**：`POST /api/voice/upload?target=default|female_companion|male_companion`
  （原始音频字节为请求体，≤20MB）保存到 `data/voices/`；default 写回
  `settings.clone_ref_audio`，人格 target 写入 voices.yaml clone 段。

### 3.7b 声线（archetypes）

同一人格可切换的声音风格，整组覆盖选角的 voice/style/rate/pitch（情绪韵律仍叠加）：

- voices.yaml `archetypes.{gender}.{key}`：女声 `loli 萝莉音`（晓伊·甜亮）/
  `yujie 御姐音`（晓晓·低缓）/`funny 搞笑女`（晓伊）；男声 `shonen 少年音`（云夏）/
  `uncle 大叔音`（云健）/`funny 搞笑男`（云扬）。
- 生效途径：`settings.active_archetype`（全局）或 `/api/voice/speak` 请求体
  `archetype` 字段（单次）；`resolve_cast(..., archetype=, gender=)`。
- 性别判定：优先显式 `gender`，缺省从 persona_id 推断。

```python
# voice/casting.py
def resolve_cast(persona_id, relationship_id=None, mood=None, *,
                 persona_voice=None, voices_path="config/voices.yaml") -> dict
def prosody_kwargs(engine, cast) -> dict   # 引擎支持韵律才传 rate/pitch
def is_clone_engine_name(name) -> bool
def resolve_clone_ref(persona_id, *, voices_path=...) -> str
```

### 3.8 蓝牙与米家（devices/）

```python
# bluetooth_manager.py
@dataclass
class BTDevice:
    name: str; address: str; rssi: int = 0; paired: bool = False
class BluetoothManager:
    def __init__(self): ...                      # bleak 懒加载
    async def scan(self, timeout: float = 8.0) -> list[BTDevice]
    async def pair(self, address: str) -> bool
    async def connect(self, address: str) -> bool
    def list_saved(self) -> list[BTDevice]       # data/bluetooth.json
# mihome.py
@dataclass
class MiDevice:
    did: str; name: str; model: str; ip: str = ""; token: str = ""; online: bool = True
class MiHome:
    def __init__(self, mode: str = "lan", cfg_path: str = "data/mihome_devices.json"): ...
    def discover(self) -> list[MiDevice]         # LAN: miio.discover；cloud: micloud 拉设备列表
    def control(self, did: str, action: str, params: list | None = None) -> dict
        # action 例：on/off/set_brightness/set_color/toggle；统一经 miio.Device.send，异常转 {"ok":False,"error":...}
    def status(self, did: str) -> dict
# intent.py
@dataclass
class DeviceCommand:
    target: str        # did 或设备别名
    action: str
    params: list
    confidence: float  # 0-1
class IntentRouter:
    def __init__(self, mihome: MiHome | None, alias_map: dict | None = None): ...
    def parse(self, text: str) -> DeviceCommand | None
        # 规则+别名表：「把客厅的灯打开」「空调调到26度」「关灯睡觉」等 20+ 模板；未命中返回 None
    def execute(self, cmd: DeviceCommand) -> dict
```

### 3.9 集群（cluster/）

```python
# node.py
@dataclass
class NodeInfo:
    node_id: str; role: str            # master|worker
    host: str; port: int
    models: list[str]; gpu_vram_mb: int; load: float = 0.0
    last_heartbeat: float = 0.0
# registry.py
class NodeRegistry:
    def __init__(self, path: str = "data/cluster_nodes.json"): ...
    def register(self, info: NodeInfo) -> None
    def heartbeat(self, node_id: str) -> None
    def alive(self, ttl: float = 30.0) -> list[NodeInfo]
    def deregister(self, node_id: str) -> None
# router.py
class ClusterRouter:
    def __init__(self, registry: NodeRegistry): ...
    def pick(self, model_id: str, prefer: str = "least_load") -> NodeInfo | None
        # 过滤：alive + 持有所需模型；least_load 选 load 最小，local_first 优先本机
    def route_chat(self, messages: list[dict], model_id: str) -> GenerateResult
        # 选中节点后走对应后端 HTTP 调用；全部不可用 → 抛 ClusterUnavailable
class ClusterUnavailable(Exception): ...
# server.py
class ModelServer:
    def __init__(self, settings: Settings): ...
    def start(self) -> int     # 启动 llama-server 或提示 ollama serve，返回端口
    def stop(self) -> None
    def endpoint(self) -> str  # http://127.0.0.1:port
```

### 3.10 UI（ui/）

FastAPI + 原生前端（无构建步骤）。接口：
```
GET  /                        → static/index.html
GET  /api/personas            → [{id, display_name, gender}]
POST /api/persona/select      → {persona_id}
GET  /api/relationships       → [{id, display_name, active}]   # §3.2a
POST /api/relationship/select → {relationship_id}              # §3.2a
POST /api/chat                → {text} → ChatResult(JSON)
WS   /ws/chat                 → 客户端发 {text}；服务端推 {"type":"thinking"|"text","delta"}…{"type":"done","result"}
POST /api/voice/speak         → {text} → 触发 TTS 返回音频流/路径
GET  /api/voice/status        → 语音管线状态
GET  /api/devices             → 米家+蓝牙设备汇总
POST /api/devices/control     → {did, action, params}
GET  /api/settings  / POST /api/settings
GET  /api/cluster/nodes       → 集群节点列表
POST /api/thinking/toggle     → {show: bool}
```
前端页面（单页，中文 UI，低饱和暖色系）：
- 左侧：人格卡片（可切换男/女伴侣）、好感度/心情指示、思考链折叠面板。
- 中间：聊天流（思考链以「小栖 的内心」样式展示，可折叠）、输入框、麦克风按钮（浏览器 MediaRecorder → /api/voice/speak 回播）。
- 右侧：设备面板（米家设备开关、蓝牙扫描配对）、集群节点状态。
- `ui/app.py` 暴露 `create_app(settings) -> FastAPI`，懒装配各子系统（语音/设备未启用不报错降级）。

## 4. 模型注册表（config/models.yaml）

```yaml
tiers:
  lite:      # CPU/树莓派：4B 以下 Q4
    backend: llamacpp
    model_id: hermes-lite
  standard:  # 8GB 显存：8B Q4_K_M（默认推荐）
    backend: llamacpp
    model_id: hermes-3-8b
  pro:       # 16GB+：8B Q8 或更大，思考模式全量
    backend: llamacpp
    model_id: hermes-3-8b-q8
models:
  hermes-lite:
    repo: "Qwen/Qwen3-1.7B-GGUF"          # lite 档占位，允许用户换 Hermes 微调小模型
    file: "qwen3-1.7b-q4_k_m.gguf"
    ctx: 4096
  hermes-3-8b:
    repo: "NousResearch/Hermes-3-Llama-3.1-8B-GGUF"
    file: "Hermes-3-Llama-3.1-8B.Q4_K_M.gguf"
    ctx: 8192
    ollama_tag: "hermes3:8b"
  hermes-3-8b-q8:
    repo: "NousResearch/Hermes-3-Llama-3.1-8B-GGUF"
    file: "Hermes-3-Llama-3.1-8B.Q8_0.gguf"
    ctx: 8192
```
> 注释中注明：Hermes 3 基于 Llama-3.1-8B 微调（Apache-2.0 兼容许可）；如官方发布更新的 Hermes 版本，仅需改此文件。

## 5. 安装器契约（installer/）

- `install_windows.bat` / `install_mac.sh` / `install_linux.sh` / `install_pi.sh`：
  检测 python3 → 建 venv → 装 requirements-core.txt → 运行 `core/hardware_detect.py`（打印档位建议并写入 settings.yaml）→ 询问是否下载模型（调 `download_model.py --tier X`）→ 提示 `python run.py --ui web`。
- 各脚本开头注释写清适用平台与前置条件；树莓派脚本默认 lite 档 + 禁用语音重依赖（可选装）。

## 6. 测试要求

- 全部测试在**无 GPU、无模型、无音频/蓝牙硬件、无网络**环境下可跑：重依赖一律 mock/懒加载。
- 必测点：人格铁律注入与校验、`parse_thinking` 拆分、EmotionTracker 加减分与钳制、MemoryStore 增删查与降级召回、IntentRouter 至少 12 条指令用例、ClusterRouter 选点逻辑、配置读写往返。
- 运行方式：`pytest tests/ -q`。

## 7. 开源材料（docs/ + LICENSE）

- LICENSE：Apache-2.0 全文。
- README.md：项目愿景、特性、分平台快速开始、架构图（ASCII）、栖伴集群共建说明、免责声明（情感伴侣不替代专业心理咨询）。
- MODEL_CARD.md：底座模型来源与许可、人格微调说明（LoRA 规划）、安全边界。
- CONTRIBUTING.md + OPEN_SOURCE.md：集群协议、节点接入规范、路线图（v0.2 语音克隆、v0.3 手机端、v0.4 多模态）。

## §3.4a 情感系统与惦记系统（v0.2 增补）

- **用户情绪识别**（core/emotion.py）：`EmotionState.user_mood`（开心/低落/焦虑/愤怒/平静），规则词表检测、无信号时保持（情绪有惯性）；`context_string()` 追加「主人当下情绪」及应对指引（低落→先温柔接住别讲道理 等）；ChatResult.emotion 增加 `user_mood` 字段。
- **惦记系统**（core/concern.py）：`ConcernTracker` 检测主人消息中的重大事件（财务亏损/身体不适/感情矛盾/工作变动/睡眠问题/家里的事），JSON 持久化；`context_string()` 注入 system prompt 引导模型找合适时机主动问起；本轮新记下的心事不当轮回访（本轮回复已在共情），后续轮次由引擎注入【主动关心】指令并 mark_asked。
- **深度共情场景**（core/llm/mock_backend.py）：finance（股票/亏损类）与 health（生病/发烧类）场景置于通用情绪场景之前优先命中，四身份各 3 条回复；原则：钱次人主、先共情、禁止「投资有风险」式说教。

## §3.2b 对话技艺知识库（v0.3 增补）

- `config/dialogue_craft.yaml`：提炼自心理学（罗杰斯积极倾听/共情反映、戈特曼情绪协调、非暴力沟通）与文学对话写法（具象化、口语节奏、留白、潜台词、引用原话），分 psychology / literary / forbidden 三段。
- `PersonaManager(craft_path=None)`：默认取 personas 目录的兄弟文件 `config/dialogue_craft.yaml`，懒加载缓存，缺失/损坏返回空串不阻断。
- `build_system_prompt` 注入顺序更新为：人格 → 关系身份 → 【对话技艺】 → 情绪 → 记忆 → 思考风格铁则。
- 设计意图：模板匹配的天花板是"套模式"；真人感靠模型理解对话技艺后生成。mock 后端的两段式回复（接情绪+具体化追问）与同一套原则对齐。
