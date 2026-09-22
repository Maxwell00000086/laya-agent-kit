# Laya 接入 Codex

可复用的多客户端安装器已整理到 [AGENT-KIT.md](AGENT-KIT.md)。新安装使用 `install.ps1` / `install.py`，同时支持 Codex、Claude Code、Cursor 和通用 MCP 配置导出。本文保留早期本机接入记录；`codex_bridge.py` 继续作为兼容入口，实际服务实现在 `agent-kit/src/laya_agent_kit/server.py`。

本地 Laya 通过 MCP 提供辅助判断，Codex 负责采集资料、整理结论、阅读截图、修改代码和验证结果。

## 使用

Codex 的全局配置注册 `laya` 服务，全局技能名称为 `$laya`。保存配置后，在 Codex 的 MCP 设置中重启该服务，或重启 Codex，再打开任务。

可直接这样提需求：

> 用 $laya 辅助整理这些 SEO 资料：按主题和相关性筛选，保留原始来源，由 Codex 对照原文汇总结论。

> 用 $laya 辅助判断这个前端问题：根据实际代码、DOM 和测试结果比较候选修复方案，由 Codex 复核并实施已授权的修改。

如果当前任务尚未刷新工具列表，技能提供同一运行时的本地命令行调用方式，无需远程 API。

## 工具

| 工具 | 输入 | 结果 |
| --- | --- | --- |
| `laya_status` | 无 | 模型缓存、已加载模型、输入限制；不加载 GPU 权重 |
| `laya_rank_passages` | 研究目标、1–16 个带来源的短片段 | 按相关性排序，保留所有来源 ID，不自动丢弃任何资料 |
| `laya_judge` | 短文本证据、1–8 个明确问题 | 分类、评分、真假概率或前端候选方案选择建议 |

默认按文本语言选英文或多语言模型；`typed-decisions` 可显式指定。使用自动路由时，问题和选项建议使用简短英文；中文原文保持中文。如问题规则本身是中文，可显式选择 `multilingual`。

服务首次推理时才加载权重，每个进程最多保留一个模型，后续同模型请求复用。语言切换可能重新加载。输出报告实际设备，便于识别 GPU 或 CPU 回退。

## 能力范围

- Laya 接收已提供的文本。它不抓取网页、不读取截图、不生成综合报告，也不会自行点击、改代码或发布。
- 英文上下文上限为 512 token，多语言和 typed-decisions 为 1024 token，问题与选项也占用预算。
- 连接层检查实际 tokenizer 预算。过长的证据、问题或选项会返回 `INPUT_TOO_LONG`，由 Codex 保留来源后分段。
- 概率和置信度没有针对本项目 SEO、前端任务校准；较高分数不代表结论已经核实。
- 资料排序帮助安排阅读顺序，不决定来源可信度、事实真假或内容是否可发布。最终综合和工程判断由 Codex 对照证据完成。

## 本地文件与复现

- 连接层：`G:\WW\laya\codex_bridge.py`
- 独立虚拟环境：`G:\WW\laya\.venv`
- Codex 配置：`C:\Users\admin\.codex\config.toml` 中的 `[mcp_servers.laya]`
- 技能：`C:\Users\admin\.codex\skills\laya\SKILL.md`
- 合成示例：`G:\WW\laya\examples\codex-seo.json`、`codex-frontend.json`
- MCP 依赖：`requirements-codex.txt`

重建环境时，在安装 Laya 后运行 `.\.venv\Scripts\python.exe -m pip install -r requirements-codex.txt`。

直接检查或运行合成示例：

```powershell
cd G:\WW\laya
.\.venv\Scripts\python.exe -X utf8 codex_bridge.py --status
.\.venv\Scripts\python.exe -X utf8 codex_bridge.py --request examples\codex-seo.json
.\.venv\Scripts\python.exe -X utf8 codex_bridge.py --request examples\codex-frontend.json
```

回归检查和真实 MCP 通信验证：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_codex_bridge.py -v
.\.venv\Scripts\python.exe -X utf8 tests\verify_codex_mcp.py
```

MCP 验证记录保存在 `.cache\verification\codex-mcp.json`。这些合成样例检查接口能运行、来源保留和基本判断方向，不代表真实资料集的准确率评测。

2026-09-22 本机验证通过：7 项输入与 token 预算测试；MCP 初始化与工具发现；英文 SEO 片段相关性排序；英文前端标签修复候选选择；中文键盘可访问性问题分类；超长输入拒绝；推理后再次查询服务状态。三个判断样例均在 CUDA 上执行。

官方依据：[Codex 连接 MCP](https://learn.chatgpt.com/docs/extend/mcp)、[Codex 技能机制](https://developers.openai.com/codex/build-skills)。
