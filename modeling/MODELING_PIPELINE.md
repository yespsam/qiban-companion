# 栖伴 3D 建模管线

当前 Three.js 几何角色只是占位原型，不再作为正式形象路线。

## 选型结论

优先路线：Meshy 3D Generation skill

- 适合从设计图生成 GLB/FBX。
- 支持贴图、PBR、自动绑定和基础动作。
- 需要 `MESHY_API_KEY`，API key 通常需要 Pro 或以上账号。

备选路线：Hunyuan3D-2.1

- 开源，适合 image-to-3D 和 PBR 资产生成。
- 官方说明完整形状 + 贴图本地运行约需 29GB VRAM；本机不适合作为默认本地构建。
- HuggingFace Space 可作为免费试跑渠道，但队列和连接稳定性不可控。

动漫人形最终生产路线：VRM / VRoid

- 如果要稳定的二次元拟人角色、面捕、动作和网页实时加载，最终资产应整理成 VRM 或标准 GLB。
- VRoid Studio 适合手工精修动漫人形；Meshy/Hunyuan 适合先出 3D 草模和贴图参考。

## 本项目目标文件

正式资产放在：

```text
desktop-wallpaper/assets/models/xiao-qi.glb
desktop-wallpaper/assets/models/qi-an.glb
```

建模参考图放在：

```text
modeling/reference/xiao-qi-front-clean.png
modeling/reference/xiao-qi-back.png
modeling/reference/qi-an-front.png
modeling/reference/qi-an-back.png
```

## Meshy 生成命令

先设置 API key：

```bash
export MESHY_API_KEY="msy_your_key_here"
```

只看计划和预计点数：

```bash
python3 tools/generate_meshy_companion_models.py --characters female male --rig
```

确认消耗点数并真正生成：

```bash
python3 -u tools/generate_meshy_companion_models.py --characters female male --rig --yes
```

生成完成后，脚本会下载 GLB/FBX 到 `meshy_output/`，并把最终 GLB 复制到 `desktop-wallpaper/assets/models/`。

默认使用 GitHub Raw 上的公开参考图 URL，避免大图 base64 上传超时。若必须使用本地图片，可追加 `--use-data-uri`。

## 建模要求

- 风格：高质量二次元拟人，非 Q 版，非低模玩具感。
- 比例：真实头身，女款约 7 头身，男款约 7.5 头身。
- 姿态：优先 T-pose 或 A-pose，方便后续自动绑定。
- 服装：黑绿科技感外套、白色内搭、金属链饰、透明绿色发光材质。
- 表情：温柔、近距离陪伴感，不做夸张卡通脸。
- 输出：GLB 用于网页；FBX 用于 Mixamo/Blender/VRoid 后续修骨骼和动作。
