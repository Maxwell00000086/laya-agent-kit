import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]


async def verify(device, directory):
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-I", "-X", "utf8", "-m", "laya_agent_kit.server", "--stdio"],
        env={"LAYA_HOME": str(directory), "LAYA_DEVICE": device},
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()

            async def call(name, arguments):
                result = await session.call_tool(name, arguments)
                if result.isError:
                    raise RuntimeError(" ".join(block.text for block in result.content if block.type == "text"))
                return result.structuredContent or json.loads(next(block.text for block in result.content if block.type == "text"))

            initial = await call("laya_status", {})
            assert initial["inference_verified"] is False
            assert initial["runtime"].get("actual_backend") is None
            request = {
                "model": "english",
                "state": "Synthetic test: a customer was charged twice for the same order and requests a refund.",
                "questions": {
                    "category": {"type": "choice", "instructions": "What is the main issue?", "criteria": {"billing": "Payment or refund", "delivery": "Parcel delivery", "uncertain": "Not enough information"}},
                    "refund": {"type": "noul", "instructions": "Does the customer request a refund?"},
                    "relevance": {"type": "score", "instructions": "How relevant is the ticket to billing support?", "criteria": ["unrelated", "partly relevant", "directly relevant"]},
                },
            }
            runs = [await call("laya_judge", request) for attempt in range(2)]
            for result in runs:
                assert result["engine"] == "local_laya"
                assert set(result["answers"]) == set(request["questions"])
                assert result["runtime"]["actual_device"] == result["device"]
                expected = result["runtime"]["selected_backend"] if device in ("auto", "cuda") else device
                if device == "auto" and result["runtime"]["actual_backend"] != expected:
                    assert result["runtime"]["actual_backend"] == "cpu" and result["runtime"]["fallback_reason"]
                else:
                    assert result["runtime"]["actual_backend"] == expected
            final = await call("laya_status", {})
            assert final["inference_verified"] is True
            assert final["runtime"] == runs[-1]["runtime"]
            return {"requested_device": device, "runs": runs, "final_status": final}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--devices", nargs="+", choices=("auto", "cpu", "cuda", "rocm", "mps"), default=["cpu", "auto"])
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".cache")
    arguments = parser.parse_args()
    directory = arguments.data_dir.resolve()
    results = []
    for device in arguments.devices:
        result = await asyncio.wait_for(verify(device, directory), timeout=240)
        results.append(result)
        print(f"PASS {device}: actual={result['runs'][-1]['runtime']['actual_backend']}; elapsed_ms={[run['elapsed_ms'] for run in result['runs']]}", flush=True)
    receipt = {"date": datetime.now(timezone.utc).isoformat(), "synthetic_smoke_only": True, "devices": results}
    destination = directory / "verification/backends.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"Saved {destination}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
