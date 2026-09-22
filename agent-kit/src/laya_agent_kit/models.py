import os
from pathlib import Path
import sys


MODEL_REPOSITORY = "convaiinnovations/laya"
MODEL_REVISION = "1c5edc17a7acd8701df6fc341c0d179f1c62c982"
MODEL_NAMES = ("english", "multilingual", "typed-decisions")
MODEL_FILES = (
    "model.safetensors",
    "rl_agent_config.json",
    "encoder/config.json",
    "tokenizer/tokenizer.json",
    "tokenizer/tokenizer_config.json",
)


def data_directory(value=None):
    if value or os.environ.get("LAYA_HOME"):
        return Path(value or os.environ["LAYA_HOME"]).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "LayaAgentKit"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "laya-agent-kit"


def model_directories(directory):
    snapshot = Path(directory) / "huggingface/hub/models--convaiinnovations--laya/snapshots" / MODEL_REVISION
    return {name: snapshot if name == "english" else snapshot / name for name in MODEL_NAMES}


def missing_model_files(directory):
    return {
        name: [filename for filename in MODEL_FILES if not (path / filename).is_file() or (path / filename).stat().st_size == 0]
        for name, path in model_directories(directory).items()
    }


def prepare_models(directory, names=MODEL_NAMES, offline=False):
    unknown = set(names) - set(MODEL_NAMES)
    if unknown:
        raise ValueError(f"Unknown models: {sorted(unknown)}")
    missing = missing_model_files(directory)
    needed = [name for name in names if missing[name]]
    if needed and offline:
        raise FileNotFoundError(f"Offline model cache is incomplete: {', '.join(needed)}. Run download with network access first.")
    if needed:
        from huggingface_hub import snapshot_download

        patterns = [
            ("" if name == "english" else name + "/") + filename
            for name in needed for filename in MODEL_FILES
        ]
        snapshot_download(
            MODEL_REPOSITORY,
            revision=MODEL_REVISION,
            cache_dir=str(Path(directory) / "huggingface/hub"),
            allow_patterns=patterns,
            max_workers=4,
        )
    missing = missing_model_files(directory)
    incomplete = {name: missing[name] for name in names if missing[name]}
    if incomplete:
        raise RuntimeError(f"Model download is incomplete: {incomplete}")
    return {name: str(model_directories(directory)[name]) for name in names}
