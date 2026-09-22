# 更新日志 / Changelog

本文件记录 Laya Agent Kit 的集成层和本仓库运行时改动，不代替上游 Laya 的版本记录。以下为源码更新；本项目尚未发布新的 PyPI 包或 GitHub Release。

## 2026-09-22 — 多硬件后端与安装诊断

### 新增与修复

- 安装器支持 `auto`、`cpu`、`cuda`、`rocm`、`mps`；Python、PowerShell 和网页 ChatGPT 的本地启动入口使用一致的设备选项。
- 自动模式复用现有可用的 CUDA/HIP 或 MPS，必要时回退 CPU。全新 Windows/Linux 环境检测不到 NVIDIA 时，默认选择官方 CPU 轮子；不会仅凭 AMD 显卡名称猜测 ROCm 版本。
- 新增 `python -m laya_agent_kit hardware --device auto`，无需加载模型即可检查 PyTorch 后端。
- MCP 判断、片段排序与诊断结果记录请求设备、实际后端和回退原因。显式要求 GPU 时，CPU 回退不能被报告为 GPU 验证成功。
- ROCm 通过 `torch.version.hip` 单独识别，仍使用 PyTorch 的 `cuda` 设备接口。精度选择改用 BF16 支持检测，移除 NVIDIA 架构编号对 AMD 的假设。
- 保留现有 Torch 构建；显式指定 `--torch-index-url` 时才按指定来源重装。新增硬件说明和 CI 回归检查。

### 验证与限制

- 77 项本地回归测试通过，包括 28 项新增后端、安装规划和回退测试；上游路由及决策模型测试通过。
- Windows 上 CPU 与 NVIDIA RTX 3060 的真实 MCP 推理通过，覆盖 `choice`、`score`、`noul`；复用缓存的完整离线安装流程通过。
- 三问题合成请求的单次热调用诊断值：CPU 729.3ms、CUDA 69.4ms。首次调用分别约 27.2 秒、24.5 秒，包含初始化和加载。以上不是通用性能保证或任务准确率基准。
- AMD ROCm 与 Apple MPS 已有代码路径和模拟回归测试，尚无对应硬件的实机验证。DirectML 与 ONNX 尚未实现。
- 本次本地验证不等于 GitHub CI 已通过，也不代表网页 ChatGPT 的真实隧道连接已经验证。

详见 [硬件支持](agent-kit/HARDWARE.md) 和 [验证记录](agent-kit/VALIDATION.md)。

### 如何更新

在从本仓库克隆的目录中拉取源码，再重新运行安装器，例如：

```sh
git pull --ff-only
python install.py --client codex
```

沿用原安装的客户端、虚拟环境、模型缓存目录和设备选项。安装后重连或重启对应客户端的 Laya MCP；已经运行的服务不会自动加载新代码。现有模型缓存可复用，无需重复下载已完整缓存的权重。

## 2026-09-22 — 模型切换内存修复与主动调用规则

已发布提交：[d1a7f2c](https://github.com/Maxwell00000086/laya-agent-kit/commit/d1a7f2cd5a64ba6680c5193d06b31fec7f542bd0)。

- 切换检查点前释放旧模型及未使用的 CUDA 缓存，降低同时占用两份模型内存的风险；相同模型继续复用。
- 补充缺失检查点、替换加载失败及模型复用的回归测试。
- 更新 Laya Skill 的主动调用、批量判断、会话复用和断线处理规则。模型建议仍需宿主 AI 核验。
- 实际 Codex MCP 重连及本地 CUDA 推理验证通过。
