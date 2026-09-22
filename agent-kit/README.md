# Laya Agent Kit

Local Laya decision tools for Codex, Claude Code, Cursor and other clients that support MCP over stdio. This community integration extends [Laya](https://github.com/NandhaKishorM/laya); it is not an official OpenAI or Anthropic product.

The host AI gathers evidence and writes the final answer. Laya ranks supplied research passages and answers bounded questions over text. It does not browse, read screenshots or execute model-selected actions.

For **web ChatGPT**, run `python start_chatgpt.py` from the repository root and follow [CHATGPT-SETUP.md](../CHATGPT-SETUP.md). This uses the official private MCP Tunnel with the existing stdio server. It requires developer mode, a workspace-associated tunnel and a runtime key entered locally. `--setup-only` verifies local readiness without connecting an account. This is not a publicly hosted ChatGPT plugin.

## Install from this checkout

From the repository root, with 64-bit Python 3.10+ (3.12 recommended):

```sh
python install.py --client codex --client claude-code
```

Windows PowerShell can find an existing local environment or Python launcher:

```powershell
.\install.ps1 -Client codex,claude-code
```

The installer creates/reuses the checkout's `.venv`, installs both local packages, downloads three pinned checkpoints into `.cache`, verifies MCP and one real inference, then registers the selected clients. The AI clients must already be installed. Initial setup needs network access and several GB of disk space; inference is offline. A GPU is optional.

Select `--client cursor` for Cursor, or `--client generic` to create `.cache/exports/mcp.json` for manual import. Repeat `--client` to select multiple targets. Only clients with local stdio MCP support can use this installation; a bare model API or remote chat UI cannot launch a local process by itself.

No package has been published to PyPI by this project. Install from the checkout, not by assuming `pip install laya-agent-kit` resolves to this code. The package in this directory is separately buildable; when installed alone it depends on `laya==0.3.5`.

## Management

Use the installed environment's Python if its commands are not on PATH:

```sh
.venv/bin/python -m laya_agent_kit doctor --data-dir .cache --inference
.venv/bin/python -m laya_agent_kit install --data-dir .cache --client codex --dry-run
.venv/bin/python -m laya_agent_kit uninstall --data-dir .cache --client codex
```

On Windows replace `.venv/bin/python` with `.\.venv\Scripts\python.exe`.

- `--dry-run` writes no configuration and downloads no models. The bootstrap also skips dependency installation in this mode.
- Existing unrelated settings and servers are preserved; TOML comments are retained. Conflicting Laya registrations or skills require `--replace`, which creates timestamped backups.
- Repeating an installation with the same paths/options leaves configuration files unchanged.
- `--project PATH` uses project configuration. Claude Code may ask the user to approve the project's MCP server.
- `--config PATH` targets a custom config for one client. Use `--no-skill` if only that configuration file should be affected.
- `--user-home PATH` redirects client configuration/skills for isolated validation. `--data-dir` selects the model cache and installation records.
- `--offline` requires cached models and Python dependencies. Bootstrap offline provisioning accepts `--wheelhouse PATH`; its wheels must match the target platform/Python. It needs setuptools and wheel as well as runtime dependencies.
- `--models english multilingual` downloads/checks only those models. Requests routed to an absent model fail explicitly with `MODEL_NOT_INSTALLED`.
- `--device auto` reuses available CUDA/HIP or MPS, with a reported CPU fallback. Explicit `cpu`, `cuda`, `rocm` and `mps` selections are supported; a requested GPU cannot pass inference verification by silently using CPU. Fresh AMD/unknown Windows or Linux systems use CPU wheels unless a supported ROCm build is already configured or explicitly selected. See [hardware setup and validation limits](HARDWARE.md).
- `python -m laya_agent_kit hardware --device auto` reports the available backend without loading weights. `doctor --inference` and judgment results report the actual backend and fallback reason. ROCm uses the `cuda` API but is identified separately as `rocm`. DirectML and ONNX are not implemented.
- `doctor --client codex` checks the client's registration. Alternative launchers, including the older `codex_bridge.py`, are verified through MCP for the kit version and data directory. `doctor --inference` executes one synthetic judgment; this is not an accuracy benchmark.
- Uninstall restores any replaced Laya registration/skill and retains unrelated later edits. It refuses to overwrite edits to the managed Laya entry or skill. Models, runtime and timestamped backups remain on disk. Keep the original `--data-dir` to retain installation ownership records.

After installation, reconnect/restart the client and ask it to call `laya_status`. Codex and Claude Code also receive the `laya` skill. The MCP server itself describes its tools for other clients.

## Tools

| Tool | Purpose |
| --- | --- |
| `laya_status` | Cache readiness, runtime versions and limits without loading weights |
| `laya_rank_passages` | Rank 1–16 short passages, keeping every source and ID |
| `laya_judge` | Answer 1–8 typed questions: `choice`, `score`, `noul` |

English context is 512 tokens; multilingual and typed-decisions contexts are 1024. Inputs that exceed the actual tokenizer budget are rejected. Confidence is not calibrated for SEO/frontend tasks. Cold loads and language switches can take tens of seconds; each server process holds at most one model, and separate clients launch separate processes.

## Configuration locations

| Client | User scope | Project scope |
| --- | --- | --- |
| Codex | `$CODEX_HOME/config.toml` or `~/.codex/config.toml` | `.codex/config.toml` |
| Claude Code | `~/.claude.json` | `.mcp.json` |
| Cursor | `~/.cursor/mcp.json` | `.cursor/mcp.json` |
| Generic | `<data-dir>/exports/mcp.json` | Same export path |

New Codex skills use `~/.agents/skills/laya`; an existing legacy skill under the selected Codex config directory's `skills/laya` is updated in place. Claude Code skills use `~/.claude/skills/laya`. Project skills use `.agents/skills/laya` and `.claude/skills/laya`, respectively. Custom `CLAUDE_CONFIG_DIR` requires an explicit `--config` plus `--no-skill`, or project scope.

## Development and license

Integration source: `src/laya_agent_kit`. The root `codex_bridge.py` remains a compatibility launcher for the earlier local installation. Model implementation stays in the upstream `laya` package. Re-run the root installer after source updates to refresh the installed package.

The bundled library is based on Laya 0.3.5 at commit `573e5b62696ba441230cd6be71d593331b5d23af` from `NandhaKishorM/laya`, with local runtime changes for backend precision and fallback reporting. Its license and credits are retained alongside this community integration. Use the root installer to include these runtime changes.

Apache-2.0; preserve the upstream license and applicable notices when redistributing upstream code. Model weights and dependencies have their own applicable licenses. This kit downloads model weights separately and does not bundle them in its wheel.

Official client references: [Codex MCP](https://developers.openai.com/codex/mcp), [Codex skills](https://developers.openai.com/codex/skills), [Claude Code MCP](https://code.claude.com/docs/en/mcp), [Claude Code skills](https://code.claude.com/docs/en/skills), [Cursor MCP](https://cursor.com/docs/context/mcp).

See [reviewed community integrations](REFERENCES.md) for how `laya-ultrafast`, `arbiter` and `laya-playground` relate to this kit, including their platform, API and permission differences.

See [validation receipt](VALIDATION.md) for tested platforms, actual client checks, test commands and existing upstream test limitations.
