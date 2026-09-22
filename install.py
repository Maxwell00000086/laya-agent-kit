import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "agent-kit/src"))

from laya_agent_kit.backends import DEVICE_CHOICES
from laya_agent_kit.provision import hardware_inventory, torch_install_plan


def environment_python(directory):
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def existing_torch(python):
    if not python.is_file():
        return None
    script = (
        "import importlib.util, json, sys; "
        f"sys.path.insert(0, {str(ROOT / 'agent-kit/src')!r}); "
        "from laya_agent_kit.backends import torch_capabilities; "
        "print(json.dumps(torch_capabilities() if importlib.util.find_spec('torch') else None))"
    )
    result = subprocess.run([str(python), "-I", "-X", "utf8", "-c", script], capture_output=True, text=True, encoding="utf-8", timeout=45, check=True)
    return json.loads(result.stdout)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Create/reuse an isolated Laya environment and install AI integrations.",
        epilog="Client options are forwarded to laya-agent-kit install. Example: python install.py --client codex --client claude-code",
    )
    parser.add_argument("--venv", type=Path, default=ROOT / ".venv")
    parser.add_argument("--torch-index-url", help="Optional official PyTorch wheel index, e.g. https://download.pytorch.org/whl/cpu")
    parser.add_argument("--wheelhouse", type=Path, help="Local wheel directory for offline provisioning")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--runtime-only", action="store_true", help="Prepare models and verify MCP without registering desktop clients")
    parser.add_argument("--device", choices=DEVICE_CHOICES, default="auto")
    arguments, remaining = parser.parse_known_args(argv)
    remaining.extend(["--device", arguments.device])
    operation = "prepare" if arguments.runtime_only else "install"
    if sys.version_info < (3, 10) or struct.calcsize("P") != 8:
        parser.error("A 64-bit Python 3.10 or newer is required; Python 3.12 is recommended.")
    directory = arguments.venv.expanduser().absolute()
    python = environment_python(directory)
    if not any(value == "--data-dir" or value.startswith("--data-dir=") for value in remaining):
        remaining.extend(["--data-dir", str(ROOT / ".cache")])
    if arguments.offline:
        remaining.append("--offline")
    if arguments.dry_run:
        print(f"Would provision Python environment: {directory}", flush=True)
        print(f"Would install local packages from: {ROOT} and {ROOT / 'agent-kit'}", flush=True)
        print(f"{operation} options:", remaining, flush=True)
        if python.is_file():
            available = subprocess.run([str(python), "-I", "-c", "import laya_agent_kit, tomlkit"], capture_output=True).returncode == 0
            if available:
                subprocess.run([str(python), "-I", "-X", "utf8", "-m", "laya_agent_kit", operation, *remaining, "--dry-run"], check=True)
        return
    if directory.exists() and not (directory / "pyvenv.cfg").is_file():
        parser.error(f"Refusing to reuse a directory without pyvenv.cfg: {directory}")
    hardware = hardware_inventory()
    try:
        plan = torch_install_plan(arguments.device, arguments.torch_index_url, arguments.offline, hardware, existing_torch(python))
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps({"hardware": hardware, "torch_installation": plan}, ensure_ascii=False), flush=True)
    if not python.is_file():
        print(f"Creating isolated environment: {directory}", flush=True)
        venv.EnvBuilder(with_pip=True).create(directory)
    pip = [str(python), "-I", "-m", "pip", "install", "--disable-pip-version-check"]
    sources = []
    if arguments.offline:
        sources.append("--no-index")
    if arguments.wheelhouse:
        sources.extend(["--find-links", str(arguments.wheelhouse.expanduser().resolve())])
    if plan["index_url"]:
        replacement = ["--force-reinstall"] if plan["replace_torch"] else []
        subprocess.run([*pip, "--upgrade", *replacement, "torch>=2.0,<3", "--index-url", plan["index_url"]], check=True)
    if arguments.offline:
        subprocess.run([*pip, *sources, "setuptools>=68", "wheel"], check=True)
        sources.append("--no-build-isolation")
    print("Installing Laya and its agent integration package...", flush=True)
    subprocess.run([*pip, *sources, str(ROOT), str(ROOT / "agent-kit")], check=True)
    subprocess.run([str(python), "-I", "-m", "pip", "check"], check=True)
    subprocess.run([str(python), "-I", "-X", "utf8", "-m", "laya_agent_kit", "hardware", "--device", arguments.device], check=True)
    subprocess.run([str(python), "-I", "-X", "utf8", "-m", "laya_agent_kit", operation, *remaining], check=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Installation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
