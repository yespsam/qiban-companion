# 栖伴解压版使用说明

这是给非开发者使用的便携包。下载 ZIP 后不需要 Git，也不需要手动找代码入口。

## 1. 解压

把 `qiban-companion-portable-v0.2.20.zip` 解压到一个普通文件夹，例如桌面或文档目录。

## 2. 启动

macOS：

```text
双击 start-qiban.command
```

Windows 10/11：

```text
双击 start-qiban.bat
```

Linux：

```bash
bash start-qiban.sh
```

第一次启动会自动创建 Python 虚拟环境并安装核心依赖，需要联网。后续启动会快很多。

## 3. 打开的入口

启动成功后会自动打开一个纯人物入口：

```text
http://127.0.0.1:8765/?dialog=1&voice=1&persona=female&mobile=1&play=daily&api=http://127.0.0.1:8766
```

画面以人物为中心，顶部是互动场景，底部是手机语音/文字输入。点击人物即可互动；选择“日常、散步、安慰、晚安、专注、想你”会触发对应动作和台词；点“造型”可按角色、皮肤、动作、声音四步生成新形象。打开对话和语音时会连接本地 API 出声，手机浏览器支持语音识别时可直接按“语”说话；不支持时会尝试把录音发给本地盒子转写。点“声线”可选择女声的随身份、萝莉、御姐、搞笑女，或男声的随身份、少年、大叔、搞笑男。关闭对话时只保留静默动作。运行时请保持启动窗口打开；关闭窗口或按提示停止后，语音、记忆和模型后端也会停止。

`v0.2.20` 修复语音对话时角色把自己的 TTS 又识别成用户输入的问题；`v0.2.19` 优化手机端整体 UI 和交互：进入时有加载状态，场景按钮、聊天气泡、语音输入条和可播放状态更适合手机触控；`v0.2.18` 加入手机互动场景和云端轻量场景回复；`v0.2.17` 已根据参考图重新生成高清男女二次元 3D 角色，并接入待机、散步、奔跑、挥手、点头、回应和说话的同源 Meshy 动作文件。新流程先生成单人正面 T-pose，再进入 3D、绑定和定制动作，资源已用 Draco + WebP 压缩到移动端友好的体积；动作文件加载前才会使用程序姿态兜底。Meshy 自动 rig 目前仍主要是手掌级骨骼，不保证逐指骨骼命名，所以项目保留五指手部覆盖层作为兜底。默认背景保持透明，只有手动加 `?scene=room` 或 `?scene=night` 才显示可选场景背景。云端和本地都会直接加载 GLB 模型，加载期间不会先显示旧内置人物，加载失败时才回退到内置人物。

常用开关：

```bash
# macOS / Linux
QIBAN_DIALOG=0 QIBAN_VOICE=0 bash start-qiban.sh
QIBAN_STATIC_PORT=9000 QIBAN_API_PORT=9001 bash start-qiban.sh
```

```powershell
# Windows PowerShell
$env:QIBAN_DIALOG="0"; $env:QIBAN_VOICE="0"; .\start-qiban.ps1
```

## 4. 需要准备

- Python：推荐 3.10 或更新版本
- 网络：首次安装依赖和 Edge TTS 在线声音需要联网
- 浏览器：Chrome、Edge、Safari 均可

### 让人物真正听懂你说话（重要）

**最简单的方式——应用内绑定 Kimi**：打开右下角控制条 →「模型」→ 粘贴 API Key → 保存绑定。Key 只存在你自己浏览器里，随对话请求加密传输，之后人物就按你说的每句话实时生成回应（不再走模板）。模型可选 kimi-k2.5（推荐）/ kimi-k2.6（更强）/ moonshot-v1-8k（经典便宜）。

Key 获取：[platform.moonshot.cn](https://platform.moonshot.cn) 注册 → 充值几块 → 控制台创建 API Key（sk- 开头）。

其他两种方式：

- **整站环境变量**（本地启动）：`export QIBAN_LLM_API_KEY="你的Key"` 再跑启动脚本；Netlify 版在站点 **Site configuration → Environment variables** 加 `LLM_API_KEY`。
- **本地模型**（完全离线）：`ai-companion/project/config/settings.yaml` 的 `llm_backend` 改为 `llamacpp` 或 `ollama`。

不配 Key 也能用——自动回退内置模板（离线兜底），只是回应不按你的话生成。

压缩包不包含模型权重、历史对话数据、虚拟环境和开发日志。对外名字已经统一为「栖伴」，默认角色是「小栖」和「栖安」。

## 5. 发给手机使用

同一 Wi-Fi 下，可以把服务暴露给手机：

macOS / Linux：

```bash
QIBAN_HOST=0.0.0.0 bash start-qiban.sh
```

Windows PowerShell：

```powershell
$env:QIBAN_HOST="0.0.0.0"; .\start-qiban.ps1
```

然后在手机浏览器打开：

```text
http://电脑局域网IP:8765/?dialog=1&voice=1&mobile=1&play=daily&api=http://电脑局域网IP:8766
```

也可以直接打开云端手机版：

```text
https://qiban-companion.netlify.app/?mobile=1&dialog=1&voice=1
```
