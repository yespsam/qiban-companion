# 栖伴

栖伴是一个本地优先的 AI 伴侣原型，包含手机聊天入口、3D 桌面壁纸入口，以及可部署到随身小盒子的 FastAPI 后端。

## 一键打开

macOS 上双击：

```text
start-qiban.command
```

或者在终端运行：

```bash
./start-qiban.sh
```

启动后会打开：

- 手机聊天：`http://127.0.0.1:8765/companion-mobile-demo/`
- 3D 壁纸：`http://127.0.0.1:8765/desktop-wallpaper/`
- 本地控制台：`http://127.0.0.1:8766/`

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
