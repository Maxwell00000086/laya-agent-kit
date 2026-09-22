from contextlib import ExitStack
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent-kit/src"))

from laya_agent_kit.backends import execution_report, select_device
from laya_agent_kit.clients import server_spec
from laya_agent_kit.cli import make_parser
from laya_agent_kit.server import JudgeRequest, LocalRuntime


def simulated_torch(backend=None, available=True):
    return SimpleNamespace(
        __version__="synthetic",
        version=SimpleNamespace(hip="synthetic-hip" if backend == "rocm" else None, cuda="synthetic-cuda" if backend == "cuda" else None),
        cuda=SimpleNamespace(is_available=lambda: available and backend in ("cuda", "rocm"), get_device_name=lambda index: "Synthetic GPU"),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: available and backend == "mps")),
    )


class BackendTests(unittest.TestCase):
    def selection(self, backend=None, requested="auto", available=True):
        with patch.dict(sys.modules, {"torch": simulated_torch(backend, available)}):
            return select_device(requested)

    def test_rocm_uses_cuda_api_without_being_reported_as_nvidia(self):
        selected = self.selection("rocm", "rocm")
        result = execution_report(selected, "cuda:0")
        self.assertEqual(selected["selected_device"], "cuda")
        self.assertEqual(result["actual_backend"], "rocm")
        self.assertIsNone(result["cuda_version"])

    def test_legacy_cuda_request_accepts_hip_but_rocm_rejects_nvidia(self):
        self.assertEqual(self.selection("rocm", "cuda")["selected_backend"], "rocm")
        with self.assertRaisesRegex(RuntimeError, "BACKEND_UNAVAILABLE"):
            self.selection("cuda", "rocm")

    def test_auto_handles_cpu_cuda_rocm_and_mps(self):
        for backend in (None, "cuda", "rocm", "mps"):
            with self.subTest(backend=backend):
                selected = self.selection(backend)
                self.assertEqual(selected["selected_backend"], backend or "cpu")
                self.assertEqual(bool(selected["fallback_reason"]), backend is None)

    def test_cpu_override_does_not_use_available_gpu(self):
        selected = self.selection("rocm", "cpu")
        self.assertEqual(selected["selected_device"], "cpu")
        self.assertIsNone(selected["fallback_reason"])

    def test_missing_driver_falls_back_only_in_auto_mode(self):
        selected = self.selection("rocm", available=False)
        self.assertEqual(selected["selected_backend"], "cpu")
        self.assertIsNotNone(selected["fallback_reason"])
        with self.assertRaisesRegex(RuntimeError, "BACKEND_UNAVAILABLE"):
            self.selection("rocm", "rocm", available=False)

    def test_detection_error_is_reported_with_cpu_fallback(self):
        runtime = simulated_torch("cuda")
        runtime.cuda.is_available = Mock(side_effect=RuntimeError("driver initialization failed"))
        with patch.dict(sys.modules, {"torch": runtime}):
            selected = select_device()
        self.assertIn("driver initialization failed", selected["fallback_reason"])
        self.assertEqual(selected["selected_backend"], "cpu")

    def test_explicit_gpu_request_cannot_pass_with_cpu_output(self):
        for backend in ("cuda", "rocm", "mps"):
            with self.subTest(backend=backend):
                with self.assertRaisesRegex(RuntimeError, "BACKEND_FALLBACK"):
                    execution_report(self.selection(backend, backend), "cpu", "synthetic allocation failure")

    def test_auto_preserves_actual_device_and_fallback_reason(self):
        result = execution_report(self.selection("rocm"), "cpu", "HIP kernel unavailable")
        self.assertEqual(result["selected_backend"], "rocm")
        self.assertEqual(result["actual_backend"], "cpu")
        self.assertEqual(result["fallback_reason"], "HIP kernel unavailable")

    def test_experimental_backends_fail_before_torch_import(self):
        with patch("laya_agent_kit.backends.torch_capabilities") as inspect:
            for backend in ("directml", "onnx"):
                with self.assertRaisesRegex(ValueError, "not implemented"):
                    select_device(backend)
        inspect.assert_not_called()

    def test_cli_and_mcp_registration_preserve_backend_selection(self):
        arguments = make_parser().parse_args(["hardware", "--device", "rocm"])
        self.assertEqual(arguments.device, "rocm")
        registration = server_spec("codex", "synthetic-cache", device="rocm")
        self.assertEqual(registration["env"]["LAYA_DEVICE"], "rocm")

    def test_mcp_reports_runtime_fallback_and_keeps_cpu_for_next_model(self):
        runtime = LocalRuntime()
        runtime.selection = self.selection("rocm")
        agent = SimpleNamespace(device="cuda", tok=None, cfg={}, fallback_reason=None)

        def predict(state, questions):
            agent.device = "cpu"
            agent.fallback_reason = "HIP kernel unavailable"
            return {"answers": {"label": {"confidence": 0.9, "noul": 0.9}}, "usage": {}}

        agent.predict = predict
        runtime.router = SimpleNamespace(
            device="cuda", loaded=["english"],
            route=lambda *args, **kwargs: {"model": "english", "reason": "synthetic"}, load=lambda model: agent,
        )
        request = JudgeRequest(state="A visible label is present.", questions={"label": {"type": "noul", "instructions": "Is a label present?"}})
        with ExitStack() as patches:
            patches.enter_context(patch("laya_agent_kit.server.missing_model_files", return_value={"english": []}))
            patches.enter_context(patch("laya_agent_kit.server.check_budget", return_value={}))
            result = runtime.judge(request)
            self.assertEqual(runtime.judge(request)["runtime"]["fallback_reason"], "HIP kernel unavailable")
        self.assertEqual(result["runtime"]["actual_backend"], "cpu")
        self.assertEqual(runtime.router.device, "cpu")
        runtime.selection["requested_device"] = "rocm"
        with self.assertRaisesRegex(RuntimeError, "BACKEND_FALLBACK"):
            runtime.describe_execution(agent)

    def test_diagnosis_rejects_cpu_receipt_for_explicit_rocm(self):
        from laya_agent_kit.diagnostics import diagnose

        selection = self.selection("rocm", "rocm")
        with patch("laya_agent_kit.diagnostics.runtime_info", return_value={"runtime": selection}), \
             patch("laya_agent_kit.diagnostics.missing_model_files", return_value={"english": []}), \
             patch("anyio.run", return_value={"inference": {"device": "cpu"}}):
            with self.assertRaisesRegex(RuntimeError, "BACKEND_FALLBACK"):
                diagnose(Path("cache"), "rocm", ["english"], "english")


if __name__ == "__main__":
    unittest.main()
