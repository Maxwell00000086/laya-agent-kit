import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

import tomlkit


CLIENTS = ("codex", "claude-code", "cursor", "generic")


@dataclass
class Change:
    path: Path
    before: bytes | None
    after: bytes | None


def read_bytes(path):
    return path.read_bytes() if path.exists() else None


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def server_spec(client, directory, device="auto", python=None):
    spec = {
        "command": str(Path(python or sys.executable).absolute()),
        "args": ["-I", "-X", "utf8", "-m", "laya_agent_kit.server", "--stdio"],
        "env": {"LAYA_HOME": str(Path(directory).resolve()), "LAYA_DEVICE": device},
    }
    if client == "codex":
        spec.update(startup_timeout_sec=60, tool_timeout_sec=180, enabled=True)
    elif client == "claude-code":
        spec["type"] = "stdio"
    return spec


def config_path(client, directory, user_home=None, project=None, override=None):
    if override:
        return Path(override).expanduser().resolve()
    root = Path(user_home).resolve() if user_home else Path.home()
    if project:
        root = Path(project).expanduser().resolve()
        names = {"codex": ".codex/config.toml", "claude-code": ".mcp.json", "cursor": ".cursor/mcp.json"}
        if client in names:
            return root / names[client]
    if client == "codex":
        codex_directory = Path(os.environ["CODEX_HOME"]).expanduser() if not user_home and os.environ.get("CODEX_HOME") else root / ".codex"
        return (codex_directory / "config.toml").resolve()
    if client == "claude-code":
        if not user_home and os.environ.get("CLAUDE_CONFIG_DIR"):
            raise ValueError("Custom CLAUDE_CONFIG_DIR detected. Supply --config with your Claude Code JSON path and --no-skill, or use --project.")
        return root / ".claude.json"
    if client == "cursor":
        return root / ".cursor/mcp.json"
    return Path(directory) / "exports/mcp.json"


def skill_path(client, config, user_home=None, project=None):
    root = Path(project).expanduser().resolve() if project else Path(user_home).resolve() if user_home else Path.home()
    if client == "codex":
        legacy = config.parent / "skills/laya"
        if not project and legacy.exists():
            return legacy
        return root / ".agents/skills/laya"
    if client == "claude-code":
        return root / ".claude/skills/laya"
    return None


def parse_config(client, content):
    text = (content or b"").decode("utf-8-sig")
    document = tomlkit.parse(text) if client == "codex" else json.loads(text) if text.strip() else {}
    if not isinstance(document, dict):
        raise ValueError("Client configuration must be an object/table")
    key = "mcp_servers" if client == "codex" else "mcpServers"
    if key in document and not isinstance(document[key], dict):
        raise ValueError(f"{key} must be an object/table")
    return document, key


def render_config(client, document):
    return tomlkit.dumps(document).encode("utf-8") if client == "codex" else json_bytes(document)


def state_path(directory, config):
    identifier = hashlib.sha256(os.path.normcase(str(config.resolve())).encode()).hexdigest()[:24]
    return Path(directory) / "integrations" / (identifier + ".json")


def skill_contents(python, directory, device):
    resource = files("laya_agent_kit").joinpath("skill")
    runtime = (
        "# This installation\n\n"
        f"Python executable: `{python}`\n\nData directory: `{directory}`\n\nDevice: `{device}`\n\n"
        "Use the host shell to set `LAYA_HOME` to the data directory and `LAYA_DEVICE` to the device above. "
        "Invoke this Python executable with argument list "
        '`["-I", "-X", "utf8", "-m", "laya_agent_kit.server", "--request", "<absolute JSON request path>"]`. '
        "Use a UTF-8 JSON object with `operation` set to `judge` or `rank_passages`, and `input` matching the tool schema. "
        "Quote each shell argument for the current OS. Exit code 1 or a JSON error means the call failed.\n\n"
        "For diagnostics, use the same executable with `-m laya_agent_kit doctor --data-dir` and the data directory.\n"
    )
    return {
        "SKILL.md": resource.joinpath("SKILL.md").read_bytes(),
        "agents/openai.yaml": resource.joinpath("agents/openai.yaml").read_bytes(),
        "LOCAL-RUNTIME.md": runtime.encode("utf-8"),
    }


