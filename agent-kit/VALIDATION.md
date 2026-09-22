# Validation receipt

Date: 2026-09-22. Host: Windows, Python 3.12.14, NVIDIA RTX 3060 12 GB, PyTorch 2.14.0+cu130. Model checkpoint revision: `1c5edc17a7acd8701df6fc341c0d179f1c62c982`. These are functional synthetic checks, not task-accuracy benchmarks.

## Passed

- 24 installer/model-preparation/diagnostic regression tests in `tests/test_agent_kit.py`: configuration preservation, TOML comments, backups, conflicts, repeated installation, rollback on write failure, concurrent-edit detection, uninstall ownership, restoration of previous skills/servers, user/project scope, argument boundaries, revision-pinned download filtering, incomplete caches and legacy-launcher diagnostics.
- Seven existing bridge tests in `tests/test_codex_bridge.py`: request validation, source IDs, JSON status, actual tokenizer budgets and overlong evidence/options.
- `tests/verify_codex_mcp.py`: initialization, tool discovery, annotations, synthetic SEO passage ranking, English/Chinese frontend judgments, overlong-input rejection and subsequent status. Actual inference used CUDA.
- `tests/verify_agent_install.py`: isolated user configurations for Codex, Claude Code, Cursor and generic MCP; a real CPU inference; startup/tool discovery through each generated registration; repeated installation with no rewrites; uninstall with cache retention. Cursor's own application was not exercised.
- Full root `install.py --offline` flow using the existing dependency/model cache and isolated client homes: local package builds/installation, `pip check`, real GPU inference and registrations. The kit was then run from its regular installed package, rather than depending on an editable source import. Isolated registrations were uninstalled afterward.
- Standalone Python wheel build includes the service, installer modules, skill and Apache license, excluding model weights.
- Skill frontmatter validator, byte compilation, dependency checks and Git whitespace checks.
- Existing upstream tests were run through their own script entrypoints: router, criteria, shortlist, decision model, packaging and email all passed.
- The actual Claude Code CLI reports `laya ... Connected`. The actual Codex task can call `laya_status`. `doctor` separately started both the legacy Codex launcher and new Claude registration and verified their kit version/data directory. The already running Codex session retains its earlier in-memory server until reconnection.

Local machine receipts, excluded from version control:

- `.cache/verification/codex-mcp.json`
- `.cache/verification/agent-install.json`
- `.cache/verification/bootstrap.log`
- `.cache/verification/bootstrap-uninstall.json`
- `.cache/verification/claude-install.json`
- `.cache/verification/installed-clients.json`

## Limits and existing failures

### Browser-assistance follow-up, 2026-09-22

Repeated browser assistance exposed two separate problems: the host needed clearer proactive skill routing, and switching from `english` to `typed-decisions` could fail with Windows error 1455 (insufficient paging-file capacity). A fresh MCP session reproduced the latter. The single-model router constructed the replacement before evicting its previous checkpoint, temporarily requiring both allocations.

The serialized Agent Kit runtime now unloads its old checkpoint, collects references and releases unused CUDA cache before constructing a different checkpoint. It still reuses a warm matching model. Missing checkpoint files are checked before unloading, and a failed replacement can be followed by a fresh load of the previous model. This does not increase Windows paging-file settings or change upstream routing semantics.

- Three new memory-lifecycle regression cases passed, after two failed against the previous implementation. They run in the Agent Kit CI job without downloading weights.
- All seven bridge tests and 24 installer tests passed. Both installed and distributable skill definitions passed validation; automatic skill selection was already enabled and remains enabled.
- A fresh real CUDA MCP session completed `english` then `typed-decisions`, followed by two calls reusing the typed checkpoint. Client-observed times were 18,478.5 ms for the first English call, 15,772.8 ms for the model switch and 27.1/31.8 ms for the subsequent short typed calls. These few observations are diagnostics, not general latency or task-accuracy benchmarks, and exclude the host AI's preparation and verification work.
- Diagnostic receipt: `.cache/verification/laya-session-probe.json`. The reproduction helper and page-specific requests remain local ignored artifacts.
- After reconnecting the actual Codex host, `laya_status` succeeded and `laya_judge` ran the `typed-decisions` checkpoint on CUDA. A synthetic duplicate-charge ticket was classified as `billing`; the first call took 18,050 ms including model loading. This verifies the host MCP connection and inference path, not general task accuracy.

