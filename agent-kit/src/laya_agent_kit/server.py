import argparse
from contextlib import redirect_stdout
import gc
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
from typing import Literal

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import __version__
from .backends import execution_report, select_device
from .models import MODEL_REVISION, data_directory, missing_model_files, model_directories


DATA_DIRECTORY = data_directory()
MODEL_DIRECTORIES = model_directories(DATA_DIRECTORY)
ModelName = Literal["auto", "english", "multilingual", "typed-decisions"]

os.environ["HF_HOME"] = str(DATA_DIRECTORY / "huggingface")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TORCH_HOME"] = str(DATA_DIRECTORY / "torch")
os.environ["USE_TF"] = "0"
os.environ["TOKENIZERS_PARALLELISM"] = "false"


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["choice", "score", "noul"]
    instructions: str = Field(min_length=1, max_length=1200)
    criteria: dict[str, str] | list[str] | None = None

    @model_validator(mode="after")
    def validate_criteria(self):
        if not self.instructions.strip():
            raise ValueError("Question instructions must not be blank")
        if self.type == "noul":
            if self.criteria is not None:
                raise ValueError("noul uses instructions only; omit criteria")
            return self
        expected_type = dict if self.type == "choice" else list
        if not isinstance(self.criteria, expected_type) or not 2 <= len(self.criteria) <= 8:
            raise ValueError("choice needs 2-8 named options; score needs 2-8 ordered rubric levels")
        values = list(self.criteria) + list(self.criteria.values()) if isinstance(self.criteria, dict) else self.criteria
        if any(not value.strip() or len(value) > 1200 for value in values):
            raise ValueError("Criteria must be nonblank short text")
        if isinstance(self.criteria, list) and len(set(self.criteria)) != len(self.criteria):
            raise ValueError("Score rubric levels must be distinct")
        return self


class JudgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str = Field(min_length=1, max_length=24000)
    questions: dict[str, Question] = Field(min_length=1, max_length=8)
    model: ModelName = "auto"

    @model_validator(mode="after")
    def validate_identifiers(self):
        if not self.state.strip():
            raise ValueError("Evidence must not be blank")
        if any(not identifier.strip() or len(identifier) > 64 for identifier in self.questions):
            raise ValueError("Question IDs must be nonblank and at most 64 characters")
        return self


class Passage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=16000)
    source: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def validate_text(self):
        if any(not value.strip() for value in (self.id, self.text, self.source)):
            raise ValueError("Passage ID, evidence text and source must not be blank")
        return self


class RankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(min_length=1, max_length=1200)
    passages: list[Passage] = Field(min_length=1, max_length=16)
    model: ModelName = "auto"

    @model_validator(mode="after")
    def validate_passages(self):
        if not self.goal.strip():
            raise ValueError("Research goal must not be blank")
        if len({passage.id for passage in self.passages}) != len(self.passages):
            raise ValueError("Passage IDs must be unique")
        return self


def check_budget(tokenizer, config, state, questions):
    from laya.common import render_options

    mask_token = tokenizer.mask_token

    def token_count(text):
        return len(tokenizer(text.replace(mask_token, " "), add_special_tokens=False)["input_ids"])

    state_tokens = token_count(state)
    budgets = {}
    for identifier, question in questions.items():
        internal = {"t": question["type"], "ins": question["instructions"], "crit": question.get("criteria")}
        option_lengths = [token_count(" " + option) for option in render_options(internal)]
        if any(length > 48 for length in option_lengths):
            raise ValueError(f"INPUT_TOO_LONG: {identifier} option exceeds 48 tokens; shorten its description")
        option_tokens = sum(length + 1 for length in option_lengths)
        instruction_budget = config["head_max_len"] - option_tokens
        instruction_tokens = token_count(f"{question['type']} question: {question['instructions']}")
        if instruction_budget < 16 or instruction_tokens > instruction_budget:
            raise ValueError(f"INPUT_TOO_LONG: {identifier} question/options exceed the prompt budget; use fewer or shorter options")
        state_budget = config["max_len"] - instruction_tokens - option_tokens - 4
        if state_tokens > state_budget:
            raise ValueError(f"INPUT_TOO_LONG: {identifier} evidence has {state_tokens} tokens; budget is {state_budget}. Split the source and preserve its citations.")
        budgets[identifier] = {"state_tokens": state_tokens, "state_budget": state_budget, "truncated": False}
    return budgets


