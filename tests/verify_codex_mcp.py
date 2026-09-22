import asyncio
from datetime import timedelta
import json
from pathlib import Path
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]


async def main():
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", str(PROJECT_DIRECTORY / "codex_bridge.py"), "--stdio"],
        cwd=str(PROJECT_DIRECTORY),
    )
    receipts = []
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream, read_timeout_seconds=timedelta(seconds=180)) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == {"laya_status", "laya_judge", "laya_rank_passages"}
            assert all(tool.annotations.readOnlyHint for tool in tools.tools)

            async def call(name, arguments):
                started = time.perf_counter()
                response = await session.call_tool(name, arguments)
                if response.isError:
                    raise AssertionError(response.content)
                result = response.structuredContent
                if result is None:
                    result = json.loads(next(block.text for block in response.content if block.type == "text"))
                receipts.append({"tool": name, "elapsed_ms": round((time.perf_counter() - started) * 1000, 1), "result": result})
                print(f"PASS {name}", flush=True)
                return result

            initial_status = await call("laya_status", {})
            assert not initial_status["loaded_models"]
            assert all(initial_status["cached_models"].values())

            seo_payload = json.loads((PROJECT_DIRECTORY / "examples/codex-seo.json").read_text(encoding="utf-8"))["input"]
            seo_result = await call("laya_rank_passages", seo_payload)
            assert {passage["id"] for passage in seo_result["ranked"]} == {"canonical-note", "unrelated-note"}
            assert seo_result["ranked"][0]["id"] == "canonical-note"
            assert seo_result["ranked"][0]["score"] > seo_result["ranked"][1]["score"]
            sources = {passage["id"]: passage["source"] for passage in seo_payload["passages"]}
            assert all(passage["source"] == sources[passage["id"]] for passage in seo_result["ranked"])

            frontend_payload = json.loads((PROJECT_DIRECTORY / "examples/codex-frontend.json").read_text(encoding="utf-8"))["input"]
            frontend_result = await call("laya_judge", frontend_payload)
            assert frontend_result["answers"]["next_step"]["choice"] == "add_label"
            assert "action" not in frontend_result["answers"]["next_step"]

            chinese_result = await call("laya_judge", {
                "state": "用户只按键盘 Tab 键操作，移动菜单打开后焦点无法进入菜单，关闭后焦点也没有返回菜单按钮。",
                "questions": {"area": {
                    "type": "choice",
                    "instructions": "Which area should be investigated for the observed problem?",
                    "criteria": {"keyboard": "Keyboard accessibility and focus management", "seo": "Search engine indexing", "color": "Brand color", "needs_review": "Insufficient evidence"},
                }},
            })
            assert chinese_result["model"] == "multilingual"
            assert chinese_result["answers"]["area"]["choice"] == "keyboard"

            oversized = await session.call_tool("laya_judge", {
                "state": "evidence " * 1800,
                "questions": {"check": {"type": "noul", "instructions": "Does the evidence mention a label?"}},
            })
            assert oversized.isError
            assert "INPUT_TOO_LONG" in " ".join(block.text for block in oversized.content if block.type == "text")
            print("PASS oversized input rejected through MCP", flush=True)
            final_status = await call("laya_status", {})
            assert len(final_status["loaded_models"]) <= 1
            receipt = {"server": initialized.serverInfo.model_dump(), "synthetic_smoke_cases_only": True, "receipts": receipts}
            output_path = PROJECT_DIRECTORY / ".cache/verification/codex-mcp.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Saved {output_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
