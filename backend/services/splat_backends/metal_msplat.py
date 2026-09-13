"""Apple-Silicon Gaussian training through the optional ``msplat`` runtime."""

from __future__ import annotations

import gc
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


def _native_config(
    runtime: Any,
    config: TrainerConfig,
    output_path: Path,
    *,
    freeze_densification: bool = False,
) -> Any:
    return runtime.TrainingConfig(
        iterations=config.iterations,
        sh_degree=config.sh_degree,
        sh_degree_interval=config.sh_warmup_every,
        ssim_weight=config.ssim_lambda,
        num_downscales=0,
        refine_every=config.refine_every,
        warmup_length=config.iterations + 1
        if freeze_densification
        else config.refine_start_iter,
        reset_alpha_every=max(1, config.reset_every // max(1, config.refine_every)),
        densify_grad_thresh=math.inf if freeze_densification else _DENSIFY_GRAD_THRESHOLD,
        stop_screen_size_at=config.refine_stop_iter,
        downscale_factor=float(config.downscale_factor),
        # msplat recenters/rescales COLMAP input while loading. ask it to
        # restore the original positions/log-scales on export so the produced
        # cloud stays in the COLMAP coordinate frame the application solved
        # its geo-transform against (#854).
        keep_crs=True,
        output=str(output_path.parent),
        save_every=-1,
    )


def _next_step_can_densify(trainer: Any, dataset: Any, config: TrainerConfig) -> bool:
    step = int(trainer.iteration) + 1
    reset_interval = max(
        config.refine_every,
        (config.reset_every // max(1, config.refine_every)) * config.refine_every,
    )
    return (
        step % config.refine_every == 0
        and step > config.refine_start_iter
        and step < config.iterations // 2
        and step % reset_interval > int(dataset.num_train) + config.refine_every
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
    native_config = _native_config(runtime, config, output_path)
    trainer = runtime.GaussianTrainer(dataset, native_config)
    if int(trainer.splat_count) > config.max_gaussians:
        raise RuntimeError(
            f"COLMAP initialized {int(trainer.splat_count):,} Gaussians, exceeding the "
            f"configured max_gaussians cap of {config.max_gaussians:,}"
        )
    densification_frozen = False

    while int(trainer.iteration) < config.iterations:
        if cancel.is_set():
            progress(
                "saving cancellation checkpoint",
                _training_pct(int(trainer.iteration), config.iterations),
                force=True,
            )
            _save_cancellation_state(runtime, trainer, output_path)
            raise ReconstructionCancelled("Cancelled by user")
        # msplat 1.1.4 has no runtime densification toggle and its native step can
        # allocate up to 3x the active count. Freeze via a native checkpoint before
        # a risky refinement, then keep optimizing all remaining iterations.
        if not densification_frozen and _next_step_can_densify(trainer, dataset, config):
            next_step = int(trainer.iteration) + 1
            count = int(trainer.splat_count)
            freeze_for_budget = 3 * count > config.max_gaussians
            freeze_for_schedule = next_step >= config.refine_stop_iter
            if freeze_for_budget or freeze_for_schedule:
                progress(
                    "densification frozen; continuing optimization within Gaussian budget",
                    _training_pct(int(trainer.iteration), config.iterations),
                    force=True,
                )
                checkpoint = output_path.with_suffix(".ply.cap-freeze.msplat")
                completed_iteration = int(trainer.iteration)
                trainer.save_checkpoint(str(checkpoint))
                runtime.sync()
                trainer = None
                gc.collect()
                try:
                    frozen_config = _native_config(
                        runtime, config, output_path, freeze_densification=True
                    )
                    trainer = runtime.GaussianTrainer(dataset, frozen_config)
                    trainer.load_checkpoint(str(checkpoint))
                    loaded_iteration = int(trainer.iteration)
                    if loaded_iteration != completed_iteration:
                        raise RuntimeError(
                            "msplat restored an unexpected iteration while freezing densification"
                        )
                    runtime.sync()
                finally:
                    checkpoint.unlink(missing_ok=True)
                densification_frozen = True

        stats = trainer.step()
        # Metal command buffers are asynchronous. Synchronize before timing-derived
        # progress or completion is observable outside this backend.
        runtime.sync()
        progress(
            f"training {int(stats.iteration)}/{config.iterations}",
            _training_pct(int(stats.iteration), config.iterations),
            force=int(stats.iteration) == 1,
        )
        if int(stats.splat_count) > config.max_gaussians:
            raise RuntimeError(
                "msplat exceeded max_gaussians despite the conservative pre-densification cap"
            )

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
