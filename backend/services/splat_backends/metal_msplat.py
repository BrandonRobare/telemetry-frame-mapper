"""Apple-Silicon Gaussian training through the optional ``msplat`` runtime."""

from __future__ import annotations

import json
import math
import platform
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.services.splat_backends.base import (
    _GPU_LOCK,
    ProgressCallback,
    ReconstructionCancelled,
    TrainerConfig,
    TrainingResult,
)

_PROGRESS_START = 40.0
_PROGRESS_END = 99.0
_PROGRESS_MIN_INTERVAL_S = 2.0
_DENSIFY_GRAD_THRESHOLD = 0.0002
_REQUIRED_API = ("GaussianTrainer", "TrainingConfig", "load_dataset", "sync")


def _load_msplat() -> Any:
    import msplat  # type: ignore[import-not-found]

    return msplat


def _platform_supported() -> bool:
    machine = platform.machine().lower()
    version = platform.mac_ver()[0]
    try:
        major = int(version.split(".", 1)[0])
    except (ValueError, IndexError):
        return False
    return platform.system() == "Darwin" and machine in {"arm64", "aarch64"} and major >= 14


@lru_cache(maxsize=1)
def is_available() -> bool:
    """Return whether the supported platform and complete native API are usable."""
    if not _platform_supported():
        return False
    try:
        runtime = _load_msplat()
    except (ImportError, OSError, RuntimeError):
        return False
    return all(callable(getattr(runtime, name, None)) for name in _REQUIRED_API)


class _ProgressThrottle:
    def __init__(self, callback: ProgressCallback) -> None:
        self._callback = callback
        self._last = -math.inf

    def __call__(self, step: str, pct: float, *, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last >= _PROGRESS_MIN_INTERVAL_S:
            self._last = now
            self._callback(step, pct)


def _training_pct(step: int, iterations: int) -> float:
    fraction = min(1.0, max(0.0, step / max(1, iterations)))
    return _PROGRESS_START + (_PROGRESS_END - _PROGRESS_START) * fraction


def _checkpoint_path(output_path: Path) -> Path:
    return output_path.with_suffix(output_path.suffix + ".checkpoint.msplat")


def _checkpoint_sidecar_path(output_path: Path) -> Path:
    return output_path.with_suffix(output_path.suffix + ".checkpoint.json")


def _save_cancellation_state(runtime: Any, trainer: Any, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = _checkpoint_path(output_path)
    runtime.sync()
    trainer.save_checkpoint(str(checkpoint))
    trainer.export_ply(str(output_path))
    runtime.sync()
    _checkpoint_sidecar_path(output_path).write_text(
        json.dumps(
            {
                "reason": "cancelled_by_user",
                "completed_iterations": int(trainer.iteration),
                "gaussian_count": int(trainer.splat_count),
                "native_checkpoint": checkpoint.name,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _train(
    runtime: Any,
    colmap_dir: Path,
    output_path: Path,
    config: TrainerConfig,
    progress_cb: ProgressCallback,
    cancel: threading.Event,
) -> TrainingResult:
    progress = _ProgressThrottle(progress_cb)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    progress("loading COLMAP model", _PROGRESS_START, force=True)
    dataset = runtime.load_dataset(
        str(colmap_dir), downscale_factor=float(config.downscale_factor), eval_mode=False
    )
    native_config = runtime.TrainingConfig(
        iterations=config.iterations,
        sh_degree=config.sh_degree,
        sh_degree_interval=config.sh_warmup_every,
        ssim_weight=config.ssim_lambda,
        num_downscales=0,
        refine_every=config.refine_every,
        warmup_length=config.refine_start_iter,
        reset_alpha_every=max(1, config.reset_every // max(1, config.refine_every)),
        densify_grad_thresh=_DENSIFY_GRAD_THRESHOLD,
        stop_screen_size_at=config.refine_stop_iter,
        downscale_factor=float(config.downscale_factor),
        output=str(output_path.parent),
        save_every=-1,
    )
    trainer = runtime.GaussianTrainer(dataset, native_config)

    while int(trainer.iteration) < config.iterations:
        if cancel.is_set():
            progress(
                "saving cancellation checkpoint",
                _training_pct(int(trainer.iteration), config.iterations),
                force=True,
            )
            _save_cancellation_state(runtime, trainer, output_path)
            raise ReconstructionCancelled("Cancelled by user")
        if int(trainer.splat_count) >= config.max_gaussians:
            progress(
                f"gaussian cap reached ({config.max_gaussians:,}) — training stopped",
                _training_pct(int(trainer.iteration), config.iterations),
                force=True,
            )
            break

        stats = trainer.step()
        # Metal command buffers are asynchronous. Synchronize before timing-derived
        # progress or completion is observable outside this backend.
        runtime.sync()
        progress(
            f"training {int(stats.iteration)}/{config.iterations}",
            _training_pct(int(stats.iteration), config.iterations),
            force=int(stats.iteration) == 1,
        )
        if int(stats.splat_count) >= config.max_gaussians:
            progress(
                f"gaussian cap reached ({config.max_gaussians:,}) — training stopped",
                _training_pct(int(stats.iteration), config.iterations),
                force=True,
            )
            break

    if cancel.is_set():
        progress(
            "saving cancellation checkpoint",
            _training_pct(int(trainer.iteration), config.iterations),
            force=True,
        )
        _save_cancellation_state(runtime, trainer, output_path)
        raise ReconstructionCancelled("Cancelled by user")

    progress("exporting splat PLY", _PROGRESS_END, force=True)
    runtime.sync()
    trainer.export_ply(str(output_path))
    runtime.sync()
    return {
        "gaussian_count": int(trainer.splat_count),
        "psnr": None,
        "ssim": None,
        "training_metrics": None,
    }


class MetalMsplatBackend:
    """Native Metal trainer implementing the backend-neutral training contract."""

    def is_available(self) -> bool:
        return is_available()

    def train(
        self,
        colmap_dir: Path,
        output_path: Path,
        config: TrainerConfig,
        progress_cb: ProgressCallback,
        cancel: threading.Event,
    ) -> TrainingResult:
        try:
            runtime = _load_msplat()
        except (ImportError, OSError, RuntimeError) as exc:
            raise RuntimeError(
                "The optional msplat Metal backend is unavailable. The reconstruction will "
                "complete with COLMAP sparse cloud only."
            ) from exc
        with _GPU_LOCK:
            return _train(runtime, colmap_dir, output_path, config, progress_cb, cancel)


METAL_MSPLAT_BACKEND = MetalMsplatBackend()
