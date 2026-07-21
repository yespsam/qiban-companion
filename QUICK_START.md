# 栖伴解压版使用说明

这是给非开发者使用的便携包。下载 ZIP 后不需要 Git，也不需要手动找代码入口。

## 1. 解压

把 `qiban-companion-portable-v0.2.10.zip` 解压到一个普通文件夹，例如桌面或文档目录。

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
http://127.0.0.1:8765/?dialog=1&voice=1&persona=female&api=http://127.0.0.1:8766
```

画面只保留人物和必要的角色/造型/对话/声线控制。点击人物即可互动；点“造型”可按角色、皮肤、动作、声音四步生成新形象。打开对话和语音时会连接本地 API 出声，点“声线”可选择女声的随身份、萝莉、御姐、搞笑女，或男声的随身份、少年、大叔、搞笑男。关闭对话时只保留静默动作。运行时请保持启动窗口打开；关闭窗口或按提示停止后，语音、记忆和模型后端也会停止。

`v0.2.10` 已内置高清男女二次元 3D 角色、男女各 3 套皮肤、温柔/元气/稳重动作节奏和真实语音声线选择，旧手机 demo 入口也会自动进入新版 3D 人物页。动作已切回第二版：走路和奔跑使用干净骨骼基准上的协调步态，不再使用第一版模型原生 walk/run 动画；待机、挥手、点头、回应和说话也使用同一套第二版骨骼控制。云端和本地都会直接加载 GLB 模型，加载失败时才回退到内置人物。第一次打开时模型文件较大，等待几秒加载完成即可。

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
http://电脑局域网IP:8765/?dialog=1&voice=1&api=http://电脑局域网IP:8766
```
