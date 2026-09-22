"""Shared torch device/dtype resolution for hf_mps training and comparison."""

import torch


def resolve_device() -> str:
    """Pick the best available torch device: CUDA, then MPS, then CPU."""
    if torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    return device


def resolve_dtype(device: str) -> torch.dtype:
    """Pick a compute dtype appropriate for the resolved device."""
    if device == "cuda":
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    elif device == "mps":
        dtype = torch.bfloat16
    else:
        dtype = torch.float32
    return dtype