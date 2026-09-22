from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import install
import start_chatgpt
from laya_agent_kit.provision import CPU_INDEX, hardware_inventory, torch_install_plan


class ProvisionTests(unittest.TestCase):
    def hardware(self, vendor="amd", system="Windows"):
        return {"system": system, "vendors": [vendor]}

    def test_fresh_amd_and_unknown_hardware_get_cpu_wheels(self):
        for vendor in ("amd", "intel", "unknown"):
            for system in ("Windows", "Linux"):
                with self.subTest(vendor=vendor, system=system):
                    plan = torch_install_plan("auto", None, False, self.hardware(vendor, system), None)
                    self.assertEqual(plan["index_url"], CPU_INDEX)

    def test_existing_rocm_and_cuda_builds_are_preserved(self):
        for existing in ({"hip_version": "synthetic"}, {"cuda_version": "synthetic"}):
            plan = torch_install_plan("auto", None, False, self.hardware(), existing)
            self.assertFalse(plan["replace_torch"])
            self.assertIsNone(plan["index_url"])

    def test_fresh_nvidia_and_mac_use_platform_default_wheels(self):
        for hardware in (self.hardware("nvidia"), self.hardware("apple", "Darwin")):
            self.assertIsNone(torch_install_plan("auto", None, False, hardware, None)["index_url"])

    def test_rocm_requires_explicit_compatible_wheels(self):
        with self.assertRaisesRegex(ValueError, "does not guess a ROCm release"):
            torch_install_plan("rocm", None, False, self.hardware(), None)
        self.assertIsNone(torch_install_plan("rocm", None, False, self.hardware(), {"hip_version": "synthetic"})["index_url"])

    def test_explicit_index_and_offline_rules(self):
        plan = torch_install_plan("cpu", CPU_INDEX, False, self.hardware(), {"cuda_version": "synthetic"})
        self.assertTrue(plan["replace_torch"])
        with self.assertRaisesRegex(ValueError, "official"):
            torch_install_plan("auto", "https://example.invalid/torch", False, self.hardware(), None)
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            torch_install_plan("auto", CPU_INDEX, True, self.hardware(), None)
        self.assertIsNone(torch_install_plan("rocm", None, True, self.hardware(), None)["index_url"])

    def test_windows_inventory_does_not_treat_amd_as_nvidia(self):
        result = subprocess.CompletedProcess([], 0, '["AMD Radeon Graphics", "Intel UHD Graphics"]', '')
        with patch("laya_agent_kit.provision.platform.system", return_value="Windows"), \
             patch("laya_agent_kit.provision.subprocess.run", return_value=result):
            hardware = hardware_inventory()
        self.assertEqual(hardware["vendors"], ["amd", "intel"])

    def test_hardware_detection_failure_is_visible_and_nonfatal(self):
        with patch("laya_agent_kit.provision.platform.system", return_value="Windows"), \
             patch("laya_agent_kit.provision.subprocess.run", side_effect=FileNotFoundError("PowerShell unavailable")):
            hardware = hardware_inventory()
        self.assertEqual(hardware["vendors"], [])
        self.assertIn("PowerShell unavailable", hardware["detection_errors"][0])

    def test_rocm_error_does_not_create_environment_or_install_packages(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(install, "hardware_inventory", return_value=self.hardware()), \
             patch.object(install, "existing_torch", return_value=None), patch.object(install.subprocess, "run") as process, \
             redirect_stderr(io.StringIO()):
            directory = Path(temporary) / "new environment"
            with self.assertRaises(SystemExit):
                install.main(["--venv", str(directory), "--device", "rocm"])
            self.assertFalse(directory.exists())
            process.assert_not_called()

    def test_dry_run_does_not_detect_hardware_or_create_environment(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(install, "hardware_inventory") as detect, redirect_stdout(io.StringIO()):
            directory = Path(temporary) / "new environment"
            install.main(["--venv", str(directory), "--device", "rocm", "--dry-run"])
            self.assertFalse(directory.exists())
            detect.assert_not_called()

    def test_bootstrap_preflights_before_models_or_registration(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(install, "hardware_inventory", return_value=self.hardware()), \
             patch.object(install, "existing_torch", return_value={"hip_version": "synthetic"}), \
             patch.object(install.venv.EnvBuilder, "create"), patch.object(install.subprocess, "run") as process, redirect_stdout(io.StringIO()):
            install.main(["--venv", str(Path(temporary) / "new environment"), "--device", "rocm", "--client", "generic"])
            commands = [call.args[0] for call in process.call_args_list]
        preflight = next(index for index, command in enumerate(commands) if "hardware" in command)
        registration = next(index for index, command in enumerate(commands) if "laya_agent_kit" in command and "install" in command)
        self.assertLess(preflight, registration)
        self.assertIn("rocm", commands[registration])
        self.assertFalse(any("--force-reinstall" in command for command in commands))

    def test_chatgpt_entrypoint_accepts_rocm(self):
        self.assertEqual(start_chatgpt.make_parser().parse_args(["--device", "rocm"]).device, "rocm")


if __name__ == "__main__":
    unittest.main()
