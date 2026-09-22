import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .backends import DEVICE_CHOICES
from .clients import CLIENTS, apply_changes, config_path, parse_config, plan_install, plan_uninstall, render_config, server_spec
from .models import MODEL_NAMES, data_directory, prepare_models


def make_parser():
    parser = argparse.ArgumentParser(description="Local Laya integration for Codex, Claude Code, Cursor and MCP clients")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="operation", required=True)
    for operation in ("install", "uninstall", "download", "doctor", "config", "prepare", "hardware"):
        command = commands.add_parser(operation)
        command.add_argument("--data-dir", type=Path, help="Model cache and installation records; also accepted via LAYA_HOME")
        if operation != "uninstall":
            command.add_argument("--device", choices=DEVICE_CHOICES, default="auto")
        if operation in ("install", "download", "doctor", "prepare"):
            command.add_argument("--models", nargs="+", choices=MODEL_NAMES, default=list(MODEL_NAMES))
        if operation in ("install", "download", "prepare"):
            command.add_argument("--offline", action="store_true", help="Require already cached models without downloading")
        if operation in ("install", "uninstall", "doctor"):
            command.add_argument("--client", action="append", choices=CLIENTS, help="Repeat to select several clients")
            command.add_argument("--user-home", type=Path, help="Override client home for portable installations and isolated validation")
            command.add_argument("--project", type=Path, help="Write project configuration instead of user configuration")
            command.add_argument("--config", type=Path, help="Explicit configuration path; requires exactly one client")
        if operation in ("install", "uninstall", "prepare"):
            command.add_argument("--dry-run", action="store_true", help="Preview without writing files or downloading")
        if operation == "install":
            command.add_argument("--replace", action="store_true", help="Back up and replace an existing conflicting laya registration/skill")
            command.add_argument("--no-skill", action="store_true", help="Register MCP only")
            command.add_argument("--skip-inference", action="store_true", help="Check MCP startup/discovery without the installation smoke inference")
        if operation == "doctor":
            command.add_argument("--inference", action="store_true", help="Also run a synthetic judgment on the first selected model")
        if operation == "config":
            command.add_argument("--client", choices=CLIENTS, default="generic")
    return parser


def run(arguments):
    directory = data_directory(arguments.data_dir)
    if arguments.operation == "hardware":
        from .diagnostics import runtime_info

        return runtime_info(arguments.device)
    if arguments.operation == "config":
        key = "mcp_servers" if arguments.client == "codex" else "mcpServers"
        print(render_config(arguments.client, {key: {"laya": server_spec(arguments.client, directory, arguments.device)}}).decode(), end="")
        return None
    if arguments.operation == "download":
        return {"models": prepare_models(directory, arguments.models, arguments.offline)}
    if arguments.operation == "prepare":
        if arguments.dry_run:
            return {"dry_run": True, "data_directory": str(directory), "models": arguments.models, "clients": []}
        from .diagnostics import diagnose

        prepare_models(directory, arguments.models, arguments.offline)
        return diagnose(directory, arguments.device, arguments.models, arguments.models[0])
    clients = list(dict.fromkeys(arguments.client or (["codex"] if arguments.operation != "doctor" else [])))
    if arguments.config and len(clients) != 1:
        raise ValueError("--config requires exactly one --client")
    if arguments.config and arguments.project:
        raise ValueError("Use either --config or --project")
    if arguments.operation == "doctor":
        from .diagnostics import diagnose, diagnose_registration

        result = diagnose(directory, arguments.device, arguments.models, arguments.models[0] if arguments.inference else None)
        result["clients"] = []
        for client in clients:
            path = config_path(client, directory, arguments.user_home, arguments.project, arguments.config)
            document, key = parse_config(client, path.read_bytes() if path.exists() else None)
            spec = document.get(key, {}).get("laya")
            matches = spec == server_spec(client, directory, arguments.device)
            registered = {"client": client, "config": str(path), "matches_generated_config": matches}
            if not spec or spec.get("enabled") is False:
                registered.update(ok=False, error="Laya is absent or disabled in the selected configuration")
            elif matches:
                registered.update(ok=True, transport_verified=True)
            else:
                try:
                    actual = diagnose_registration(spec, directory, arguments.device)
                    status = actual["status"]
                    compatible = status.get("agent_kit_version") == __version__ and Path(status.get("data_directory", "")).resolve() == directory
                    registered.update(ok=compatible, transport_verified=True, status=status)
                except Exception as error:
                    registered.update(ok=False, error=str(error))
            result["clients"].append(registered)
            result["ok"] = result["ok"] and registered["ok"]
        return result
    changes = []
    targets = []
    for client in clients:
        options = {"user_home": arguments.user_home, "project": arguments.project, "override": arguments.config}
        if arguments.operation == "install":
            additions, target = plan_install(client, directory, arguments.device, replace=arguments.replace, include_skill=not arguments.no_skill, **options)
        else:
            additions, target = plan_uninstall(client, directory, **options)
        changes.extend(additions)
        targets.append(target)
    if arguments.dry_run:
        return {**apply_changes(changes, dry_run=True), "targets": targets, "data_directory": str(directory)}
    diagnostics = None
    if arguments.operation == "install":
        from .diagnostics import diagnose

        print("Preparing local models...", file=sys.stderr, flush=True)
        prepare_models(directory, arguments.models, arguments.offline)
        print("Checking runtime and MCP transport...", file=sys.stderr, flush=True)
        diagnostics = diagnose(directory, arguments.device, arguments.models, None if arguments.skip_inference else arguments.models[0])
    result = {**apply_changes(changes), "targets": targets, "data_directory": str(directory)}
    if diagnostics:
        result["verification"] = diagnostics
        result["next_step"] = "Restart or reconnect the selected clients to load laya. A client may request trust/approval for a project MCP configuration."
    else:
        result["note"] = "Removed this installation's registrations and restored previous entries. Runtime and model cache are retained."
    return result


def main():
    parser = make_parser()
    arguments = parser.parse_args()
    try:
        result = run(arguments)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
            if result.get("ok") is False:
                raise SystemExit(1)
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from error