The skills now describe proactive passage ranking and bounded browser/frontend comparisons, batching, model reuse, independent verification and connection-failure handling. They are host instructions, not mandatory tool interception hooks. Incorrect browser suggestions remain possible; this change does not train the model or establish its accuracy. An already closed host MCP transport still needs reconnection to start the updated runtime.

- An exploratory `unittest discover -p 'test_*.py'` is not a valid all-suite runner for upstream: several script tests call `sys.exit()` when imported, and `test_local_e2e.py` interprets positional arguments as its model directory. Use their documented script entrypoints and supply the expected model layout.
- The unmodified upstream `tests/test_download.py` has Windows path-separator assertion failures: expected file names use `str(Path)` backslashes, while Hugging Face file selection returns forward slashes. Five comparisons failed. The test's actual inference comparisons passed before those assertions. This integration does not modify that upstream test or claim that every upstream test passes on Windows.
- macOS/Linux provisioning and Apple hardware were not tested on physical machines. There is no MLX backend in this kit.
- A completely empty machine performing the full multi-GB network installation was not retested. The root bootstrap reused the verified cache; download selection/missing-file behavior was covered with isolated fixtures.
- No HTTP/Jev service, browser executor or `PreToolUse` permission hook was installed. These checks did not publish a PyPI package or create a release.

## Web ChatGPT setup extension

Also verified on 2026-09-22:

- 15 additional tests in `tests/test_chatgpt_setup.py` passed, along with the 24 existing installer tests. Coverage includes no-op dry runs, runtime-only installation, credential selection, unrelated tunnel/environment isolation, archive checksum and path checks, failed setup/doctor/start behavior, and duplicate local tunnel locking.
- Downloaded the official Windows amd64 `tunnel-client` v0.0.14 archive and verified SHA-256 `784ab8da7b5a88f0109f1fd8aaf0a1c86067430b896dddf307ef7e3cc49fa1a5`. The binary reports source revision `0f870e50a973fa820d4c409000059e181e8d242b`.
- `tests/verify_chatgpt_setup.py` exercised the actual official binary's `init` and `doctor`, including Python/profile paths with spaces, an apostrophe and `&`. The synthetic credential stayed out of generated profiles and output. Its `doctor` preflight misinterprets a separate `-X utf8` value as a Python script, so this launcher uses the equivalent `-Xutf8` spelling.
- `start_chatgpt.py --setup-only --offline` completed the full cached bootstrap: regular package installation, dependency checks, MCP initialization/tool discovery and an actual CUDA judgment. No desktop registrations were written and no tunnel was connected.
- Receipts: `.cache/verification/chatgpt-local.json` and `.cache/verification/chatgpt-setup.log` (both ignored).

No real tunnel ID/key or ChatGPT workspace was used. Authenticated control-plane connectivity, the live forwarding path and discovery/tool calls from web ChatGPT remain **unverified**. Local `doctor` success is not an end-to-end connection receipt. Linux/macOS and Windows ARM downloads were not executed on those platforms. The published download hashes come from the official v0.0.14 `SHA256SUMS.txt`.

Reproduce the new checks:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p test_chatgpt_setup.py -v
.\.venv\Scripts\python.exe -X utf8 start_chatgpt.py --setup-only --offline
.\.venv\Scripts\python.exe -X utf8 tests\verify_chatgpt_setup.py
```

The last command runs local official-client preflight with a synthetic value; it does not start a tunnel or contact the control plane with an account credential.

## Reproduce the integration checks

Run from the repository root on Windows:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p test_agent_kit.py -v
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p test_codex_bridge.py -v
.\.venv\Scripts\python.exe -X utf8 tests\test_runtime_lifecycle.py
.\.venv\Scripts\python.exe -X utf8 tests\verify_codex_mcp.py
.\.venv\Scripts\python.exe -X utf8 tests\verify_agent_install.py
.\.venv\Scripts\python.exe -X utf8 -m pip check
```

The real MCP checks require the downloaded checkpoints. The isolated installer smoke test writes integration records/export files under the existing data directory and removes its registrations at the end. It does not replace the user's actual client configuration.
