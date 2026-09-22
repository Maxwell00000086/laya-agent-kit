from contextlib import ExitStack
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import weakref


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent-kit/src"))

from laya_agent_kit.server import JudgeRequest, LocalRuntime


class CyclicCheckpoint:
    def __init__(self):
        self.cycle = self
        self.device = "cpu"
        self.tok = None
        self.cfg = {}

    def predict(self, state, questions):
        return {"answers": {"present": {"confidence": 0.9, "noul": 0.9}}, "usage": {}}


class SingleCheckpointMemory:
    def __init__(self):
        self.cache = {}
        self.previous = None
        self.created = []
        self.fail_model = None

    @property
    def loaded(self):
        return list(self.cache)

    def route(self, state, questions, model):
        return {"model": model, "reason": "explicit test model"}

    def load(self, model):
        if model in self.cache:
            return self.cache[model]
        if self.previous is not None and self.previous() is not None:
            raise MemoryError("The previous checkpoint still consumes the memory budget")
        if model == self.fail_model:
            raise OSError("Replacement checkpoint failed to load")
        checkpoint = CyclicCheckpoint()
        self.previous = weakref.ref(checkpoint)
        self.cache[model] = checkpoint
        self.created.append(model)
        return checkpoint

    def unload(self):
        self.cache.clear()


class RuntimeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.runtime = LocalRuntime()
        self.runtime.router = SingleCheckpointMemory()
        self.runtime.selection = {"requested_device": "auto", "selected_backend": "cpu", "fallback_reason": None}
        self.missing = {"english": [], "multilingual": [], "typed-decisions": []}
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(patch("laya_agent_kit.server.missing_model_files", return_value=self.missing))
        self.patches.enter_context(patch("laya_agent_kit.server.check_budget", return_value={}))
        self.patches.enter_context(patch.dict(sys.modules, {"torch": SimpleNamespace(cuda=SimpleNamespace(is_initialized=lambda: False))}))

    def request(self, model):
        return JudgeRequest(
            state="A visible label is present.",
            questions={"present": {"type": "noul", "instructions": "Is a label present?"}},
            model=model,
        )

    def test_switch_fits_single_checkpoint_memory_and_reuses_warm_model(self):
        self.runtime.judge(self.request("english"))
        self.runtime.judge(self.request("english"))
        self.assertEqual(self.runtime.router.created, ["english"])
        self.runtime.judge(self.request("typed-decisions"))
        self.runtime.judge(self.request("typed-decisions"))
        self.assertEqual(self.runtime.router.created, ["english", "typed-decisions"])
        self.assertEqual(self.runtime.router.loaded, ["typed-decisions"])

    def test_missing_checkpoint_keeps_working_model(self):
        self.runtime.judge(self.request("english"))
        self.missing["typed-decisions"] = ["model.safetensors"]
        with self.assertRaisesRegex(ValueError, "MODEL_NOT_INSTALLED"):
            self.runtime.judge(self.request("typed-decisions"))
        self.runtime.judge(self.request("english"))
        self.assertEqual(self.runtime.router.created, ["english"])

    def test_failed_replacement_allows_loading_previous_model_again(self):
        self.runtime.judge(self.request("english"))
        self.runtime.router.fail_model = "typed-decisions"
        with self.assertRaisesRegex(OSError, "Replacement checkpoint failed"):
            self.runtime.judge(self.request("typed-decisions"))
        self.assertEqual(self.runtime.router.loaded, [])
        self.runtime.judge(self.request("english"))
        self.assertEqual(self.runtime.router.created, ["english", "english"])


if __name__ == "__main__":
    unittest.main()
