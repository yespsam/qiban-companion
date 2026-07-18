# 参与共建 · Contributing

感谢你愿意为 栖伴 出一份力！本文档约定分支、提交与测试规范，
让协作保持简单、可预期。

## 0. 先读规格

`SPEC.md` 是项目的**单一事实来源**：模块边界、接口签名、数据格式都以它为准。
任何与 SPEC 冲突的实现都需要先在 Issue 中讨论并更新 SPEC，再动代码。

## 1. 分支规范

- `main`：稳定分支，只接受 PR 合入，禁止直接推送。
- 功能分支：`feat/<模块>-<简述>`，例如 `feat/cluster-router`、`feat/voice-barge-in`。
- 修复分支：`fix/<模块>-<简述>`，例如 `fix/registry-atomic-write`。
- 文档分支：`docs/<简述>`。
- 一个分支只做一件事；大功能先拆 Issue 再拆 PR。

## 2. 提交规范

采用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)，描述用中文：

```
<type>(<scope>): <一句话说明>

[可选正文：动机、方案取舍、关联 Issue]
```

- type：`feat` / `fix` / `docs` / `test` / `refactor` / `chore` / `perf`
- scope：模块名，如 `core`、`voice`、`devices`、`cluster`、`ui`、`installer`、`docs`
- 示例：
  - `feat(cluster): 节点注册表原子写入与 ttl 过滤`
  - `fix(engine): parse_thinking 容忍未闭合的 <think> 标签`
  - `test(cluster): 覆盖 local_first 选点策略`

## 3. 代码规范

- Python ≥ 3.10，全平台（Windows / macOS / Linux / 树莓派 64 位）都必须可用：
  不用平台专属 API，路径一律 `pathlib`。
- **懒加载铁律**：torch、whisper、TTS 引擎、bleak、miio 等重依赖只能在函数内部 import；
  模块顶层只允许轻量 import（标准库 + 核心依赖）。
  无 GPU / 无音频 / 无蓝牙的环境必须能 import 全项目。
- 日志统一走 `core.logging_utils.get_logger(__name__)`，禁止 `print` 调试入库。
- 运行时数据只写项目内 `data/`（尊重 `HERMES_HOME`），禁止写项目外路径。
- 类型标注：公开接口必须标注；注释与 docstring 用中文。

## 4. 测试规范

- 运行方式：`pytest tests/ -q`；提交前必须本地全绿。
- **离线可跑**：测试必须在无 GPU、无模型、无音频/蓝牙硬件、**无网络**的环境通过——
  所有 HTTP（含 httpx）、硬件与重依赖调用一律 mock / monkeypatch。
- 新行为必配新测试；bugfix 必须先写复现用例再修。
- 文件落盘一律用 `tmp_path` 等临时目录，不得依赖开发者机器状态。
- 各模块必测点见 `SPEC.md` §6（人格铁律、`parse_thinking`、情绪加减分、
  记忆增删查与降级、意图模板 ≥12 条、集群选点、配置读写往返）。

## 5. PR 流程与检查清单

1. Fork / 分支开发 → 自测 → 提交 PR 到 `main`，描述写清「做了什么 / 为什么 / 怎么测的」。
2. PR 检查清单：
   - [ ] 符合 SPEC.md 的接口契约（或已在 PR 中说明并同步更新 SPEC）
   - [ ] `pytest tests/ -q` 全绿（含新增用例）
   - [ ] 无顶层重依赖 import；`python -c "import <你的模块>"` 在裸环境成功
   - [ ] 未写入项目外路径；未引入未声明的新依赖（新依赖需更新 requirements 注释）
   - [ ] 公开行为变化已更新 docs/ 相应文档
3. 至少一名维护者 review 通过后合入（Squash merge，保持 main 历史干净）。

## 6. 行为准则

友善、尊重、对事不对人。本项目是情感陪伴软件，讨论中请特别注意：
不嘲讽用户情感需求、不歧视任何使用群体、涉及心理健康话题保持专业与克制。

## 7. 在哪里帮忙

- 好的第一步：标记 `good first issue` 的 Issue、补充测试、完善文档翻译。
- 长期共建：栖伴集群协议与节点实现（见 [OPEN_SOURCE.md](OPEN_SOURCE.md)）、
  人格 LoRA 数据与训练、语音链路体验优化。
