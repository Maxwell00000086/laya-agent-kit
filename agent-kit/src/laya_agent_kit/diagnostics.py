from contextlib import redirect_stdout
from datetime import timedelta
from importlib.metadata import version
import json
import sys

from .clients import server_spec
from .models import missing_model_files


def runtime_info():
    with redirect_stdout(sys.stderr):
        import torch

        cuda = torch.cuda.is_available()
        return {
            "python": sys.version.split()[0],
            "packages": {name: version(name) for name in ("laya", "laya-agent-kit", "mcp", "torch", "transformers")},
            "cuda_available": cuda,
            "gpu": torch.cuda.get_device_name(0) if cuda else None,
        }


async def probe(directory, device="auto", inference_model=None, registration=None):
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    spec = registration if registration is not None else server_spec("generic", directory, device)
    parameters = StdioServerParameters(**spec)
    with anyio.fail_after(240):
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=180)) as session:
                initialized = await session.initialize()
                listing = await session.list_tools()
                expected = {"laya_status", "laya_judge", "laya_rank_passages"}
                if {tool.name for tool in listing.tools} != expected:
                    raise RuntimeError("MCP tool discovery returned unexpected tools")
                if not all(tool.annotations and tool.annotations.readOnlyHint for tool in listing.tools):
                    raise RuntimeError("MCP tools lack their read-only annotations")

                async def call(name, arguments):
                    response = await session.call_tool(name, arguments)
                    if response.isError:
                        message = " ".join(block.text for block in response.content if block.type == "text")
                        raise RuntimeError(message)
                    return response.structuredContent or json.loads(next(block.text for block in response.content if block.type == "text"))

                result = {
                    "server": initialized.serverInfo.model_dump(),
                    "tools": sorted(expected),
                    "status": await call("laya_status", {}),
                }
                if inference_model:
                    result["inference"] = await call("laya_judge", {
                        "state": "The email input has a visible label and can be reached using the keyboard.",
                        "questions": {"label": {"type": "noul", "instructions": "Does the evidence state that a visible label is present?"}},
                        "model": inference_model,
                    })
                return result


def diagnose(directory, device="auto", models=(), inference_model=None):
    import anyio

    info = runtime_info()
    missing = missing_model_files(directory)
    info["missing_model_files"] = missing
    if device == "cuda" and not info["cuda_available"]:
        raise RuntimeError("CUDA was requested but is unavailable. Install a compatible PyTorch CUDA build/driver or select --device cpu.")
    incomplete = [name for name in models if missing[name]]
    if incomplete:
        raise RuntimeError(f"Missing models: {', '.join(incomplete)}. Run download first.")
    info["mcp"] = anyio.run(probe, directory, device, inference_model)
    info["ok"] = True
    return info


def diagnose_registration(spec, directory, device="auto"):
    import anyio

    return anyio.run(probe, directory, device, None, spec)
