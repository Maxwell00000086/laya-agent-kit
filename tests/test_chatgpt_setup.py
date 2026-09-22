from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent-kit/src"))

import start_chatgpt as setup
from laya_agent_kit import cli


class ChatGPTSetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="laya chatgpt ")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.tunnel_id = "tunnel_0123456789abcdef0123456789abcdef"

    def test_dry_run_never_downloads_starts_or_prompts(self):
        with patch.object(setup, "ensure_tunnel_client") as download, patch.object(setup.subprocess, "run") as run, patch.object(setup, "runtime_key") as key, redirect_stdout(io.StringIO()):
            setup.main(["--dry-run", "--data-dir", str(self.directory / "cache")])
        download.assert_not_called()
        run.assert_not_called()
        key.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_runtime_prepare_has_no_desktop_registration(self):
        arguments = cli.make_parser().parse_args(["prepare", "--data-dir", str(self.directory / "cache")])
        with patch.object(cli, "prepare_models") as models, patch("laya_agent_kit.diagnostics.diagnose", return_value={"ok": True}) as diagnose, patch.object(cli, "plan_install") as register:
            self.assertTrue(cli.run(arguments)["ok"])
        models.assert_called_once()
        diagnose.assert_called_once()
        register.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_prepare_dry_run_is_side_effect_free(self):
        arguments = cli.make_parser().parse_args(["prepare", "--data-dir", str(self.directory / "cache"), "--dry-run"])
        with patch.object(cli, "prepare_models") as download:
            self.assertEqual(cli.run(arguments)["clients"], [])
        download.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_setup_only_does_not_request_credentials_or_connect(self):
        with patch.object(setup, "ensure_tunnel_client", return_value=Path("tunnel-client")), patch.object(setup.subprocess, "run") as run, patch.object(setup, "runtime_key") as key, patch.object(setup, "run_tunnel") as connect, redirect_stdout(io.StringIO()):
            setup.main(["--setup-only", "--data-dir", str(self.directory)])
        self.assertIn("--runtime-only", run.call_args.args[0])
        self.assertNotIn("--client", run.call_args.args[0])
        key.assert_not_called()
        connect.assert_not_called()

    def test_failed_local_setup_never_connects(self):
        with patch.object(setup, "ensure_tunnel_client", return_value=Path("tunnel-client")), patch.object(setup.subprocess, "run", side_effect=subprocess.CalledProcessError(7, ["python"])), patch.object(setup, "run_tunnel") as connect, redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError):
                setup.main(["--data-dir", str(self.directory)])
        connect.assert_not_called()

    def test_key_requires_explicit_environment_selection(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "unrelated-secret", "CONTROL_PLANE_API_KEY": "not-authorized-secret", "LAYA_TEST_KEY": "selected-secret"}), patch.object(setup.sys.stdin, "isatty", return_value=False):
            with self.assertRaisesRegex(ValueError, "interactive terminal"):
                setup.runtime_key()
            self.assertEqual(setup.runtime_key("LAYA_TEST_KEY"), "selected-secret")

    def test_child_environment_does_not_inherit_other_tunnels_or_openai_keys(self):
        previous = {"OPENAI_API_KEY": "other-secret", "OPENAI_ADMIN_KEY": "admin-secret", "TUNNEL_CLIENT_CONFIG": "other.yaml", "MCP_SERVER_URL": "https://example.invalid", "CONTROL_PLANE_BASE_URL": "https://example.invalid", "PATH": "system-path"}
        with patch.dict(os.environ, previous, clear=True):
            child = setup.child_environment(self.directory, "cpu", "selected-secret")
        self.assertEqual(child["CONTROL_PLANE_API_KEY"], "selected-secret")
        self.assertEqual(child["LAYA_HOME"], str(self.directory))
        self.assertEqual(child["PATH"], "system-path")
        for name in previous.keys() - {"PATH"}:
            self.assertNotIn(name, child)

    def test_mcp_command_handles_spaces_quotes_and_shell_symbols(self):
        python = self.directory / "user's data $value & tools" / "python.exe"
        self.assertEqual(shlex.split(setup.mcp_command(python)), [python.as_posix(), "-I", "-Xutf8", "-m", "laya_agent_kit.server", "--stdio"])

    def test_invalid_tunnel_id_is_rejected_before_download(self):
        with patch.object(setup, "ensure_tunnel_client") as download:
            with self.assertRaises(ValueError):
                setup.main(["--tunnel-id", "invalid"])
        download.assert_not_called()

    def test_offline_missing_tool_does_not_download(self):
        with patch.object(setup.platform, "system", return_value="Windows"), patch.object(setup.platform, "machine", return_value="AMD64"), patch.object(setup, "download_archive") as download:
            with self.assertRaises(FileNotFoundError):
                setup.ensure_tunnel_client(self.directory, offline=True)
        download.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_checksum_failure_is_not_installed_or_executed(self):
        output = io.StringIO()
        with patch.object(setup.platform, "system", return_value="Windows"), patch.object(setup.platform, "machine", return_value="AMD64"), patch.object(setup.urllib.request, "urlopen", return_value=io.BytesIO(b"bad download")), patch.object(setup.subprocess, "run") as run, redirect_stdout(output):
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                setup.ensure_tunnel_client(self.directory)
        run.assert_not_called()
        self.assertFalse((self.directory / "tools/tunnel-client" / setup.TUNNEL_VERSION / "windows-amd64").exists())

    def test_archive_traversal_and_links_are_rejected_before_extraction(self):
        for name in ("../escape", "/absolute", "C:/escape", "nested\\escape", "link"):
            with self.subTest(name=name):
                archive = self.directory / "test.zip"
                with zipfile.ZipFile(archive, "w") as package:
                    package.writestr("normal", "ok")
                    member = zipfile.ZipInfo(name)
                    member.filename = name
                    if name == "link":
                        member.external_attr = (stat.S_IFLNK | 0o777) << 16
                    package.writestr(member, "bad")
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    setup.extract_archive(archive, self.directory / "output")
                self.assertFalse((self.directory / "output").exists())

    def test_failed_doctor_prevents_start_and_never_persists_key(self):
        calls = []

        def fake_run(command, **options):
            calls.append(command)
            self.assertNotIn("private-test-key", " ".join(command))
            self.assertEqual(options["env"]["CONTROL_PLANE_API_KEY"], "private-test-key")
            if command[1] == "init":
                profile = Path(command[command.index("--profile-dir") + 1]) / "laya.yaml"
                profile.write_text("control_plane:\n  api_key: env:CONTROL_PLANE_API_KEY\n")
            if command[1] == "doctor":
                raise subprocess.CalledProcessError(2, command)

        with patch.object(setup.subprocess, "run", side_effect=fake_run), redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(subprocess.CalledProcessError):
                setup.run_tunnel(Path("tunnel-client"), Path(sys.executable), self.directory, "cpu", self.tunnel_id, "private-test-key")
        self.assertEqual([command[1] for command in calls], ["init", "doctor"])
        self.assertNotIn("private-test-key", output.getvalue())
        self.assertFalse(list(self.directory.rglob("*.yaml")))

    def test_foreground_exit_is_propagated_and_session_profile_is_removed(self):
        commands = []

        def fake_run(command, **options):
            commands.append(command)
            if command[1] == "run":
                raise subprocess.CalledProcessError(19, command)

        with patch.object(setup.subprocess, "run", side_effect=fake_run), redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                setup.run_tunnel(Path("tunnel-client"), Path(sys.executable), self.directory, "cpu", self.tunnel_id, "private-test-key")
        self.assertEqual(caught.exception.returncode, 19)
        self.assertEqual([command[1] for command in commands], ["init", "doctor", "run"])
        self.assertNotIn("private-test-key", output.getvalue())
        self.assertFalse(list(self.directory.rglob("session-*")))

    def test_same_directory_tunnel_lock_prevents_duplicate_runtime(self):
        with setup.tunnel_lock(self.directory, self.tunnel_id):
            with self.assertRaisesRegex(RuntimeError, "already running"):
                with setup.tunnel_lock(self.directory, self.tunnel_id):
                    self.fail("A duplicate tunnel acquired the lock")
        with setup.tunnel_lock(self.directory, self.tunnel_id):
            pass


if __name__ == "__main__":
    unittest.main()
