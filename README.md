# 栖伴

栖伴是一个本地优先的 AI 伴侣原型，打开后直接进入拟人化二次元 3D 角色画面，可部署到电脑、手机浏览器或随身小盒子上的 FastAPI 后端。

当前 `v0.2.14` 版本包含高清男女 3D 角色模型、男女各 3 套皮肤、分步造型生成面板、参数化动作节奏（温柔/元气/稳重）、云端/本地真实语音声线选择和移动/桌面自适应构图。动作系统已重做：待机、散步、奔跑、挥手、点头、回应、转身和说话都使用新的表演骨架，统一处理呼吸、重心、肩胯、膝脚、头颈视线、手腕细节和动作淡入淡出；walk/run 不再使用第一版模型原生动画，而是使用正面可见的全身重心步态。`v0.2.14` 还合入了优化包里的 WebP 纹理版 GLB 和离线解码器，模型资源体积约减半，手机端打开会更快。默认背景保持透明，只有手动加 `?scene=room` 或 `?scene=night` 才显示可选场景背景。云端模型会直接加载 GLB，加载期间不会先显示旧内置人物，根入口和旧手机 demo 入口都会进入新版 3D 人物页。

## 一键打开

解压版适合直接发给别人用。对方只需要安装 Python，下载 ZIP，解压后运行对应入口。

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

首次启动会自动创建虚拟环境并安装核心依赖，需要联网；后续启动会直接复用本地环境。

启动后会打开一个纯人物入口：

```text
http://127.0.0.1:8765/?dialog=1&voice=1&persona=female&api=http://127.0.0.1:8766
```

画面只保留人物和底部角色/造型/对话/声线开关。点击人物即可互动；点“造型”可按角色、皮肤、动作、声音四步生成新形象。`dialog=1&voice=1` 时会连接本地 API 生成真实语音，点“声线”可切换女声的随身份、萝莉、御姐、搞笑女，或男声的随身份、少年、大叔、搞笑男。`dialog=0&voice=0` 时只保留静默动作。默认不会使用浏览器自带机械朗读，未接入真实语音时按钮会显示“语音未接”。

端口和开关可通过环境变量调整：

```bash
QIBAN_STATIC_PORT=9000 QIBAN_API_PORT=9001 QIBAN_DIALOG=1 QIBAN_VOICE=1 QIBAN_PERSONA=female bash start-qiban.sh
```

也可以直接在 URL 中指定 API：

```text
http://127.0.0.1:8765/?api=http://127.0.0.1:8766
```

更短的说明见 [QUICK_START.md](QUICK_START.md)，适合放进压缩包一起发给别人。

## 发行压缩包

维护者生成解压版 ZIP：

```bash
./scripts/package-release.sh v0.2.14
```

产物会生成到：

```text
dist/qiban-companion-portable-v0.2.14.zip
```

压缩包只包含可发布源码、启动脚本、静态资源和说明文档，不包含 `.git`、虚拟环境、运行日志、历史对话数据、测试截图或旧备份。

别人使用时从 GitHub Releases 下载 `qiban-companion-portable-v0.2.14.zip`，解压后按系统双击启动即可。

## 云端静态入口

仓库根目录的 `index.html` 可直接用于 GitHub Pages / Netlify / 任意静态服务器。

Netlify 云端入口已经内置同源真实语音函数，打开对话后会直接生成 MP3，不再使用浏览器机械朗读。连接本地电脑或随身小盒子时，也可以指定 API 地址，例如 `?api=http://设备IP:8766&dialog=1&voice=1`。

如果只是临时调试浏览器朗读，可手动加 `browserVoice=1`，但正式陪伴模式建议保持关闭，避免听到机械声。

## 角色名

默认产品名：栖伴  
女声角色：小栖  
男声角色：栖安

可在这里修改：

```text
ai-companion/project/config/settings.yaml
ai-companion/project/config/personas/
```

## 随身小盒子

部署说明见：

```text
ai-companion/project/docs/POCKET_BOX.md
```
