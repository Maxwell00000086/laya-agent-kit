import argparse
from contextlib import contextmanager
import getpass
import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import warnings
import zipfile

from install import ROOT, environment_python
from laya_agent_kit.backends import DEVICE_CHOICES


TUNNEL_VERSION = "v0.0.14"
TUNNEL_RELEASE = f"https://github.com/openai/tunnel-client/releases/download/{TUNNEL_VERSION}"
TUNNEL_CHECKSUMS = {
    "windows-amd64": "784ab8da7b5a88f0109f1fd8aaf0a1c86067430b896dddf307ef7e3cc49fa1a5",
    "windows-arm64": "fa775db8897df543dd4ba66404f69492a2acfbc6a291f10df27aced064a16568",
    "linux-amd64": "15bd17e805cad39d412199115bb9e10a978dd35258a114cdf25dd2ae6681c7d3",
    "linux-arm64": "2de3fb879a18edb847e0313592c912f1983685488290a7fdba7ac403e6a4fb0a",
}
TUNNELS_URL = "https://platform.openai.com/settings/organization/tunnels"
KEYS_URL = "https://platform.openai.com/settings/organization/api-keys"
CHATGPT_URL = "https://chatgpt.com/#settings/Connectors"


def make_parser():
    parser = argparse.ArgumentParser(description="Set up local Laya and start its private ChatGPT MCP tunnel.")
    parser.add_argument("--setup-only", action="store_true", help="Install and verify locally without keys or a tunnel connection")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writes, downloads, processes or credential prompts")
    parser.add_argument("--skip-install", action="store_true", help="Reuse installed Python packages; still verify MCP and inference")
    parser.add_argument("--offline", action="store_true", help="Provision from cached models/packages/tools; the running tunnel still needs network access")
    parser.add_argument("--venv", type=Path, default=ROOT / ".venv")
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".cache")
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--torch-index-url")
    parser.add_argument("--device", choices=DEVICE_CHOICES, default="auto")
    parser.add_argument("--tunnel-id", help="Existing tunnel_<32 lowercase hex> associated with your ChatGPT workspace")
    parser.add_argument("--tunnel-client", type=Path, help="Use an explicitly selected official tunnel-client executable")
    parser.add_argument("--key-env", help="Explicitly read the runtime key from this environment variable instead of prompting locally")
    return parser


def validate_tunnel_id(value):
    if not re.fullmatch(r"tunnel_[0-9a-f]{32}", value):
        raise ValueError("Tunnel ID must be tunnel_ followed by 32 lowercase hex characters.")
    return value


def release_platform():
    system = platform.system().lower()
    architecture = {"amd64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine().lower())
    name = f"{system}-{architecture}"
    if name not in TUNNEL_CHECKSUMS:
        raise ValueError(f"No automatic tunnel-client download for {system}/{platform.machine()}; supply --tunnel-client PATH.")
    return name


def download_archive(destination, name):
    asset = f"tunnel-client-{TUNNEL_VERSION}-{name}.zip"
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(f"{TUNNEL_RELEASE}/{asset}", timeout=60) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 512 * 1024 * 1024:
                raise ValueError("Tunnel archive exceeds the 512 MiB download limit.")
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != TUNNEL_CHECKSUMS[name]:
        raise ValueError("Official tunnel-client archive checksum mismatch; nothing was executed.")


def extract_archive(archive, destination):
    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        names = set()
        if sum(member.file_size for member in members) > 1024 * 1024 * 1024:
            raise ValueError("Tunnel archive exceeds the 1 GiB extraction limit.")
        for member in members:
            path = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            normalized = member.filename.casefold()
            if (path.is_absolute() or ".." in path.parts or "\\" in member.orig_filename or ":" in member.filename or "\0" in member.orig_filename
                    or normalized in names or stat.S_ISLNK(mode)
                    or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))):
                raise ValueError("Unsafe or duplicate path in tunnel archive.")
            names.add(normalized)
        package.extractall(destination)
    if os.name != "nt":
        for executable in ("tunnel-client", "cloudflared"):
            for path in destination.rglob(executable):
                path.chmod(0o755)