class LocalRuntime:
    def __init__(self):
        self.router = None
        self.selection = None
        self.last_execution = None
        self.lock = threading.RLock()

    def get_router(self):
        if self.router is None:
            with redirect_stdout(sys.stderr):
                from laya import Router

                device = os.environ.get("LAYA_DEVICE", "auto")
                self.selection = select_device(device)
                self.router = Router(
                    models={name: str(directory) for name, directory in MODEL_DIRECTORIES.items()},
                    device=self.selection["selected_device"],
                    max_loaded=1,
                )
        return self.router

    def status(self):
        with self.lock:
            return {
                "agent_kit_version": __version__,
                "laya_version": version("laya"),
                "mcp_version": version("mcp"),
                "offline": True,
                "model_revision": MODEL_REVISION,
                "cached_models": {name: not missing for name, missing in missing_model_files(DATA_DIRECTORY).items()},
                "data_directory": str(DATA_DIRECTORY),
                "loaded_models": self.router.loaded if self.router else [],
                "runtime": self.last_execution or self.selection or {"requested_device": os.environ.get("LAYA_DEVICE", "auto"), "actual_device": None, "actual_backend": None},
                "inference_verified": self.last_execution is not None,
                "unimplemented_backends": ["directml", "onnx"],
                "context_tokens": {"english": 512, "multilingual": 1024, "typed-decisions": 1024},
                "limits": {"questions": 8, "options_per_question": 8, "passages": 16},
                "capabilities": ["typed judgments over supplied text", "passage relevance ranking"],
                "limitations": ["no browsing, screenshots or text generation", "task accuracy and probabilities are not calibrated"],
            }

    def judge(self, request):
        with self.lock, redirect_stdout(sys.stderr):
            started = time.perf_counter()
            router = self.get_router()
            questions = {identifier: question.model_dump(exclude_none=True) for identifier, question in request.questions.items()}
            decision = router.route(request.state, questions, model=None if request.model == "auto" else request.model)
            missing = missing_model_files(DATA_DIRECTORY)[decision["model"]]
            if missing:
                raise ValueError(f"MODEL_NOT_INSTALLED: {decision['model']}. Run laya-agent-kit download for this model. Missing files: {', '.join(missing)}")
            if router.loaded and decision["model"] not in router.loaded:
                router.unload()
                gc.collect()
                import torch

                if torch.cuda.is_initialized():
                    torch.cuda.empty_cache()
            agent = router.load(decision["model"])
            self.describe_execution(agent)
            budgets = check_budget(agent.tok, agent.cfg, request.state, questions)
            result = agent.predict(request.state, questions)
            execution = self.describe_execution(agent)
            answers = {}
            for identifier, answer in result["answers"].items():
                answers[identifier] = {key: value for key, value in answer.items() if key != "action"}
                numbers = [answer["confidence"], *answer.get("probabilities", {}).values()]
                numbers.extend(answer[key] for key in ("score", "noul") if key in answer)
                if not all(math.isfinite(number) for number in numbers):
                    raise RuntimeError("Model returned a non-finite result; no decision is available")
            self.last_execution = execution
            return {
                "engine": "local_laya",
                "advisory": True,
                "calibrated_for_task": False,
                "model": decision["model"],
                "model_revision": MODEL_REVISION,
                "device": str(agent.device),
                "runtime": execution,
                "routing_reason": decision["reason"],
                "answers": answers,
                "input_budget": budgets,
                "usage": result["usage"],
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            }

    def describe_execution(self, agent):
        previous_reason = self.last_execution.get("fallback_reason") if self.last_execution else None
        execution = execution_report(self.selection, agent.device, getattr(agent, "fallback_reason", None) or previous_reason)
        if execution["actual_backend"] == "cpu" and self.selection["requested_device"] == "auto":
            self.router.device = "cpu"
        return execution

    def rank(self, request):
        questions = {
            "relevance": Question(
                type="score",
                instructions="How relevant is the passage to the research goal? Judge the supplied text only.",
                criteria=["unrelated", "loosely related", "useful supporting information", "directly addresses the goal"],
            )
        }
        ranked = []
        for passage in request.passages:
            evidence = f"Research goal: {request.goal}\n\nPassage:\n{passage.text}"
            try:
                result = self.judge(JudgeRequest(state=evidence, questions=questions, model=request.model))
            except ValueError as error:
                raise ValueError(f"Passage {passage.id}: {error}") from error
            answer = result["answers"]["relevance"]
            ranked.append({
                "id": passage.id,
                "source": passage.source,
                "score": answer["score"],
                "confidence": answer["confidence"],
                "probabilities": answer["probabilities"],
                "model": result["model"],
                "device": result["device"],
                "runtime": result["runtime"],
                "input_budget": result["input_budget"]["relevance"],
            })
        ranked.sort(key=lambda passage: passage["score"], reverse=True)
        return {
            "engine": "local_laya",
            "advisory": True,
            "calibrated_for_task": False,
            "goal": request.goal,
            "ranked": ranked,
            "discarded_passages": 0,
            "note": "All supplied IDs are retained. Scores suggest review order, not source truth or permission to discard evidence.",
        }


