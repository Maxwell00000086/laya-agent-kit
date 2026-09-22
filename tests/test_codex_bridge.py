import json
from pathlib import Path
import subprocess
import sys
import unittest

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codex_bridge import JudgeRequest, MODEL_DIRECTORIES, Question, RankRequest, check_budget


class RequestValidationTests(unittest.TestCase):
    def test_duplicate_source_ids_are_rejected(self):
        passage = {"id": "same", "source": "synthetic:test", "text": "Evidence"}
        with self.assertRaises(ValidationError):
            RankRequest(goal="Relevance", passages=[passage, passage])

    def test_oversized_choice_and_unknown_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            Question(type="choice", instructions="Pick", criteria={str(index): "option" for index in range(9)})
        with self.assertRaises(ValidationError):
            JudgeRequest(state="Evidence", questions={"check": {"type": "noul", "instructions": "Present?"}}, execute=True)

    def test_missing_evidence_and_rubric_are_rejected(self):
        with self.assertRaises(ValidationError):
            JudgeRequest(state=" ", questions={"check": {"type": "noul", "instructions": "Present?"}})
        with self.assertRaises(ValidationError):
            Question(type="score", instructions="Quality", criteria=["good", "good"])

    def test_status_is_valid_json_without_loading_models(self):
        bridge_path = Path(__file__).resolve().parents[1] / "codex_bridge.py"
        completed = subprocess.run([sys.executable, str(bridge_path), "--status"], capture_output=True, text=True, check=True)
        status = json.loads(completed.stdout)
        self.assertTrue(status["offline"])
        self.assertEqual(status["loaded_models"], [])


class TokenBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from transformers import AutoTokenizer

        cls.tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIRECTORIES["english"] / "tokenizer"), local_files_only=True)
        cls.config = json.loads((MODEL_DIRECTORIES["english"] / "rl_agent_config.json").read_text())
        cls.question = {"check": {"type": "noul", "instructions": "Does the evidence mention a label?"}}

    def test_allowed_input_is_not_truncated_by_upstream_packer(self):
        from laya.common import build_sequence

        state = "The email input has a visible label."
        budget = check_budget(self.tokenizer, self.config, state, self.question)["check"]
        internal = {"t": "noul", "ins": self.question["check"]["instructions"], "crit": None}
        packed, _ = build_sequence(self.tokenizer, state, internal, self.config["max_len"], self.config["head_max_len"])
        state_ids = self.tokenizer(state, add_special_tokens=False)["input_ids"]
        self.assertEqual(packed[-len(state_ids) - 1:-1], state_ids)
        self.assertFalse(budget["truncated"])

    def test_overlong_state_is_rejected_instead_of_losing_ending(self):
        with self.assertRaisesRegex(ValueError, "INPUT_TOO_LONG.*Split the source"):
            check_budget(self.tokenizer, self.config, "ordinary " * 1200 + "critical exception at the end", self.question)

    def test_long_instructions_and_option_descriptions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "prompt budget"):
            check_budget(self.tokenizer, self.config, "Evidence", {"check": {"type": "noul", "instructions": "explain " * 300}})
        with self.assertRaisesRegex(ValueError, "option exceeds 48 tokens"):
            check_budget(self.tokenizer, self.config, "Evidence", {
                "check": {"type": "choice", "instructions": "Pick", "criteria": {"first": "description " * 70, "other": "unknown"}}
            })


if __name__ == "__main__":
    unittest.main()