def ensure_tunnel_client(directory, explicit=None, offline=False):
    if explicit:
        executable = explicit.expanduser().resolve()
        if not executable.is_file():
            raise FileNotFoundError(f"No tunnel-client executable at {executable}")
        return executable
    if platform.system() == "Darwin":
        installed = shutil.which("tunnel-client")
        if installed:
            return Path(installed)
        brew = shutil.which("brew")
        if offline or not brew:
            raise RuntimeError("Install the notarized macOS client with: brew install openai/tools/tunnel-client; then rerun.")
        subprocess.run([brew, "install", "openai/tools/tunnel-client"], check=True)
        installed = shutil.which("tunnel-client")
        if not installed:
            raise RuntimeError("Homebrew installed tunnel-client; add its bin directory to PATH and rerun.")
        return Path(installed)
    name = release_platform()
    folder = directory / "tools" / "tunnel-client" / TUNNEL_VERSION / name
    filename = "tunnel-client.exe" if name.startswith("windows-") else "tunnel-client"
    receipt = folder / ".laya-verified-sha256"
    if receipt.is_file() and receipt.read_text().strip() == TUNNEL_CHECKSUMS[name]:
        matches = list(folder.rglob(filename))
        if len(matches) == 1:
            return matches[0]
    if folder.exists():
        raise RuntimeError(f"Incomplete tunnel installation at {folder}; use --tunnel-client with a verified official binary.")
    if offline:
        raise FileNotFoundError("No cached tunnel-client. Run setup online first or provide --tunnel-client PATH.")
    folder.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading official tunnel-client {TUNNEL_VERSION} ({name}) and checking SHA-256...", flush=True)
    with tempfile.TemporaryDirectory(prefix="download-", dir=folder.parent) as temporary:
        temporary = Path(temporary)
        archive = temporary / "release.zip"
        download_archive(archive, name)
        unpacked = temporary / "unpacked"
        extract_archive(archive, unpacked)
        matches = list(unpacked.rglob(filename))
        if len(matches) != 1:
            raise RuntimeError("Expected exactly one tunnel-client executable in the official archive.")
        relative = matches[0].relative_to(unpacked)
        (unpacked / receipt.name).write_text(TUNNEL_CHECKSUMS[name], encoding="ascii")
        unpacked.rename(folder)
    return folder / relative


def child_environment(directory, device, key=None):
    environment = {
        name: value for name, value in os.environ.items()
        if not name.upper().startswith(("CONTROL_PLANE_", "TUNNEL_CLIENT_", "MCP_", "HARPOON_", "HEALTH_", "ADMIN_UI_", "CLOUDFLARED_"))
        and name.upper() not in ("OPENAI_API_KEY", "OPENAI_ADMIN_KEY", "LOG_FILE", "LOG_LEVEL", "LOG_FORMAT", "PROCESS_PID_FILE")
    }
    environment.update(LAYA_HOME=str(directory), LAYA_DEVICE=device, PYTHONUTF8="1")
    if key is not None:
        environment["CONTROL_PLANE_API_KEY"] = key
    return environment


def runtime_key(variable=None):
    if variable:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable):
            raise ValueError("--key-env requires an environment variable name, not a key.")
        value = os.environ.get(variable, "").strip()
        if not value:
            raise ValueError("The selected runtime-key environment variable is empty.")
        return value
    if not sys.stdin.isatty():
        raise ValueError("Run in an interactive terminal to enter the runtime key, or explicitly select --key-env VARIABLE.")
    print(f"Runtime key (Tunnels Read + Use): {KEYS_URL}\nEnter it here only; never paste it into ChatGPT. It will not be saved.", flush=True)
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        value = getpass.getpass("Tunnel runtime key (hidden): ").strip()
    if not value:
        raise ValueError("A tunnel runtime key is required.")
    return value


def mcp_command(python):
    return shlex.join([python.as_posix(), "-I", "-Xutf8", "-m", "laya_agent_kit.server", "--stdio"])


