# Hardware and inference backends

The installer distinguishes a physical GPU from a working PyTorch backend. A detected AMD or NVIDIA adapter alone does not prove that its driver, installed wheels and model operators work together. Installation normally completes one real MCP inference before registering clients.

| Backend | Selection | Validation in this project |
| --- | --- | --- |
| CPU | `--device cpu` | Real Windows CPU inference; portable fallback |
| NVIDIA CUDA | `--device cuda` | Real Windows RTX 3060 inference |
| AMD ROCm / HIP | `--device rocm` | Backend detection, registration, precision selection and fallback regression tests; no AMD hardware validation yet |
| Apple MPS | `--device mps`, or `auto` when available | Selection regression tests; no Apple hardware validation yet |
| DirectML / ONNX | Not selectable | Research candidates, not implemented or advertised as working backends |

CPU and GPU latency depend on the checkpoint, evidence length, number of questions, hardware and threading. Model loading must be measured separately from repeated calls. There is no universal 20–60 ms CPU guarantee or GPU-equivalent performance claim.

## Automatic installation

```sh
python install.py --client codex --client claude-code
```

Existing importable PyTorch installations are reused without replacing their backend. Runtime selection prefers available CUDA/HIP, then MPS, then CPU. ROCm is identified with `torch.version.hip`; its tensors still use PyTorch's `cuda` device API. For compatibility, `--device cuda` accepts either a working CUDA or HIP build, while `--device rocm` specifically requires HIP.

In a fresh Windows/Linux environment without a detected NVIDIA adapter, the installer chooses official CPU wheels. This includes AMD machines without a preconfigured ROCm build. A fresh NVIDIA environment uses platform-default PyTorch wheels and verifies the result; this is not a guarantee that those wheels support every NVIDIA card or driver. macOS uses platform-default PyTorch wheels. A failed hardware inventory is reported and uses the conservative CPU path on Windows/Linux.

In `auto` mode, recognized accelerator allocation/kernel failures may retry on CPU. The result reports the actual backend and failure reason. A failed CPU retry remains an error. An explicit GPU request fails if the model falls back to CPU; it cannot produce a successful GPU installation receipt. `--skip-inference` explicitly skips the model check and reports `inference_verified: false`.

The installer does not install drivers, change paging-file settings, enable WSL or automatically replace Torch with DirectML.

## CPU and NVIDIA

Force CPU even if a GPU is present:

```sh
python install.py --client codex --device cpu
```

To explicitly replace this checkout's Torch build with official CPU wheels:

```sh
python install.py --client codex --device cpu --torch-index-url https://download.pytorch.org/whl/cpu
```

For NVIDIA, first use the [official PyTorch selector](https://pytorch.org/get-started/locally/) to choose wheels compatible with the driver and GPU. An explicit `--torch-index-url` reinstalls Torch in the selected virtual environment; use a separate `--venv` if keeping another environment intact is required. Then require GPU verification:

```sh
python install.py --client codex --device cuda
```

Windows PowerShell supports the same selection:

```powershell
.\install.ps1 -Client codex,claude-code -Device cpu
```

## AMD ROCm

1. Check AMD's exact GPU, operating-system, driver, Python and PyTorch compatibility matrix. Linux, WSL and native Windows have different supported combinations; a series name such as RX 6000/7000 is insufficient.
2. Create the chosen virtual environment and install the officially supported ROCm/PyTorch wheels into it using AMD's instructions. Use the same environment for this installer. A compatible official `download.pytorch.org/whl/rocm...` index may instead be passed with `--torch-index-url`; this project does not prescribe one ROCm release for every machine.
3. Run `python install.py --client codex --device rocm`. Add `--venv PATH` for a nondefault environment. The installer verifies HIP availability and a real model invocation before registering the client.

If an online installation requests ROCm without an existing HIP build or explicit wheel index, it stops before creating the environment or installing packages. Select `--device cpu` to continue on unsupported hardware. Offline provisioning accepts matching local wheels via `--wheelhouse`; the installed backend still must pass verification.

Use the root installer from this checkout: it installs both the integration and this checkout's Laya runtime, including HIP-aware precision and fallback reporting. Installing the Agent Kit package alone against the unchanged upstream Laya 0.3.5 does not include those runtime fixes.

## Inspect the actual backend

On Windows, replace `.venv/bin/python` with `.\.venv\Scripts\python.exe`:

```sh
.venv/bin/python -m laya_agent_kit hardware --device auto
.venv/bin/python -m laya_agent_kit doctor --data-dir .cache --device auto --models english --inference
```

`hardware` reports detected runtime support without loading model weights or writing client settings. `doctor --inference` adds actual inference verification. `runtime` contains the requested device, selected backend, CUDA/HIP build versions, GPU name, actual device/backend after inference, and `fallback_reason`. A HIP device can correctly report `actual_device: cuda` together with `actual_backend: rocm`.

`laya_judge` and every `laya_rank_passages` entry include the same execution information. `laya_status` reports the last successful inference and does not load weights just to check status. Before any runtime initialization its actual device/backend are unknown, not CPU. Reconnect existing MCP sessions after installing updated code; existing server processes do not hot-reload it.

The local part of `start_chatgpt.py` accepts the same `--device` choices. This does not establish end-to-end web ChatGPT connectivity.

## Reproduce checks

These tests require the integration's test dependencies but no GPU or weights:

```sh
python tests/test_backends.py
python tests/test_provision.py
python tests/test_runtime_lifecycle.py
```

`python tests/test_device_runtime.py` uses CPU PyTorch tensors and simulated accelerator errors, without weights or GPU access. Real-device smoke checks use the installed package and cached models:

```sh
.venv/bin/python tests/verify_backends.py --devices cpu cuda
```

Use `--devices rocm` only on an appropriately configured AMD machine. The receipt records the actual backend and first/repeated-call timings for a small synthetic request; it is not a general performance or task-accuracy benchmark.

Official references: [PyTorch HIP semantics](https://docs.pytorch.org/docs/2.14/notes/hip.html), [AMD Radeon/Ryzen ROCm](https://rocm.docs.amd.com/projects/radeon/en/latest/), [PyTorch DirectML](https://learn.microsoft.com/en-us/windows/ai/directml/pytorch-windows), [ONNX Runtime DirectML limitations](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html).
