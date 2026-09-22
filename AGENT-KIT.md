# Laya Agent Kit：一条命令安装并接入 AI

这套扩展复用了本机已验证的 Laya 接入，把运行环境、模型下载、MCP 注册和使用技能整理为可重复安装的工具。项目继续独立位于 `laya` 文件夹，新增代码集中在 `agent-kit/`。

支持 Codex、Claude Code、Cursor；其他支持本地 stdio MCP 的客户端可以导入生成的 JSON。LLM API 本身不能启动本机服务，需要由支持工具调用的客户端或 Agent 接入。

**网页 ChatGPT** 使用新增的 `python start_chatgpt.py`，通过官方私有 MCP Tunnel 连接本机 Laya。下载命令、首次账号步骤和给 GPT 的引导语见 [CHATGPT-SETUP.md](CHATGPT-SETUP.md)。

## Windows 安装

在项目根目录打开 PowerShell：

```powershell
.\install.ps1 -Client codex,claude-code
```

只接入一个客户端：

```powershell
.\install.ps1 -Client codex
.\install.ps1 -Client claude-code
.\install.ps1 -Client cursor
```

先预览，遇到现有同名配置时查看冲突：

```powershell
.\install.ps1 -Client codex,claude-code -DryRun
```

确认需要更新旧的 Laya 接入时，加 `-Replace`。安装器会备份配置和旧技能，保留其他 MCP、模型设置和客户端配置。

如果系统阻止运行 `.ps1`，可以直接调用 Python，不需要调整系统执行策略：

```powershell
python install.py --client codex --client claude-code
```

本机已有 Python 虚拟环境，也可直接使用：

```powershell
.\.venv\Scripts\python.exe -X utf8 install.py --client codex --client claude-code
```

## 前提与安装内容

- 已安装 64 位 Python 3.10+，推荐 3.12；目标 AI 客户端需要事先安装。
- 首次安装需要联网下载依赖和模型，预留数 GB 磁盘空间。安装后推理离线，不需要 API Key。
- 根目录 `.venv/` 保存独立 Python 环境，`.cache/` 保存模型和安装记录。
- 默认下载固定版本的英文、多语言、typed-decisions 三个模型；已有完整缓存直接复用。
- 安装完成前实际检查 MCP 初始化、工具发现及一次模型推理；失败则不写客户端注册。
- Codex 和 Claude Code 同时安装 `laya` 技能，指导资料筛选、来源保留和前端判断；其他客户端依靠 MCP 工具说明。
- 不替换 AI 客户端自己的主模型。主 AI 负责检索、阅读截图、资料整合和代码修改，Laya 提供短文本分类、打分和排序。

安装完成后重新连接 MCP 或重启客户端，再要求它调用 `laya_status`。部分客户端首次接入项目 MCP 时会弹出自身的信任确认。

## 其他系统与高级选项

macOS/Linux 使用同一个 Python 安装入口：

```sh
python3 install.py --client codex --client claude-code
```

当前实现提供跨平台路径和安装逻辑；本次真实设备验收在 Windows 完成，macOS/Linux 尚未实机验证。

仅导出其他 MCP 客户端可导入的配置：

```powershell
.\install.ps1 -Client generic
```

生成 `.cache/exports/mcp.json`。里面包含当前机器的绝对路径，换机器或移动项目后应重新运行安装器。

更多选项通过 Python 入口使用：

```powershell
.\.venv\Scripts\python.exe install.py --client codex --project 'D:\my-project'
.\.venv\Scripts\python.exe install.py --client cursor --device cpu
.\.venv\Scripts\python.exe install.py --client codex --models english multilingual
```

`--device auto` 优先复用现有可用 CUDA/ROCm，其次 MPS，最后 CPU；推理结果显示实际后端和回退原因。支持显式选择 `cpu`、`cuda`、`rocm`、`mps`。显式要求 GPU 时，CPU 回退不能被当作验证成功。

全新 Windows/Linux 环境检测不到 NVIDIA 时默认安装 CPU 轮子；A 卡可以先通过 CPU 使用。AMD GPU 加速要求按官方兼容矩阵配置 ROCm/PyTorch，再运行 `python install.py --client codex --device rocm`；安装器不会只凭 A 卡名称猜测 ROCm 版本。已有 Torch 默认保留，只有显式传入 `--torch-index-url` 才重装指定来源的 Torch。PowerShell 入口支持 `-Device` 和 `-TorchIndexUrl`。

