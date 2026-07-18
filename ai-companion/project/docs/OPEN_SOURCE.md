# 开源路线图与 栖伴集群共建规范

> 栖伴 以 [Apache-2.0](../LICENSE) 开源。本文档给出版本路线图，
> 并公开 **栖伴集群协议与节点接入规范**，欢迎社区一起把「家里的每台设备都变成伴侣的算力」。

---

## 1. 开源路线图（Roadmap）

### v0.1 · 当前版本 —— 能跑起来的完整闭环
- [x] 双人格（小栖 / 栖安）+ 主人第一顺位铁律与人格校验
- [x] 思考模式（推理链可见 / 可隐藏）
- [x] 文字对话 + Web 控制台（聊天 / 思考链面板 / 设备面板 / 集群状态）
- [x] 长期记忆（sqlite 关键词召回，可选向量增强）与情绪状态机
- [x] 蓝牙（BLE 扫描/配对）与米家控制 + 语音意图路由
- [x] **栖伴集群 v1 协议**：JSON 注册表 + 心跳 + least_load / local_first 路由
- [x] 分平台安装器与硬件自检分档（lite / standard / pro）

### v0.2 · 语音克隆 —— 让陪伴有「她的声音」
- [ ] 本地声纹注册：主人提供数分钟参考音频，克隆伴侣音色（SoVITS / XTTS 类方案，全部本地）
- [ ] 情绪音色：TTS 输出随 EmotionTracker 的心情/好感度变化
- [ ] 全双工对话体验优化：更稳的 VAD 打断、边想边说（思考链与语音并行流式）
- [ ] 伦理护栏：仅允许克隆本人明确授权的声音，内置授权确认流程

### v0.3 · 手机端 —— 把伴侣装进口袋
- [ ] Android / iOS 客户端（优先 PWA + 原生壳，降低维护成本）
- [ ] 手机作为集群节点：接入 栖伴集群协议（上报能力、承接轻量推理或仅做语音终端）
- [ ] 与桌面端记忆同步（端到端加密的局域网同步，不走云端）
- [ ] 后台常驻与通知：早安问候、提醒事项的主动陪伴

### v0.4 · 多模态 —— 看得见彼此
- [ ] 视觉输入：本地 VLM（看图、识物、看屏幕协助）
- [ ] 表情/形象输出：Live2D 或 3D 虚拟形象，口型与情绪联动
- [ ] 多模态记忆：照片/截图进入长期记忆并可检索
- [ ] 设备视觉联动：米家摄像头等（严格本地处理，隐私优先）

> 版本节奏以 Issue 里程碑为准；欢迎认领任何一格。

---

## 2. 栖伴集群协议（v1）

### 2.1 架构角色

- **master**：持有 `NodeRegistry`（JSON 文件注册表）与 `ClusterRouter`，负责选点与请求路由；
  自身也可以同时是推理节点。
- **worker**：运行模型服务（llama.cpp `llama-server` 或 Ollama），周期上报心跳。

### 2.2 节点信息（NodeInfo）

节点以如下 JSON 结构描述自己（对应 `cluster.node.NodeInfo`）：

