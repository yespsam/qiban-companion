# 栖伴

栖伴是一个本地优先的 AI 伴侣原型，包含手机聊天入口、3D 桌面壁纸入口，以及可部署到随身小盒子的 FastAPI 后端。

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

启动后会打开：

- 手机聊天：`http://127.0.0.1:8765/companion-mobile-demo/`
- 3D 壁纸：`http://127.0.0.1:8765/desktop-wallpaper/`
- 本地控制台：`http://127.0.0.1:8766/`

更短的说明见 [QUICK_START.md](QUICK_START.md)，适合放进压缩包一起发给别人。

## 发行压缩包

维护者生成解压版 ZIP：

```bash
./scripts/package-release.sh v0.1.0
```

产物会生成到：

```text
dist/qiban-companion-portable-v0.1.0.zip
```

压缩包只包含可发布源码、启动脚本、静态资源和说明文档，不包含 `.git`、虚拟环境、运行日志、历史对话数据、测试截图或旧备份。

别人使用时从 GitHub Releases 下载 `qiban-companion-portable-v0.1.0.zip`，解压后按系统双击启动即可。

## 云端静态入口

仓库根目录的 `index.html` 可直接用于 GitHub Pages / Netlify / 任意静态服务器。

云端静态页面负责展示手机聊天和 3D 壁纸界面；真实语音、记忆和模型服务请连接本地电脑或随身小盒子的 `8766` 后端。

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
