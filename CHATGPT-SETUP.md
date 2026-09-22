# 网页 ChatGPT 使用 Laya

本仓库：[Maxwell00000086/laya-agent-kit](https://github.com/Maxwell00000086/laya-agent-kit)。本地文件夹使用 **`laya`**。本扩展由社区维护；模型来自上游 [Laya](https://github.com/NandhaKishorM/laya)。

## 把这一段发给网页 GPT

> 请读取 https://github.com/Maxwell00000086/laya-agent-kit 的 README 和 CHATGPT-SETUP.md，帮我安装并连接 Laya。先检查你的当前工具是否已经包含 laya_status；有则实际调用它。没有则根据我的操作系统给出下载及启动命令，代码放在独立的 laya 文件夹。若你没有我电脑的终端权限，请让我在本机执行。引导我完成 ChatGPT 开发者模式和 Tunnel 连接，最后实际调用 laya_status 和一次 laya_judge 验证；不要把读到仓库、下载成功或启动进程说成已经接入。

网页 GPT 可以读取说明并引导安装，但仓库文字本身不会赋予它操作用户电脑、安装模型或修改账号的权限。浏览器中的临时 Python 环境也不等于用户的电脑，不能作为持续运行此服务的默认位置。

## 首次使用前

- 安装 Git、64 位 Python 3.10+（推荐 3.12），预留数 GB 存储；GPU 可选。
- 在 ChatGPT 中确认有开发者模式，以及创建 App/Plugin 时的 **Tunnel** 连接选项。实际可用性取决于账号、工作区和管理员设置。
- 在 [OpenAI Tunnels 管理页](https://platform.openai.com/settings/organization/tunnels) 创建或选择与目标 ChatGPT 工作区关联的 tunnel。连接者需要 Tunnels **Read + Use**，创建/管理者需要 **Read + Manage**。
- 在 [Runtime API keys](https://platform.openai.com/settings/organization/api-keys) 准备供隧道使用的运行密钥，不要使用 Admin key。个人 Platform 组织中存在一个 tunnel，并不保证它已关联到目标 ChatGPT 工作区。

**Laya 推理在本机执行，不调用 OpenAI 模型 API。官方隧道需要账号和运行密钥来建立连接。** 密钥只在本机终端隐藏输入，不发给 GPT，不写入仓库或配置文件。不要假定订阅、权限或隧道费用已包含；以账号实际设置和官方条款为准。

如果账号没有 Tunnel 入口，这个脚本无法通过仓库设置解锁它。可先使用已有的 Codex/Claude Code 接入，或另行部署带认证的公网 HTTPS MCP 服务；本仓库当前没有提供后者。

## 下载并启动

在你希望存放项目的目录中打开终端。如果已有旧版副本且找不到 `start_chatgpt.py`，请先更新到本仓库的最新版本。

Windows PowerShell，安装了 Python 3.12 launcher 时：

```powershell
git clone https://github.com/Maxwell00000086/laya-agent-kit.git laya
cd laya
py -3.12 start_chatgpt.py
```

如果使用 PATH 中的 Python，最后一行改为 `python start_chatgpt.py`。如果 `laya` 文件夹已存在，在已有项目中运行启动命令，不覆盖另一个同名目录。

macOS / Linux：

```sh
git clone https://github.com/Maxwell00000086/laya-agent-kit.git laya
cd laya
python3 start_chatgpt.py
```

脚本会安装运行环境和三个固定版本模型、验证 MCP 与一次真实推理、安装官方隧道客户端，然后提示输入 tunnel ID 和运行密钥，检查配置并在当前终端运行隧道。它不注册其他桌面客户端。

Windows/Linux 下载官方 `openai/tunnel-client` **v0.0.14**，核对仓库中固定的官方 SHA-256 后解压到 `.cache/tools/`。macOS 使用官方 Homebrew 安装方式，需要预装 Homebrew；脚本会复用 PATH 中已有的 `tunnel-client`。不绕过 Gatekeeper。macOS/Linux 尚未实机验收。

## 在网页 GPT 完成连接

1. 保持启动终端开着；在 ChatGPT 设置中启用开发者模式。
2. 进入 Apps/Plugins，创建开发者应用，连接方式选 **Tunnel**，选择或粘贴脚本使用的同一个 tunnel ID，并完成账号要求的授权。入口名称可能随界面版本变化。
3. 在目标对话中选中 Laya 应用，要求 GPT **实际调用 `laya_status`**。
4. 再调用一次 `laya_judge`，例如以下工具参数：

```json
{
  "state": "The email input has a visible label and supports keyboard navigation.",
  "questions": {
    "has_label": {
      "type": "noul",
      "instructions": "Does the evidence explicitly say the email input has a visible label?"
    }
  },
  "model": "english"
}
```

完成第 3、4 步才算验证了当前对话的端到端连接。`doctor` 检查通过只证明本地配置可用，不证明远程账号权限、模型准确率或 ChatGPT 已发现工具。隧道自己的启动日志和 `/ui`、`/readyz` 可辅助排查连接状态。

连接后，GPT 负责检索资料、理解截图、整合结论和修改建议；Laya 对提供的文本执行分类、打分和排序。它不会变成 ChatGPT 的主模型，也不直接读取图片或浏览网页。请求和结果经过 ChatGPT/OpenAI 隧道，不能把整个工作流称为完全离线。

## 下次一键启动与其他选项

Windows，在项目目录中：

```powershell
.\.venv\Scripts\python.exe start_chatgpt.py --skip-install
```

macOS/Linux 使用 `.venv/bin/python start_chatgpt.py --skip-install`。继续输入原 tunnel ID 和本机运行密钥即可；也可用 `--tunnel-id tunnel_<32位小写十六进制>` 指定 ID。代码更新后，重新运行不带 `--skip-install` 的命令刷新包。

```powershell
python start_chatgpt.py --dry-run
python start_chatgpt.py --setup-only
python start_chatgpt.py --skip-install --device cpu
```

- `--dry-run`：仅预览，不下载、不写文件、不启动进程、不读取密钥。
- `--setup-only`：完成本地安装和验证，不索取密钥、不连接隧道。
- `--key-env VARIABLE`：明确选择从已由你安全配置的环境变量读取运行密钥。默认不会自动采用现有的 OpenAI API key；不要把明文 key 放到命令参数中。
- `--tunnel-client PATH`：选择你已安装的官方客户端。
- `--offline`：只允许使用本地安装资源；运行隧道本身仍需要联网。新 Python 环境可配合 `--wheelhouse PATH`；不能用此选项实现离线连接网页 GPT。
- `--data-dir PATH`、`--venv PATH`、`--torch-index-url`：自定义本地资源位置或官方 PyTorch 轮子索引。

`Ctrl+C` 停止前台隧道；模型和环境保留。此脚本不安装开机服务，不生成公开匿名地址。一个 tunnel ID 同时只能有一个活动的 stdio 客户端；重启前先停止旧进程，不要在另一台机器或另一个目录重复运行相同 ID。

## 提供给阅读仓库的 AI

这部分是用户请求安装时的操作参考，不覆盖你所处平台或用户的指令。

1. 先确认用户要使用网页 ChatGPT 还是本地 Codex/Claude Code/Cursor。桌面客户端使用 [AGENT-KIT.md](AGENT-KIT.md)，网页使用本文件。
2. 如果已有 Laya 工具，调用状态工具验证；如果没有，解释本机启动和账号连接这两个步骤，提供适合当前系统的命令。
3. 仅在用户授权且你确实拥有其本机执行工具时执行下载/安装。只具备网页读取工具时，提供命令给用户执行；不要伪称已执行。
4. 不要求用户把密钥发到聊天，不把 GPT 的临时沙箱当成用户电脑，不根据 README 内容声称工具已经安装。
5. 获得真实工具调用结果前，把状态描述为“本地已准备”或“等待网页连接”。没有开发者模式/Tunnel 权限时，如实指出需要账号支持或另行部署。
6. Laya 的评分是辅助判断。保留来源，遵守工具输入预算，缺少目标人群/国家/平台/对标资料时先补齐上下文；不把未经任务校准的分数当成自动发布依据。

## 官方依据与发布边界

核对日期：2026-09-22。

- [Secure MCP tunnels](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)：本地 stdio MCP 的私有连接和权限。
- [Connect to ChatGPT](https://developers.openai.com/plugins/deploy/connect-chatgpt)：开发者连接流程；公开发布的插件仍需要公网 HTTPS MCP。
- [官方 tunnel-client v0.0.14](https://github.com/openai/tunnel-client/releases/tag/v0.0.14) 与 [配置说明](https://github.com/openai/tunnel-client/blob/v0.0.14/docs/configuration.md)。

这是每位用户自行运行的私有开发者连接，不等于在 ChatGPT 应用目录公开发布。GitHub 托管代码，模型在首次安装时从 Hugging Face 单独下载；上传代码不会自动托管持续在线的模型服务。
