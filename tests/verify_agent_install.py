import asyncio
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import tomlkit
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".cache"
CLIENTS = ("codex", "claude-code", "cursor", "generic")


def command(operation, user_home, *options):
    arguments = [sys.executable, "-I", "-X", "utf8", "-m", "laya_agent_kit", operation, "--data-dir", str(DATA), "--user-home", str(user_home)]
    for client in CLIENTS:
        arguments.extend(["--client", client])
    completed = subprocess.run([*arguments, *options], cwd=user_home, text=True, encoding="utf-8", capture_output=True, timeout=300)
    if completed.returncode:
        raise RuntimeError(completed.stderr)
    return json.loads(completed.stdout)


async def inspect_registration(target):
    path = Path(target["config"])
    document = tomlkit.parse(path.read_text(encoding="utf-8")) if target["client"] == "codex" else json.loads(path.read_text(encoding="utf-8"))
    key = "mcp_servers" if target["client"] == "codex" else "mcpServers"
    spec = document[key]["laya"]
    parameters = StdioServerParameters(command=spec["command"], args=spec["args"], env=dict(spec["env"]))
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=60)) as session:
            await session.initialize()
            listing = await session.list_tools()
            assert {tool.name for tool in listing.tools} == {"laya_status", "laya_judge", "laya_rank_passages"}
            response = await session.call_tool("laya_status", {})
            assert not response.isError
            status = response.structuredContent
            if status is None:
                status = json.loads(next(block.text for block in response.content if block.type == "text"))
            assert status["offline"]
            assert status["agent_kit_version"] == "0.1.0"
            return {"client": target["client"], "tools": [tool.name for tool in listing.tools], "status": status}


def main():
    with tempfile.TemporaryDirectory(prefix="laya client smoke ") as temporary:
        user_home = Path(temporary)
        installed = command("install", user_home, "--offline", "--device", "cpu")
        assert installed["verification"]["mcp"]["inference"]["device"] == "cpu"
        print("PASS install + real CPU inference", flush=True)
        receipts = []
        for target in installed["targets"]:
            receipts.append(asyncio.run(inspect_registration(target)))
            print(f"PASS generated {target['client']} registration starts MCP", flush=True)
        repeated = command("install", user_home, "--offline", "--device", "cpu", "--dry-run")
        assert repeated["files"] == []
        print("PASS idempotent reinstallation", flush=True)
        removed = command("uninstall", user_home)
        for target in removed["targets"]:
            path = Path(target["config"])
            document = tomlkit.parse(path.read_text(encoding="utf-8")) if target["client"] == "codex" else json.loads(path.read_text(encoding="utf-8"))
            key = "mcp_servers" if target["client"] == "codex" else "mcpServers"
            assert "laya" not in document.get(key, {})
        assert (DATA / "huggingface").is_dir()
        print("PASS uninstall + cache retention", flush=True)
        receipt_path = DATA / "verification/agent-install.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps({"isolated_client_configuration": True, "synthetic_smoke_only": True, "verification": installed["verification"], "clients": receipts}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved {receipt_path}", flush=True)


if __name__ == "__main__":
    main()
