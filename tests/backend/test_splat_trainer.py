from __future__ import annotations

import importlib
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.services import splat_trainer
from backend.services.splat_trainer import ReconstructionCancelled, TrainerConfig, smoothstep


def _noop_progress(step: str, pct: float) -> None:
    pass


def test_module_imports_without_torch():
    module = importlib.import_module("backend.services.splat_trainer")
    # Importing the trainer must never pull in the optional GPU stack.
    assert "torch" not in sys.modules
    assert "gsplat" not in sys.modules
    for name in ("train_splats", "render_thumbnail", "render_flythrough", "TrainerConfig"):
        assert hasattr(module, name)
    assert issubclass(ReconstructionCancelled, RuntimeError)


def test_train_splats_without_torch_raises_colmap_only_guidance(tmp_path: Path):
    config = TrainerConfig.from_preset({"iterations": 1000})
    with pytest.raises(RuntimeError, match="COLMAP sparse cloud only"):
        splat_trainer.train_splats(
            tmp_path, tmp_path / "splat.ply", config, _noop_progress, threading.Event()
        )


def test_render_thumbnail_without_torch_returns_none(tmp_path: Path):
    result = splat_trainer.render_thumbnail(tmp_path / "splat.ply", tmp_path / "thumb.jpg")
    assert result is None


def test_render_flythrough_without_torch_mentions_browser_recording(tmp_path: Path):
    keyframes = [
        {"position": [0.0, 0.0, 0.0], "target": [0.0, 0.0, 1.0], "duration_s": 1.0},
        {"position": [1.0, 0.0, 0.0], "target": [1.0, 0.0, 1.0], "duration_s": 1.0},
    ]
    with pytest.raises(
        RuntimeError,
        match="Use browser recording or install optional reconstruction dependencies",
    ):
        splat_trainer.render_flythrough(
            tmp_path / "splat.ply", tmp_path / "out.mp4", keyframes,
            fps=30, width=1280, height=720,
        )


def test_render_flythrough_without_ffmpeg_raises_install_guidance(tmp_path: Path):
    keyframes = [
        {"position": [0.0, 0.0, 0.0], "target": [0.0, 0.0, 1.0], "duration_s": 1.0},
        {"position": [1.0, 0.0, 0.0], "target": [1.0, 0.0, 1.0], "duration_s": 1.0},
    ]
    with (
        patch.dict(sys.modules, {"torch": MagicMock(), "gsplat": MagicMock()}),
        patch("backend.services.splat_trainer.shutil.which", return_value=None),
        pytest.raises(RuntimeError, match="ffmpeg.*browser recording"),
    ):
        splat_trainer.render_flythrough(
            tmp_path / "splat.ply", tmp_path / "out.mp4", keyframes,
            fps=30, width=1280, height=720,
        )


def test_trainer_config_from_preset_quick_and_full_defaults():
    quick = TrainerConfig.from_preset({"iterations": 1000, "max_frames": 500})
    assert quick.iterations == 1000
    assert quick.sh_degree == 1
    assert quick.downscale_factor == 4
    assert quick.max_gaussians == 350_000
    assert (quick.refine_start_iter, quick.refine_stop_iter, quick.refine_every) == (
        300, 800, 100,
    )
    assert quick.reset_every > quick.iterations  # opacity reset disabled on quick
    assert (quick.eval_every, quick.eval_views) == (250, 4)
    assert quick.sh_warmup_every == 500
    assert quick.ssim_lambda == 0.2
    assert quick.init_opacity == 0.1

    full = TrainerConfig.from_preset({"iterations": 30000, "max_frames": None})
    assert full.iterations == 30000
    assert full.sh_degree == 2
    assert full.downscale_factor == 2
    assert full.max_gaussians == 1_000_000
    assert (full.refine_start_iter, full.refine_stop_iter, full.refine_every) == (
        500, 15_000, 100,
    )
    assert full.reset_every == 3000
    assert (full.eval_every, full.eval_views) == (1000, 4)
    assert full.sh_warmup_every == 1000

    # Per-preset overrides in config.yaml win over profile defaults.
    overridden = TrainerConfig.from_preset({"iterations": 1000, "max_gaussians": 123})
    assert overridden.max_gaussians == 123


def test_smoothstep_keyframe_interpolation_endpoints():
    assert smoothstep(0.0) == 0.0
    assert smoothstep(1.0) == 1.0
    assert smoothstep(0.5) == 0.5
    # Must mirror frontend/src/features/splat/smoothstep.ts exactly.
    for t in (0.1, 0.25, 0.6, 0.9):
        assert smoothstep(t) == pytest.approx(t * t * (3 - 2 * t), abs=1e-12)
    assert smoothstep(0.1) < 0.1
    assert smoothstep(0.9) > 0.9