```json
{
  "node_id": "study-pc-a1b2c3",
  "role": "worker",
  "host": "192.168.1.10",
  "port": 8080,
  "models": ["hermes-3-8b"],
  "gpu_vram_mb": 8192,
  "load": 0.42,
  "last_heartbeat": 1737000000.0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `node_id` | string | 集群内唯一；建议 `主机名-随机6位`（`collect_local_info()` 自动生成） |
| `role` | string | `master` 或 `worker` |
| `host` / `port` | string / int | 节点 OpenAI 兼容服务地址 |
| `models` | string[] | 本节点已加载/可服务的 model_id 列表（对应 `config/models.yaml` 的 key） |
| `gpu_vram_mb` | int | 显存总量（MB），无 GPU 填 0；尽力探测，允许不精确 |
| `load` | float | 0.0~1.0 负载估计（CPU/内存/显存综合），选点的依据 |
| `last_heartbeat` | float | Unix 时间戳；注册表按它与 ttl 判定存活 |

### 2.3 注册表与心跳

- 注册表是 master 上的一个 JSON 文件（默认 `data/cluster_nodes.json`），
  内容为 `{node_id: NodeInfo}` 的映射；**写入必须原子**（临时文件 + `os.replace`）。
- worker 每 `ttl/3` 秒（建议 10s）调用一次 `heartbeat(node_id)` 刷新时间戳；
  默认 **ttl = 30s**，超时节点从 `alive()` 中消失，不再参与选点。
- 节点下线应主动 `deregister(node_id)`；异常下线由 ttl 兜底清理。
- v1 用共享文件（如 NFS/同步盘）或 master 代管实现多机注册；
  **mDNS 自动发现与 HTTP 注册端点是 v1→v2 的演进方向**，欢迎社区贡献。

### 2.4 推理接口（OpenAI 兼容）

每个节点必须暴露 OpenAI 兼容的 chat 接口：

```
POST http://<host>:<port>/v1/chat/completions
Content-Type: application/json

{
  "model": "<model_id>",
  "messages": [{"role": "user", "content": "..."}],
  "temperature": 0.7,
  "max_tokens": 1024
}
```

- llama.cpp 的 `llama-server` 与 Ollama 均原生兼容该协议（Ollama 为 `/v1` 兼容端点）。
- 推理模型的思考链通过响应 `choices[0].message.reasoning_content` 字段返回，
  master 侧将其映射为 `GenerateResult.reasoning`。
- 路由策略（`ClusterRouter.pick`）：
  - `least_load`：存活 + 持有目标模型的节点中选 `load` 最小者；
  - `local_first`：优先本机节点（本机节点间再按 load 最小），无本机节点退化为 `least_load`。
- 全部节点不可用 / 调用失败时，master 抛出 `ClusterUnavailable`，
  由上层（对话引擎）降级到本地 mock 或提示主人检查集群。

### 2.5 节点接入步骤（如何加入一个集群）

1. **准备模型服务**（二选一）：
   - llama.cpp：让 `llama-server` 可被找到（PATH 或 `HERMES_LLAMA_SERVER` 环境变量），
     下载对应 GGUF 到 `data/models/`；
   - Ollama：安装并运行 `ollama serve`，`ollama pull hermes3:8b`。
   `cluster.server.ModelServer` 会自动探测/拉起服务并给出缺失组件的安装指引。
2. **上报能力**：调用 `collect_local_info(role="worker", port=<端口>, models=[<model_id>])`
   生成 `NodeInfo`，`NodeRegistry.register(info)` 注册到 master 的注册表。
3. **周期心跳**：每 ~10 秒 `registry.heartbeat(node_id)`；进程退出时 `deregister`。
4. **验证**：在 master 的 Web 控制台右侧「集群节点状态」面板应能看到新节点；
   `GET /api/cluster/nodes` 返回节点列表。

### 2.6 安全须知

- v1 协议**面向主人自己的可信局域网**：注册表与推理接口均无鉴权，
  请勿将节点端口暴露到公网；跨机器部署时请放在防火墙/内网之后。
- 集群内传输的对话内容是明文 HTTP；有更高隐私需求时请在节点侧自行叠加
  TLS 反向代理（如 Caddy/nginx），协议保持不变。
- 只注册你信任的设备：任何能写注册表文件的人都能把流量引向恶意节点。

### 2.7 协议演进（欢迎共建）

| 方向 | 说明 | 状态 |
| --- | --- | --- |
| mDNS 自动发现 | worker 开机即被发现，免手动注册 | 规划中 |
| HTTP 注册/心跳端点 | 替代共享文件，跨 OS 更稳 | 规划中 |
| 节点鉴权 | 预共享密钥 + 签名校验 | 讨论中 |
| 流式路由 | `route_chat_stream` 透传 SSE token 流 | 讨论中 |
| 负载精化 | 结合排队深度 / tokens-per-second 的真实负载 | 讨论中 |

有意参与请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 并从 Issue 开始。