@contextmanager
def tunnel_lock(directory, tunnel_id):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{tunnel_id}.lock").open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("This tunnel is already running from this data directory; stop it before restarting.") from error
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def run_tunnel(executable, python, directory, device, tunnel_id, key):
    environment = child_environment(directory, device, key)
    workspace = directory / "chatgpt"
    with tunnel_lock(workspace, tunnel_id), tempfile.TemporaryDirectory(prefix="session-", dir=workspace) as session:
        subprocess.run([
            str(executable), "init", "--sample", "sample_mcp_stdio_local", "--profile", "laya",
            "--profile-dir", session, "--tunnel-id", tunnel_id,
            "--mcp-command", mcp_command(python), "--health-listen-addr", "127.0.0.1:0",
        ], env=environment, check=True)
        profile = str(Path(session) / "laya.yaml")
        subprocess.run([str(executable), "doctor", "--profile-file", profile, "--explain"], env=environment, check=True)
        print(
            f"\nStarting the tunnel. Keep this terminal open; Ctrl+C stops it.\n"
            f"ChatGPT: {CHATGPT_URL}\n"
            f"Enable developer mode, create an app/plugin, select Connection: Tunnel, then choose {tunnel_id}.\n"
            "Select Laya in your conversation and ask it to call laya_status, then laya_judge.\n"
            "Local doctor passing does not verify account access or a ChatGPT tool call.\n",
            flush=True,
        )
        subprocess.run([str(executable), "run", "--profile-file", profile], env=environment, check=True)


def main(argv=None):
    parser = make_parser()
    arguments = parser.parse_args(argv)
    if arguments.tunnel_id:
        validate_tunnel_id(arguments.tunnel_id)
    directory = arguments.data_dir.expanduser().resolve()
    python = environment_python(arguments.venv.expanduser().resolve())
    if arguments.dry_run:
        print(f"Would prepare Laya in {python.parent.parent}, models in {directory}; desktop clients are not registered.")
        print(f"Would use {arguments.tunnel_client or 'official tunnel-client ' + TUNNEL_VERSION}.")
        print("Setup only." if arguments.setup_only else "Would prompt locally for tunnel ID/key, run doctor and start the foreground tunnel.")
        return
    print(f"Private ChatGPT connection requires developer mode and a workspace-associated tunnel: {TUNNELS_URL}", flush=True)
    executable = ensure_tunnel_client(directory, arguments.tunnel_client, arguments.offline)
    if arguments.skip_install:
        subprocess.run([
            str(python), "-I", "-X", "utf8", "-m", "laya_agent_kit", "doctor",
            "--data-dir", str(directory), "--device", arguments.device, "--inference",
        ], env=child_environment(directory, arguments.device), check=True)
    else:
        command = [
            sys.executable, "-X", "utf8", str(ROOT / "install.py"), "--runtime-only",
            "--venv", str(arguments.venv.expanduser().resolve()), "--data-dir", str(directory), "--device", arguments.device,
        ]
        if arguments.offline:
            command.append("--offline")
        for name in ("wheelhouse", "torch_index_url"):
            if value := getattr(arguments, name):
                command.extend(["--" + name.replace("_", "-"), str(value)])
        subprocess.run(command, env=child_environment(directory, arguments.device), check=True)
    if arguments.setup_only:
        print("Local setup verified. No tunnel was connected. Rerun with --skip-install to connect.", flush=True)
        return
    tunnel_id = arguments.tunnel_id
    if not tunnel_id:
        if not sys.stdin.isatty():
            raise ValueError("Supply --tunnel-id or run in an interactive terminal.")
        tunnel_id = input("Existing ChatGPT workspace tunnel ID: ").strip()
    validate_tunnel_id(tunnel_id)
    key = runtime_key(arguments.key_env)
    run_tunnel(executable, python, directory, arguments.device, tunnel_id, key)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped. Reconnect by running this command again.", file=sys.stderr)
        raise SystemExit(130)
    except subprocess.CalledProcessError as error:
        print(f"Setup/start failed (exit {error.returncode}). Review the preceding diagnostic output; ChatGPT connection is not confirmed.", file=sys.stderr)
        raise SystemExit(1)
    except (OSError, ValueError, RuntimeError, getpass.GetPassWarning) as error:
        print(f"Setup/start failed: {error}", file=sys.stderr)
        raise SystemExit(1)
