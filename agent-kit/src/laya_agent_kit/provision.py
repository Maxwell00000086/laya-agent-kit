import json
from pathlib import Path
import platform
import shutil
import subprocess


CPU_INDEX = "https://download.pytorch.org/whl/cpu"


def hardware_inventory():
    system = platform.system()
    adapters = []
    errors = []
    try:
        if system == "Windows":
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "$ErrorActionPreference = 'Stop'; @(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) | ConvertTo-Json -Compress"],
                capture_output=True, text=True, timeout=15, check=True,
            )
            values = json.loads(result.stdout)
            adapters = values if isinstance(values, list) else [values] if values else []
        elif system == "Linux":
            for path in Path("/sys/class/drm").glob("card*/device/vendor"):
                vendor = path.read_text().strip().lower()
                adapters.append({"0x10de": "NVIDIA", "0x1002": "AMD", "0x8086": "Intel"}.get(vendor, vendor))
        elif system == "Darwin":
            adapters = ["Apple" if platform.machine().lower() == "arm64" else "Mac"]
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        errors.append(str(error))
    if system == "Linux" and not any("nvidia" in name.lower() for name in adapters) and shutil.which("nvidia-smi"):
        try:
            result = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True, timeout=10, check=True)
            adapters.extend("NVIDIA " + name for name in result.stdout.splitlines() if name.strip())
        except (OSError, subprocess.SubprocessError) as error:
            errors.append(str(error))
    vendors = sorted({
        vendor for name in adapters for vendor, labels in {
            "nvidia": ("nvidia",), "amd": ("amd", "radeon"), "intel": ("intel",), "apple": ("apple",),
        }.items() if any(label in name.lower() for label in labels)
    })
    return {"system": system, "wsl": system == "Linux" and "microsoft" in platform.release().lower(),
            "adapters": adapters, "vendors": vendors, "detection_errors": errors}


def torch_install_plan(device, index_url, offline, hardware, existing):
    if index_url and not index_url.startswith("https://download.pytorch.org/whl/"):
        raise ValueError("Use an official https://download.pytorch.org/whl/ index.")
    if offline and index_url:
        raise ValueError("--torch-index-url cannot be combined with --offline; use --wheelhouse.")
    if index_url:
        return {"index_url": index_url, "replace_torch": True, "reason": "Explicit PyTorch index selected; the requested backend must pass runtime verification."}
    if offline:
        return {"index_url": None, "replace_torch": False, "reason": "Offline: reuse installed dependencies or matching local wheels; verify the backend before registration."}
    if device == "rocm" and not (existing and existing.get("hip_version")):
        raise ValueError(
            "ROCm was requested but this environment has no ROCm PyTorch build. "
            "Follow https://rocm.docs.amd.com/projects/radeon/en/latest/ for your exact GPU/OS, "
            "install its supported wheels into the selected virtual environment, or supply the matching official "
            "--torch-index-url. This installer does not guess a ROCm release from an AMD GPU name."
        )
    if device == "mps" and hardware["system"] != "Darwin":
        raise ValueError("MPS requires supported Apple hardware and macOS; select --device cpu or auto.")
    if existing:
        return {"index_url": None, "replace_torch": False, "reason": "Reuse existing PyTorch without replacing its CPU/CUDA/ROCm build; verify actual inference separately."}
    if device == "cpu" or (device == "auto" and "nvidia" not in hardware["vendors"] and hardware["system"] != "Darwin"):
        return {"index_url": CPU_INDEX if hardware["system"] in ("Windows", "Linux") else None,
                "replace_torch": False, "reason": "Use CPU wheels as the portable default; AMD hardware alone does not establish ROCm compatibility."}
    return {"index_url": None, "replace_torch": False, "reason": "Use platform-default PyTorch wheels, then verify device availability and actual inference."}
