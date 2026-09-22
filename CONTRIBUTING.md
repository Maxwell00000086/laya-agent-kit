# Contributing to Laya Agent Kit

Contributions, bug reports and documentation improvements are welcome. This project adds installation and MCP integration to upstream [Laya](https://github.com/NandhaKishorM/laya). Preserve the upstream license, credits and model boundaries.

## Where to start

- Use [Discussions](https://github.com/Maxwell00000086/laya-agent-kit/discussions) for installation questions, usage and early ideas. English and Chinese are welcome.
- Use Issues for reproducible bugs and concrete feature requests. Include your operating system, Python version, client, exact command, expected behavior and a redacted error log.
- Report security vulnerabilities privately using [the security policy](SECURITY.md).

Be respectful and constructive. Do not post API keys, environment files, account credentials, private client configurations or unredacted transcripts.

## Development

Fork the repository, create a branch in your fork, and submit a pull request against `main`. Keep changes focused and explain the problem, resulting behavior and validation. Discuss changes to model behavior or authentication design before implementing them.

From a checkout with 64-bit Python 3.10+ (3.12 recommended):

```sh
python -m venv .venv
```

Activate the environment using your platform's normal command, then install both packages:

```sh
python -m pip install -e . -e ./agent-kit
python -m unittest discover -s tests -p test_agent_kit.py -v
python -m unittest discover -s tests -p test_chatgpt_setup.py -v
```

These regression tests do not need model weights or an OpenAI account. Installation and inference checks do need the checkpoints; see [VALIDATION.md](agent-kit/VALIDATION.md). Do not run all upstream `test_*.py` files through unittest discovery: some are standalone scripts.

Integration code lives in `agent-kit/src/laya_agent_kit`; root launchers provide checkout-based setup. Do not commit `.venv`, model caches, binaries downloaded by the launcher, credentials or machine-specific client settings. Keep configuration preservation, dry-run behavior and uninstall recovery intact.

## Reviews and releases

Pull requests use squash merging, and merged branches may be removed automatically. Run relevant checks and describe platform coverage accurately. Local setup success does not establish a live ChatGPT connection or task-level model accuracy.

Maintainers decide when to merge or release. Contributing does not grant publish rights. The upstream PyPI publication workflow is restricted to the upstream repository; this community kit is installed from source until a separate release process is established.
