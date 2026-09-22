from contextlib import ExitStack, nullcontext, redirect_stdout
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import torch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from laya.agent import Agent, _inference_dtype


class DeviceRuntimeTests(unittest.TestCase):
    def test_precision_uses_bf16_support_without_nvidia_architecture_assumptions(self):
        for available in (True, False):
            with self.subTest(available=available), patch.object(torch.cuda, "is_bf16_supported", return_value=available), \
                 patch.object(torch.cuda, "get_device_capability", side_effect=AssertionError("NVIDIA capability queried for HIP")):
                self.assertEqual(_inference_dtype(torch.device("cuda"), torch.bfloat16), torch.bfloat16 if available else torch.float16)
                self.assertEqual(_inference_dtype(torch.device("cuda"), torch.float16), torch.float16)

    def test_cpu_and_mps_use_float32(self):
        for backend in ("cpu", "mps"):
            self.assertEqual(_inference_dtype(torch.device(backend), torch.bfloat16), torch.float32)

    def predict_with_failure(self, failure, second_failure=None):
        agent = Agent.__new__(Agent)
        agent.device = torch.device("cuda")
        agent.dtype = torch.float16
        agent.fallback_reason = None
        agent.tok = SimpleNamespace(pad_token_id=0)
        agent.cfg = {"max_len": 512, "head_max_len": 192}
        agent.temperature = [1.0, 1.0, 1.0]
        agent.temperature_by_options = {}
        result = (torch.tensor([[0.0, 1.0]]), torch.tensor([[1.0, 0.0]]))
        agent.model = Mock(side_effect=[failure, second_failure or result])
        batch = {name: torch.ones(1, 2, dtype=torch.long) for name in ("input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype")}
        patches = ExitStack()
        self.addCleanup(patches.close)
        patches.enter_context(patch("laya.agent.build_sequence", return_value=([1, 2], [0, 1])))
        patches.enter_context(patch("laya.agent.collate_items", return_value=batch))
        patches.enter_context(patch.object(torch, "autocast", return_value=nullcontext()))
        patches.enter_context(patch.object(torch.Tensor, "to", lambda tensor, *args, **kwargs: tensor))
        return agent

    def test_hip_kernel_error_retries_on_cpu_and_preserves_reason(self):
        agent = self.predict_with_failure(RuntimeError("HIP error: no kernel image is available"))
        with redirect_stdout(io.StringIO()):
            result = agent.predict("A label is present", {"label": {"type": "noul", "instructions": "Is there a label?"}})
        self.assertEqual(agent.device.type, "cpu")
        self.assertIn("HIP error", agent.fallback_reason)
        self.assertEqual(agent.model.call_count, 2)
        self.assertGreater(result["answers"]["label"]["noul"], 0.5)

    def test_unrelated_shape_error_does_not_trigger_fallback(self):
        agent = self.predict_with_failure(RuntimeError("shape mismatch"))
        with self.assertRaisesRegex(RuntimeError, "shape mismatch"):
            agent.predict("A label is present", {"label": {"type": "noul", "instructions": "Is there a label?"}})
        self.assertEqual(agent.device.type, "cuda")
        self.assertIsNone(agent.fallback_reason)
        self.assertEqual(agent.model.call_count, 1)

    def test_failed_cpu_retry_is_not_reported_as_success(self):
        agent = self.predict_with_failure(RuntimeError("HIP error"), RuntimeError("CPU allocation failed"))
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "CPU allocation failed"):
            agent.predict("A label is present", {"label": {"type": "noul", "instructions": "Is there a label?"}})
        self.assertEqual(agent.model.call_count, 2)


if __name__ == "__main__":
    unittest.main()
