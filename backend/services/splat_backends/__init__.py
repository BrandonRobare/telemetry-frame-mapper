from __future__ import annotations

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


def get_training_backend(override: str | None = None) -> SplatTrainerBackend:
    """Return the requested trainer backend; only CUDA gsplat exists in Wave 3."""
    if override not in (None, "cuda", "cuda_gsplat"):
        raise ValueError(f"Unsupported splat trainer backend: {override!r}")
    return CUDA_GSPLAT_BACKEND


def get_renderer_backend(override: str | None = None) -> SplatRendererBackend:
    """Return the current server-side rasterizer implementation."""
    if override not in (None, "cuda", "cuda_gsplat"):
        raise ValueError(f"Unsupported splat renderer backend: {override!r}")
    return CUDA_GSPLAT_RENDERER_BACKEND


__all__ = [
    "ProgressCallback",
    "ReconstructionCancelled",
    "SplatRendererBackend",
    "SplatTrainerBackend",
    "TrainerConfig",
    "TrainingResult",
    "get_renderer_backend",
    "get_training_backend",
]
