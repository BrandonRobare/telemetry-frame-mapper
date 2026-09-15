from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Protocol

ProgressCallback = Callable[[str, float], None]
TrainingResult = dict[str, object]

# Every in-process accelerator trainer and renderer shares one device-work lock.
_GPU_LOCK = threading.Lock()


class ReconstructionCancelled(RuntimeError):
    """Raised when a reconstruction backend saves state and stops on request."""


@dataclass
class TrainerConfig:
    """Backend-neutral hyperparameters for one Gaussian training run."""

    iterations: int
    sh_degree: int
    downscale_factor: int
    max_gaussians: int
    refine_start_iter: int
    refine_stop_iter: int
    refine_every: int = 100
    reset_every: int = 3000
    eval_every: int = 1000
    eval_views: int = 4
    ssim_lambda: float = 0.2
    init_opacity: float = 0.1
    sh_warmup_every: int = 1000
    # Opt-in benchmark controls; product presets keep their historical behavior.
    benchmark_heldout_split: bool = False
    benchmark_test_every: int = 8
    background_color: tuple[float, float, float] | None = None

    @classmethod
    def from_preset(cls, preset_cfg: dict) -> TrainerConfig:
        iterations = int(preset_cfg.get("iterations", 1000))
        if iterations < 5000:
            config = cls(
                iterations=iterations,
                sh_degree=1,
                downscale_factor=4,
                max_gaussians=350_000,
                refine_start_iter=300,
                refine_stop_iter=800,
                reset_every=iterations + 1,
                eval_every=250,
                sh_warmup_every=500,
            )
        else:
            config = cls(
                iterations=iterations,
                sh_degree=2,
                downscale_factor=2,
                max_gaussians=1_000_000,
                refine_start_iter=500,
                refine_stop_iter=15_000,
                reset_every=3000,
                eval_every=1000,
                sh_warmup_every=1000,
            )
        for field in fields(cls):
            if field.name != "iterations" and field.name in preset_cfg:
                current = getattr(config, field.name)
                value = preset_cfg[field.name]
                if field.name == "background_color":
                    if value is None:
                        setattr(config, field.name, None)
                    else:
                        color = tuple(float(component) for component in value)
                        if len(color) != 3:
                            raise ValueError(
                                "background_color must contain exactly three components"
                            )
                        setattr(config, field.name, color)
                else:
                    setattr(config, field.name, type(current)(value))
        return config


class SplatTrainerBackend(Protocol):
    """Train a finished COLMAP model into an application-compatible PLY."""

    def is_available(self) -> bool: ...

    def train(
        self,
        colmap_dir: Path,
        output_path: Path,
        config: TrainerConfig,
        progress_cb: ProgressCallback,
        cancel: threading.Event,
    ) -> TrainingResult: ...


class SplatRendererBackend(Protocol):
    """Backend-neutral boundary for optional server-side splat rasterization."""

    def is_available(self) -> bool: ...

    def rasterize(
        self,
        torch: Any,
        cloud: Any,
        viewmat: Any,
        width: int,
        height: int,
        device: str,
        *,
        sh_degree: int | None = None,
        intrinsics: Any | None = None,
        render_mode: str | None = None,
        packed: bool = True,
    ) -> Any: ...
