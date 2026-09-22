import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from start_chatgpt import ROOT, child_environment, ensure_tunnel_client, mcp_command


def main():
    directory = ROOT / ".cache"
    executable = ensure_tunnel_client(directory, offline=True)
    environment = child_environment(directory, "auto", "synthetic-local-doctor-value")
    reports = []
    with tempfile.TemporaryDirectory(prefix="laya user's tools & ") as temporary:
        temporary = Path(temporary)
        spaced_python = temporary / Path(sys.executable).name
        shutil.copy2(sys.executable, spaced_python)
        for index, python in enumerate((Path(sys.executable), spaced_python)):
            profile_name = f"local-check-{index}"
            subprocess.run([
                str(executable), "init", "--sample", "sample_mcp_stdio_local",
                "--profile", profile_name, "--profile-dir", str(temporary),
                "--tunnel-id", "tunnel_0123456789abcdef0123456789abcdef",
                "--mcp-command", mcp_command(python), "--health-listen-addr", "127.0.0.1:0",
            ], env=environment, check=True, capture_output=True, text=True, encoding="utf-8")
            profile = temporary / f"{profile_name}.yaml"
            document = profile.read_text(encoding="utf-8")
            assert "synthetic-local-doctor-value" not in document
            assert "env:CONTROL_PLANE_API_KEY" in document
            checked = subprocess.run([
                str(executable), "doctor", "--profile-file", str(profile), "--json",
            ], env=environment, check=True, capture_output=True, text=True, encoding="utf-8")
            assert "synthetic-local-doctor-value" not in checked.stdout + checked.stderr
            report = json.loads(checked.stdout)
            assert report["result"] == "ok", report
            assert any(check["id"] == "mcp_command_executable" and check["status"] == "PASS" for check in report["checks"])
            reports.append({"path_with_spaces_and_quote": index == 1, "result": report["result"], "checks": report["checks"]})
    receipt = directory / "verification/chatgpt-local.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({
        "official_tunnel_client": str(executable),
        "checks": reports,
        "live_tunnel_started": False,
        "chatgpt_end_to_end_verified": False,
        "note": "Official init/doctor only, using a synthetic value. No authenticated control-plane request or ChatGPT account connection.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Official init/doctor passed for both command paths. Receipt: {receipt}")


if __name__ == "__main__":
    main()
