# Laya 本地安装

项目目录：`G:\WW\laya`。

这是 Python 决策模型 SDK，没有随仓库提供的本地网页服务。
源码来自 https://github.com/NandhaKishorM/laya，采用独立 `.venv` 环境安装。

安装版本为 Laya `0.3.5`，源码提交 `573e5b62696ba441230cd6be71d593331b5d23af`。
依赖包括 PyTorch `2.14.0+cu130`、Transformers `5.17.0`；完整依赖版本快照见 `.cache\installed-requirements.txt`。

## 运行

在 PowerShell 中执行，无需激活虚拟环境：

```powershell
cd G:\WW\laya
.\.venv\Scripts\python.exe -X utf8 .\local_demo.py --offline
```

默认输入中文，自动选择多语言模型。自定义输入：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\local_demo.py --offline --text "I was charged twice. Please refund me."
```

验证三个模型，或指定 CPU：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\local_demo.py --offline --all-models
.\.venv\Scripts\python.exe -X utf8 .\local_demo.py --offline --device cpu
```

可用模型参数：`--model auto`、`english`、`multilingual`、`typed-decisions`。
默认自动使用可用的 CUDA GPU。示例输出包含实际推理设备、路由信息，以及分类、评分和真假概率结果。
`typed-decisions` 针对其训练任务微调；示例结果仅用于确认模型可运行，不是业务准确率验收。

## 本地文件

- `.venv`：项目专用 Python 环境和依赖。
- `.cache\huggingface`：Hugging Face 模型权重及 tokenizer 缓存。
- `.cache\pip`：安装包缓存。
- `.cache\wheels`：经过 SHA256 校验的 CUDA 版 PyTorch 安装包。
- `local_demo.py`：本地中英文推理示例。

缓存通过本仓库 `.git/info/exclude` 排除，不进入版本管理。
示例中的 `--offline` 使用已下载权重；去掉该参数可联网下载缺失模型。
自行编写脚本时，在导入 `laya` 之前将 `HF_HOME` 设为 `G:\WW\laya\.cache\huggingface`，以复用本地缓存。

## 环境重建

当前虚拟环境使用 Codex 自带的 Python 3.12.14：
`C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`。
虚拟环境依赖该基础解释器；如果该运行时被移除，请使用已安装的 Python 3.10 或更新版本重新创建 `.venv`。

本机安装使用 NVIDIA RTX 3060 与 CUDA 13.0 版 PyTorch：

```powershell
$env:PIP_CACHE_DIR = 'G:\WW\laya\.cache\pip'
.\.venv\Scripts\python.exe -m pip install 'torch==2.14.0+cu130' --index-url https://download.pytorch.org/whl/cu130
.\.venv\Scripts\python.exe -m pip install -r .cache\installed-requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -X utf8 .\local_demo.py --all-models
```

此安装无需 API Key。模型推理在本机运行。

## 模型来源

三个模型均来自 `convaiinnovations/laya`，模型仓库版本为
`1c5edc17a7acd8701df6fc341c0d179f1c62c982`：根目录英文模型、`multilingual` 多语言模型和 `typed-decisions` 微调模型。
本地下载使用 Hugging Face 官方地址，权重按仓库记录的 SHA256 校验。

## 已完成验证

2026-09-22 在本机验证：

- `pip check` 通过，CUDA 可用，设备为 NVIDIA GeForce RTX 3060。
- 路由、criteria、shortlist、decision model、packaging、email 六组自带测试通过。
- 三个模型均成功在 CUDA 上离线推理，返回 `choice`、`score` 和 `noul` 结果。
- 中文自动路由到 `multilingual`，英文自动路由到 `english`，显式 `typed-decisions` 选择正常。
- 推理日志保存在 `.cache\verification`。

英文和 typed-decisions 模型加载时会出现上游关于 `choice:11+` 温度校准值的警告；库会限制该值，推理仍正常完成。该警告涉及相关题型的置信度校准，不代表安装失败。

## Codex 集成

已增加本地 MCP 连接层和 `$laya` 技能，支持 Codex 调用 Laya 辅助进行 SEO 资料排序与前端文本判断。使用方式、能力范围和验证命令见 [CODEX-INTEGRATION.md](CODEX-INTEGRATION.md)。
