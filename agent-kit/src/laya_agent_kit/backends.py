DEVICE_CHOICES = ("auto", "cpu", "cuda", "rocm", "mps")


def torch_capabilities():
    import torch

    errors = []
    cuda_available = False
    mps_available = False
    gpu = None
    try:
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            gpu = torch.cuda.get_device_name(0)
    except Exception as error:
        cuda_available = False
        errors.append(f"CUDA/HIP detection failed: {error}")
    try:
        mps_available = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    except Exception as error:
        errors.append(f"MPS detection failed: {error}")
    hip_version = getattr(torch.version, "hip", None)
    cuda_version = getattr(torch.version, "cuda", None)
    accelerator = ("rocm" if hip_version else "cuda") if cuda_available else "mps" if mps_available else None
    return {
        "torch_version": str(torch.__version__),
        "cuda_version": cuda_version,
        "hip_version": hip_version,
        "cuda_available": cuda_available,
        "mps_available": mps_available,
        "accelerator": accelerator,
        "gpu": gpu if cuda_available else "Apple MPS" if mps_available else None,
        "detection_errors": errors,
    }


def select_device(requested="auto", capabilities=None):
    if requested not in DEVICE_CHOICES:
        raise ValueError(f"Unsupported device {requested!r}. Choose {', '.join(DEVICE_CHOICES)}. DirectML and ONNX are not implemented.")
    info = torch_capabilities() if capabilities is None else capabilities
    accelerator = info["accelerator"]
    if requested == "auto":
        backend = accelerator or "cpu"
    elif requested == "cpu":
        backend = "cpu"
    elif requested == "cuda" and accelerator in ("cuda", "rocm"):
        backend = accelerator
    elif requested == accelerator:
        backend = requested
    else:
        raise RuntimeError(
            f"BACKEND_UNAVAILABLE: requested {requested}, available accelerator: {accelerator or 'none'}. "
            "Install the matching PyTorch build and supported driver/hardware, or select --device cpu. "
            "ROCm requires AMD's exact hardware/OS compatibility matrix; CUDA wheels cannot enable an AMD GPU."
        )
    reason = None
    if requested == "auto" and backend == "cpu":
        reason = "No usable CUDA, ROCm or MPS accelerator was detected by this PyTorch installation. Using CPU."
        if info["detection_errors"]:
            reason += " " + "; ".join(info["detection_errors"])
    return {
        **info,
        "requested_device": requested,
        "selected_backend": backend,
        "selected_device": "cuda" if backend == "rocm" else backend,
        "fallback_reason": reason,
    }


def execution_report(selection, actual_device, fallback_reason=None):
    device = str(actual_device)
    device_type = device.split(":", 1)[0]
    backend = "rocm" if device_type == "cuda" and selection.get("hip_version") else device_type
    reason = fallback_reason or selection.get("fallback_reason")
    if backend != selection["selected_backend"] and not reason:
        reason = f"The model selected {backend} after {selection['selected_backend']} was requested; no further reason was reported."
    report = {**selection, "actual_device": device, "actual_backend": backend, "fallback_reason": reason}
    if selection["requested_device"] != "auto" and backend != selection["selected_backend"]:
        raise RuntimeError(
            f"BACKEND_FALLBACK: requested {selection['requested_device']} but the model is running on {backend}. "
            f"{reason} Select --device auto to permit CPU fallback or --device cpu explicitly."
        )
    return report