runtime = LocalRuntime()
server = FastMCP(
    "laya",
    instructions="Local offline Laya supplies advisory text judgments and passage rankings. Supply short evidence, explicit questions and source IDs. It cannot browse, see screenshots or synthesize documents. Confidence is not task-calibrated. The host AI verifies sources and makes final decisions. Oversized inputs are rejected; split evidence and keep citations. Tools never execute model-selected actions.",
    log_level="ERROR",
)
read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


@server.tool(annotations=read_only)
async def laya_status() -> dict:
    """Inspect cached local models and input limits without loading GPU weights."""
    return await anyio.to_thread.run_sync(runtime.status)


@server.tool(annotations=read_only)
async def laya_judge(state: str, questions: dict[str, Question], model: ModelName = "auto") -> dict:
    """Classify short supplied evidence, score an explicit rubric, or compare 2-8 frontend options. Questions use choice/score/noul. Include an uncertainty option in choices. This is advisory; no screenshots, external browsing, code edits or action execution. Oversized evidence/options are rejected."""
    request = JudgeRequest(state=state, questions=questions, model=model)
    return await anyio.to_thread.run_sync(runtime.judge, request)


@server.tool(annotations=read_only)
async def laya_rank_passages(goal: str, passages: list[Passage], model: ModelName = "auto") -> dict:
    """Rank 1-16 short supplied SEO/research passages against a goal, retaining every original ID and source. Returns 0-3 relevance scores, not summaries, fact verification or an instruction to discard low scores. Supply source text rather than URLs alone."""
    request = RankRequest(goal=goal, passages=passages, model=model)
    return await anyio.to_thread.run_sync(runtime.rank, request)


def serve():
    runtime.get_router()
    server.run(transport="stdio")


def main():
    parser = argparse.ArgumentParser(description="Local Laya tools for MCP-compatible AI clients")
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--stdio", action="store_true")
    operation.add_argument("--status", action="store_true")
    operation.add_argument("--request", type=Path)
    arguments = parser.parse_args()
    if arguments.stdio:
        serve()
        return
    try:
        if arguments.status:
            result = runtime.status()
        else:
            payload = json.loads(arguments.request.read_text(encoding="utf-8-sig"))
            if payload.get("operation") == "judge":
                result = runtime.judge(JudgeRequest.model_validate(payload["input"]))
            elif payload.get("operation") == "rank_passages":
                result = runtime.rank(RankRequest.model_validate(payload["input"]))
            else:
                raise ValueError("operation must be judge or rank_passages")
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
