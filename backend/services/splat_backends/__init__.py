from __future__ import annotations

from backend.services import accelerator
from backend.services.splat_backends.base import (
    ProgressCallback,
    ReconstructionCancelled,
    SplatRendererBackend,
    SplatTrainerBackend,
    TrainerConfig,
    TrainingResult,
)
from backend.services.splat_backends.cuda_gsplat import (
    CUDA_GSPLAT_BACKEND,
    CUDA_GSPLAT_RENDERER_BACKEND,
)
from backend.services.splat_backends.metal_msplat import METAL_MSPLAT_BACKEND


def get_training_backend(override: str | None = None) -> SplatTrainerBackend:
    """Select CUDA gsplat or native msplat from the detected accelerator."""
    if override in ("metal", "mps", "msplat", "metal_msplat"):
        return METAL_MSPLAT_BACKEND
    if override in ("cuda", "cuda_gsplat"):
        return CUDA_GSPLAT_BACKEND
    if override is not None:
        raise ValueError(f"Unsupported splat trainer backend: {override!r}")
    if accelerator.detect().kind == "metal":
        return METAL_MSPLAT_BACKEND
    return CUDA_GSPLAT_BACKEND


def get_renderer_backend(override: str | None = None) -> SplatRendererBackend:
    """Return the current server-side rasterizer implementation."""
    if override not in (None, "cuda", "cuda_gsplat"):
        raise ValueError(f"Unsupported splat renderer backend: {override!r}")
    return CUDA_GSPLAT_RENDERER_BACKEND


__all__ = [
    "METAL_MSPLAT_BACKEND",
    "ProgressCallback",
    "ReconstructionCancelled",
    "SplatRendererBackend",
    "SplatTrainerBackend",
    "TrainerConfig",
    "TrainingResult",
    "get_renderer_backend",
    "get_training_backend",
]
