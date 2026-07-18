# 栖伴解压版使用说明

这是给非开发者使用的便携包。下载 ZIP 后不需要 Git，也不需要手动找代码入口。

## 1. 解压

把 `qiban-companion-portable-v0.1.1.zip` 解压到一个普通文件夹，例如桌面或文档目录。

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

启动成功后会自动打开：

- 手机聊天：`http://127.0.0.1:8765/companion-mobile-demo/`
- 3D 角色壁纸：`http://127.0.0.1:8765/desktop-wallpaper/`
- 本地控制台：`http://127.0.0.1:8766/`

运行时请保持启动窗口打开。关闭窗口或按提示停止后，语音、记忆和模型后端也会停止。

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
http://电脑局域网IP:8765/companion-mobile-demo/
```
