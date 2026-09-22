from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent-kit/src"))

import tomlkit

from laya_agent_kit import clients
from laya_agent_kit.cli import make_parser, run
from laya_agent_kit.models import MODEL_FILES, MODEL_REVISION, missing_model_files, model_directories, prepare_models


class ClientInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="laya agent kit ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "user home"
        self.data = self.root / "model cache"

    def install(self, client, **options):
        changes, target = clients.plan_install(client, self.data, user_home=self.home, **options)
        return clients.apply_changes(changes), target

    def test_codex_preserves_comments_unrelated_servers_and_settings(self):
        config = self.home / ".codex/config.toml"
        config.parent.mkdir(parents=True)
        original = '# Keep this comment\nmodel = "custom"\n[mcp_servers.other]\ncommand = "unrelated"\n[mcp_servers.other.env]\nTOKEN = "private-value"\n'
        config.write_text(original, encoding="utf-8")
        original_bytes = config.read_bytes()
        result, _ = self.install("codex")
        text = config.read_text(encoding="utf-8")
        parsed = tomlkit.parse(text)
        self.assertIn("# Keep this comment", text)
        self.assertEqual(parsed["model"], "custom")
        self.assertEqual(parsed["mcp_servers"]["other"]["env"]["TOKEN"], "private-value")
        self.assertEqual(parsed["mcp_servers"]["laya"]["env"]["LAYA_HOME"], str(self.data.resolve()))
        self.assertNotIn("private-value", json.dumps(result))
        self.assertEqual(Path(result["backups"][0]).read_bytes(), original_bytes)

    def test_json_clients_keep_authentication_projects_and_other_servers(self):
        for client in ("claude-code", "cursor", "generic"):
            with self.subTest(client=client):
                path = clients.config_path(client, self.data, self.home)
                path.parent.mkdir(parents=True, exist_ok=True)
                previous = {"auth": {"token": "private-value"}, "projects": {"other": {"allowed": True}}, "mcpServers": {"other": {"command": "existing"}}}
                path.write_text(json.dumps(previous), encoding="utf-8")
                self.install(client)
                current = json.loads(path.read_text(encoding="utf-8"))
                current["mcpServers"].pop("laya")
                self.assertEqual(current, previous)

    def test_reinstall_does_not_rewrite_files_or_create_backups(self):
        self.install("codex")
        changes, _ = clients.plan_install("codex", self.data, user_home=self.home)
        self.assertEqual(changes, [])
        self.assertEqual(clients.apply_changes(changes)["backups"], [])

    def test_conflict_is_rejected_before_any_write(self):
        path = self.home / ".claude.json"
        path.parent.mkdir(parents=True)
        original = '{"mcpServers":{"laya":{"command":"some-other-install"}}}'
        path.write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "existing laya server differs"):
            self.install("claude-code")
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        self.assertFalse(self.data.exists())

    def test_uninstall_restores_replaced_server_and_skill_preserving_later_edits(self):
        config = self.home / ".codex/config.toml"
        legacy = self.home / ".codex/skills/laya/SKILL.md"
        legacy.parent.mkdir(parents=True)
        old_skill = b"An existing local skill\n"
        legacy.write_bytes(old_skill)
        previous = {"command": "old-python", "args": ["old-bridge.py"]}
        config.write_text(tomlkit.dumps({"model": "original", "mcp_servers": {"laya": previous}}), encoding="utf-8")
        self.install("codex", replace=True)
        document = tomlkit.parse(config.read_text(encoding="utf-8"))
        document["model"] = "changed-after-install"
        document["mcp_servers"]["new-server"] = {"command": "later"}
        config.write_text(tomlkit.dumps(document), encoding="utf-8")
        changes, _ = clients.plan_uninstall("codex", self.data, user_home=self.home)
        clients.apply_changes(changes)
        restored = tomlkit.parse(config.read_text(encoding="utf-8"))
        self.assertEqual(restored["mcp_servers"]["laya"], previous)
        self.assertEqual(restored["model"], "changed-after-install")
        self.assertEqual(restored["mcp_servers"]["new-server"]["command"], "later")
        self.assertEqual(legacy.read_bytes(), old_skill)
        self.assertFalse((legacy.parent / "LOCAL-RUNTIME.md").exists())

    def test_uninstall_rejects_user_edits_to_owned_entry(self):
        _, target = self.install("claude-code")
        config = Path(target["config"])
        document = json.loads(config.read_text())
        document["mcpServers"]["laya"]["env"]["CUSTOM"] = "keep"
        config.write_text(json.dumps(document), encoding="utf-8")
        before = config.read_bytes()
        with self.assertRaisesRegex(ValueError, "edited after installation"):
            clients.plan_uninstall("claude-code", self.data, user_home=self.home)
        self.assertEqual(config.read_bytes(), before)

    def test_uninstall_rejects_user_edits_to_owned_skill(self):
        _, target = self.install("codex")
        skill = Path(target["skill"]) / "SKILL.md"
        skill.write_text("User updated this skill", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "skill was edited"):
            clients.plan_uninstall("codex", self.data, user_home=self.home)
        self.assertEqual(skill.read_text(), "User updated this skill")

    def test_uninstall_requires_ownership_and_keeps_cache(self):
        with self.assertRaisesRegex(ValueError, "unowned"):
            clients.plan_uninstall("cursor", self.data, user_home=self.home)
        self.install("cursor")
        cached = self.data / "do-not-delete.safetensors"
        cached.write_bytes(b"model data")
        changes, _ = clients.plan_uninstall("cursor", self.data, user_home=self.home)
        clients.apply_changes(changes)
        self.assertEqual(cached.read_bytes(), b"model data")

    def test_dry_run_has_no_filesystem_side_effects(self):
        changes, _ = clients.plan_install("codex", self.data, user_home=self.home)
        result = clients.apply_changes(changes, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_concurrent_config_change_is_not_overwritten(self):
        changes, target = clients.plan_install("cursor", self.data, user_home=self.home)
        config = Path(target["config"])
        config.parent.mkdir(parents=True)
        config.write_bytes(b'{"new":"concurrent user edit"}')
        with self.assertRaisesRegex(ValueError, "File changed"):
            clients.apply_changes(changes)
        self.assertEqual(config.read_bytes(), b'{"new":"concurrent user edit"}')
        self.assertFalse(self.data.exists())

    def test_failed_transaction_restores_earlier_files(self):
        first = self.root / "first.json"
        second = self.root / "second.json"
        first.write_bytes(b"old")
        real_write = clients.atomic_write

        def failing_write(path, content):
            if path == second:
                raise OSError("simulated disk failure")
            real_write(path, content)

        with patch.object(clients, "atomic_write", side_effect=failing_write):
            with self.assertRaisesRegex(OSError, "disk failure"):
                clients.apply_changes([clients.Change(first, b"old", b"new"), clients.Change(second, None, b"new")])
        self.assertEqual(first.read_bytes(), b"old")
        self.assertFalse(second.exists())

    def test_project_scope_does_not_touch_user_settings(self):
        project = self.root / "project with spaces"
        for client in ("codex", "claude-code", "cursor"):
            changes, target = clients.plan_install(client, self.data, user_home=self.home, project=project)
            clients.apply_changes(changes)
            self.assertTrue(Path(target["config"]).is_relative_to(project))
        self.assertFalse(self.home.exists())

    def test_invalid_json_and_server_container_are_rejected(self):
        for content in (b'{"broken":', b'[]', b'{"mcpServers":[]}'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                clients.parse_config("claude-code", content)

    def test_codex_home_is_respected_but_isolated_home_takes_precedence(self):
        custom = self.root / "custom codex home"
        with patch.dict(os.environ, {"CODEX_HOME": str(custom)}):
            self.assertEqual(clients.config_path("codex", self.data), custom / "config.toml")
            self.assertEqual(clients.config_path("codex", self.data, self.home), self.home / ".codex/config.toml")

    def test_runtime_configuration_keeps_argument_boundaries_and_utf8(self):
        python = self.root / "environment with spaces/bin/python"
        config = clients.server_spec("claude-code", self.data, python=python)
        self.assertEqual(config["command"], str(python.absolute()))
        self.assertEqual(config["args"], ["-I", "-X", "utf8", "-m", "laya_agent_kit.server", "--stdio"])
        self.assertEqual(config["type"], "stdio")
        self.assertEqual(config["env"]["LAYA_HOME"], str(self.data.resolve()))

    def test_cli_dry_run_does_not_import_torch_or_download(self):
        arguments = make_parser().parse_args(["install", "--client", "codex", "--user-home", str(self.home), "--data-dir", str(self.data), "--dry-run"])
        with patch("laya_agent_kit.cli.prepare_models", side_effect=AssertionError("No downloads allowed")):
            result = run(arguments)
        self.assertTrue(result["dry_run"])
        self.assertFalse(self.home.exists())

    def test_multiple_clients_cannot_share_custom_config(self):
        arguments = make_parser().parse_args(["install", "--client", "codex", "--client", "cursor", "--config", str(self.root / "shared"), "--dry-run"])
        with self.assertRaisesRegex(ValueError, "exactly one"):
            run(arguments)

    def test_codex_config_export_is_valid_toml(self):
        arguments = make_parser().parse_args(["config", "--client", "codex", "--data-dir", str(self.data)])
        output = io.StringIO()
        with redirect_stdout(output):
            run(arguments)
        parsed = tomlkit.parse(output.getvalue())
        self.assertEqual(parsed["mcp_servers"]["laya"]["env"]["LAYA_HOME"], str(self.data.resolve()))

    def test_doctor_verifies_a_compatible_legacy_launcher(self):
        config = self.home / ".codex/config.toml"
        config.parent.mkdir(parents=True)
        legacy = {"command": "python", "args": ["legacy-bridge.py"]}
        config.write_text(tomlkit.dumps({"mcp_servers": {"laya": legacy}}), encoding="utf-8")
        arguments = make_parser().parse_args(["doctor", "--client", "codex", "--user-home", str(self.home), "--data-dir", str(self.data)])
        status = {"agent_kit_version": "0.1.0", "data_directory": str(self.data)}
        with patch("laya_agent_kit.diagnostics.diagnose", return_value={"ok": True}):
            with patch("laya_agent_kit.diagnostics.diagnose_registration", return_value={"status": status}) as probe:
                result = run(arguments)
        self.assertTrue(result["ok"])
        self.assertFalse(result["clients"][0]["matches_generated_config"])
        probe.assert_called_once_with(legacy, self.data.resolve(), "auto")

    def test_doctor_rejects_a_different_data_directory(self):
        config = self.home / ".claude.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"mcpServers": {"laya": {"command": "other-python"}}}), encoding="utf-8")
        arguments = make_parser().parse_args(["doctor", "--client", "claude-code", "--user-home", str(self.home), "--data-dir", str(self.data)])
        status = {"agent_kit_version": "0.1.0", "data_directory": str(self.root / "other-model-cache")}
        with patch("laya_agent_kit.diagnostics.diagnose", return_value={"ok": True}):
            with patch("laya_agent_kit.diagnostics.diagnose_registration", return_value={"status": status}):
                result = run(arguments)
        self.assertFalse(result["ok"])


class ModelPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="laya-models-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def fill_model(self, name):
        directory = model_directories(self.directory)[name]
        for relative in MODEL_FILES:
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic test fixture")

    def test_weights_alone_do_not_count_as_a_ready_model(self):
        directory = model_directories(self.directory)["english"]
        directory.mkdir(parents=True)
        (directory / "model.safetensors").write_bytes(b"weights")
        missing = missing_model_files(self.directory)["english"]
        self.assertIn("tokenizer/tokenizer.json", missing)
        self.assertNotIn("model.safetensors", missing)
        with self.assertRaisesRegex(FileNotFoundError, "incomplete"):
            prepare_models(self.directory, ["english"], offline=True)

    def test_complete_subset_works_offline_without_unselected_models(self):
        self.fill_model("english")
        result = prepare_models(self.directory, ["english"], offline=True)
        self.assertEqual(set(result), {"english"})
        self.assertTrue(missing_model_files(self.directory)["multilingual"])

    def test_download_is_revision_pinned_and_requests_only_missing_selected_files(self):
        self.fill_model("english")

        def download(*arguments, **options):
            self.fill_model("multilingual")

        with patch("huggingface_hub.snapshot_download", side_effect=download) as snapshot:
            prepare_models(self.directory, ["english", "multilingual"])
        self.assertEqual(snapshot.call_args.kwargs["revision"], MODEL_REVISION)
        self.assertTrue(all(name.startswith("multilingual/") for name in snapshot.call_args.kwargs["allow_patterns"]))

    def test_partial_download_never_reports_success(self):
        with patch("huggingface_hub.snapshot_download"):
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                prepare_models(self.directory, ["english"])


if __name__ == "__main__":
    unittest.main()
