import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Run Laya with this project's local model cache.")
    parser.add_argument("--text", default="发票被重复扣款，请帮我退款。")
    parser.add_argument("--model", choices=["auto", "english", "multilingual", "typed-decisions"], default="auto")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--all-models", action="store_true")
    arguments = parser.parse_args()

    project_directory = Path(__file__).resolve().parent
    os.environ["HF_HOME"] = str(project_directory / ".cache" / "huggingface")
    os.environ["TORCH_HOME"] = str(project_directory / ".cache" / "torch")
    os.environ["USE_TF"] = "0"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    if arguments.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"

    import laya
    import torch

    questions = {
        "department": {
            "type": "choice",
            "instructions": "Which department should handle this request?",
            "criteria": {
                "billing": "invoices, payments, refunds",
                "technical": "bugs, outages, system errors",
                "sales": "pricing, new contracts",
                "other": "everything else",
            },
        },
        "urgency": {
            "type": "score",
            "instructions": "How urgent is this request?",
            "criteria": ["not urgent", "soon", "critical deadline or blocking issue"],
        },
        "refund_requested": {
            "type": "noul",
            "instructions": "Does the customer explicitly request a refund?",
        },
    }
    device = None if arguments.device == "auto" else arguments.device
    router = laya.Router(device=device, max_loaded=1)
    examples = [(arguments.model, arguments.text)]
    if arguments.all_models:
        examples = [
            ("english", "I was charged twice for invoice 4411. Please refund the duplicate today."),
            ("multilingual", "发票4411被重复扣款，请今天退款。"),
            ("typed-decisions", "I was charged twice for invoice 4411. Please refund the duplicate today."),
        ]
    try:
        for model_name, message in examples:
            selected_model = None if model_name == "auto" else model_name
            print(f"Loading and running: {model_name}", flush=True)
            result = router.predict({"message": message}, questions, model=selected_model)
            agent = router.load(result["routing"]["model"])
            output = {
                "laya_version": laya.__version__,
                "torch_version": torch.__version__,
                "device": str(agent.device),
                "input": message,
                "result": result,
            }
            print(json.dumps(output, ensure_ascii=False, indent=2), flush=True)
    finally:
        router.unload()


if __name__ == "__main__":
    main()