def plan_install(client, directory, device="auto", user_home=None, project=None, override=None, replace=False, include_skill=True):
    config = config_path(client, directory, user_home, project, override)
    before = read_bytes(config)
    document, key = parse_config(client, before)
    existing = document.get(key, {}).get("laya")
    spec = server_spec(client, directory, device)
    state_file = state_path(directory, config)
    state_before = read_bytes(state_file)
    state = json.loads(state_before) if state_before else None
    if state and (state.get("config") != str(config) or state.get("client") != client):
        raise ValueError(f"Registration record does not match {config}")
    owned = state is not None and existing == state["installed"]
    if existing is not None and existing != spec and not owned and not replace:
        raise ValueError(f"An existing laya server differs in {config}. Inspect it, then use --replace to back it up and replace it.")
    if state and not owned and not replace:
        raise ValueError(f"Laya configuration changed since installation: {config}. Use --replace only after reviewing it.")
    changes = []
    if existing != spec:
        if key not in document:
            document[key] = {}
        document[key]["laya"] = spec
        changes.append(Change(config, before, render_config(client, document)))
    record = {
        "client": client,
        "config": str(config),
        "installed": spec,
        "previous": state["previous"] if owned else existing,
        "skills": state.get("skills", []) if state else [],
    }
    target = skill_path(client, config, user_home, project) if include_skill else None
    if target:
        previous_skills = {item["path"]: item for item in record["skills"]}
        for relative, content in skill_contents(spec["command"], directory, device).items():
            path = target / relative
            original = read_bytes(path)
            previous = previous_skills.get(str(path))
            matches = previous and original is not None and hashlib.sha256(original).hexdigest() == previous["installed_sha256"]
            if original is not None and original != content and not matches and not replace:
                raise ValueError(f"Existing skill differs: {path}. Use --replace to back it up and replace it, or --no-skill.")
            if previous and not matches and original != content and not replace:
                raise ValueError(f"Installed skill changed: {path}")
            previous_skills[str(path)] = {
                "path": str(path),
                "installed_sha256": hashlib.sha256(content).hexdigest(),
                "previous": previous["previous"] if matches else base64.b64encode(original).decode() if original is not None else None,
            }
            if original != content:
                changes.append(Change(path, original, content))
        record["skills"] = list(previous_skills.values())
    state_after = json_bytes(record)
    if state_before != state_after:
        changes.append(Change(state_file, state_before, state_after))
    return changes, {"client": client, "config": str(config), "skill": str(target) if target else None}


def plan_uninstall(client, directory, user_home=None, project=None, override=None):
    config = config_path(client, directory, user_home, project, override)
    state_file = state_path(directory, config)
    state_before = read_bytes(state_file)
    if state_before is None:
        raise ValueError(f"No installation record for {config}; refusing to remove an unowned server.")
    state = json.loads(state_before)
    if state.get("config") != str(config) or state.get("client") != client:
        raise ValueError("Registration record does not match the requested client")
    before = read_bytes(config)
    document, key = parse_config(client, before)
    if document.get(key, {}).get("laya") != state["installed"]:
        raise ValueError(f"Laya configuration was edited after installation: {config}. Preserve or reconcile those edits first.")
    if state["previous"] is None:
        del document[key]["laya"]
    else:
        document[key]["laya"] = state["previous"]
    changes = [Change(config, before, render_config(client, document))]
    for item in state.get("skills", []):
        path = Path(item["path"])
        original = read_bytes(path)
        if original is None or hashlib.sha256(original).hexdigest() != item["installed_sha256"]:
            raise ValueError(f"Installed skill was edited or removed: {path}. Preserve or reconcile those edits first.")
        restored = base64.b64decode(item["previous"]) if item["previous"] is not None else None
        if original != restored:
            changes.append(Change(path, original, restored))
    changes.append(Change(state_file, state_before, None))
    return changes, {"client": client, "config": str(config)}


def atomic_write(path, content):
    if content is None:
        path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    descriptor, temporary = tempfile.mkstemp(prefix=".laya-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_changes(changes, dry_run=False):
    paths = [change.path.resolve() for change in changes]
    if len(paths) != len(set(paths)):
        raise ValueError("Multiple clients target the same file; install them separately")
    for change in changes:
        if read_bytes(change.path) != change.before:
            raise ValueError(f"File changed while preparing installation: {change.path}. Retry after the client finishes writing.")
    if dry_run:
        return {"dry_run": True, "files": [str(path) for path in paths], "backups": []}
    completed = []
    backups = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    try:
        for change in changes:
            if read_bytes(change.path) != change.before:
                raise ValueError(f"File changed during installation: {change.path}")
            if change.before is not None:
                backup = change.path.with_name(change.path.name + ".laya-backup-" + stamp)
                atomic_write(backup, change.before)
                backups.append(str(backup))
            atomic_write(change.path, change.after)
            completed.append(change)
    except Exception:
        for change in reversed(completed):
            if read_bytes(change.path) == change.after:
                atomic_write(change.path, change.before)
        raise
    return {"dry_run": False, "files": [str(path) for path in paths], "backups": backups}