新增 `python -m laya_agent_kit hardware --device auto` 查看后端；`doctor --inference` 执行真实验证。当前 CPU、NVIDIA 有实机验证，AMD/MPS 需要相应机器验证；DirectML/ONNX 尚未实现。详见 [硬件支持与验证范围](agent-kit/HARDWARE.md)，不承诺所有 CPU 都能达到 20–60ms。

完全离线安装使用 `--offline`，需要提前备好模型缓存和兼容 Python 依赖；新环境可通过 `--wheelhouse` 指定本地轮子目录。离线安装不会联网补齐缺失资源。

## 检查、更新和卸载

```powershell
.\.venv\Scripts\python.exe -m laya_agent_kit doctor --data-dir .cache --client codex --client claude-code --inference
.\.venv\Scripts\python.exe -m laya_agent_kit download --data-dir .cache --models multilingual
.\.venv\Scripts\python.exe -m laya_agent_kit uninstall --data-dir .cache --client claude-code
```

更新本地源码后，重新运行安装入口即可更新安装包。相同参数重复安装不会重复添加配置。诊断命令默认检查三个模型，部分模型安装时应传入相同的 `--models`。

卸载只撤销本次工具管理的接入与技能，并恢复被替换的旧版 Laya 项；保留模型、运行环境和备份。它不会抹掉其他服务器或后续无关设置。如果管理的 Laya 项或技能已被人工修改，卸载会停止并提示，不覆盖这些修改。

安装记录位于 `.cache/integrations/`；不要在卸载前删除。配置备份在原文件旁，名称包含 `.laya-backup-`。备份可能含原客户端的敏感配置，应留在本机。

## 使用示例与限制

> 用 Laya 按相关性排列这些 SEO 资料，保留来源，由你对照原文整合结论。

> 用 Laya 辅助比较这个前端问题的几个修复方案，结合代码和浏览器证据复核。

Laya 不抓取网页、不看图片、不写综合报告，也不执行候选动作。英文上下文 512 token，其他两个模型 1024 token，超长输入会明确拒绝。分数不代表任务准确率，合成检查不代表真实业务评测。

源码、客户端默认路径和协议参考见 [agent-kit/README.md](agent-kit/README.md)。根目录原版 Laya 的许可证及作者信息保持保留；README 的接入入口、根目录安装脚本和 `agent-kit` 是本扩展的新增/修改部分。从 [GitHub 仓库](https://github.com/Maxwell00000086/laya-agent-kit) 下载并安装；本项目尚未将集成工具发布到 PyPI。

## 相关项目的取舍

已核对 `laya-ultrafast`、`arbiter` 和 `laya-playground` 的源码及许可证，具体版本与依据见 [REFERENCES.md](agent-kit/REFERENCES.md)。

- `laya-ultrafast` 用于 Mac 浏览器 Agent，依赖 Apple Silicon 的 MLX；默认仍调用一次远程文本模型做任务规划，只有配置本地文本模型后这部分才无 API 费用。
- `arbiter` 适合共享 HTTP 服务、Jev API 兼容和并发批处理。它的 MCP SDK 版本与当前环境不同，安全钩子还会改变 Claude 的权限行为，因此本安装器不自动安装这些部分。
- `laya-playground` 的提问与评估经验已整理进本 kit 的技能：问可观察事实、明确选项含义、按语言选模型、用真实标注数据验证阈值。其示例性能及校准结论不作为本项目的准确率承诺。

本地客户端使用直接 stdio MCP；网页 ChatGPT 的新增入口通过官方私有 Tunnel 复用同一服务。HTTP/Jev 服务、Apple MLX 浏览器 Agent 和工具权限钩子均属于后续独立扩展。

## 本机交付状态

2026-09-22：Codex 原有连接入口保留，Claude Code 已新增用户级 `laya` MCP 与技能，`claude mcp list` 返回 `Connected`。本机两个接入都通过实际 MCP 检查，无须重新安装即可使用。若今后要把 Codex 旧入口也迁移到统一管理的安装项，可运行 `.\install.ps1 -Client codex -Replace`。

已验证 24 项安装/诊断回归、7 项桥接回归、CPU/GPU 真实推理、四种生成配置的 MCP 启动、完整缓存离线安装和卸载恢复。Mac/Linux 尚未实机验证；上游 Windows 下载测试存在路径断言问题。完整依据与复现命令见 [VALIDATION.md](agent-kit/VALIDATION.md)。
