from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.services import splat_trainer
from backend.services.splat_trainer import TrainerConfig, smoothstep


def _noop_progress(step: str, pct: float) -> None:
    pass


# Setting a sys.modules entry to None makes `import <name>` raise ImportError, so
# these tests simulate a torch-less environment deterministically — they must pass
# both in CI (no torch installed) and on the GPU dev machine (torch installed).
_NO_GPU_STACK = {"torch": None, "gsplat": None}


def test_module_imports_without_torch():
    # Clean-room subprocess: with the GPU stack blocked before anything else
    # imports, the module must still import — proving its top level never pulls
    # in torch/gsplat. (An in-process importlib.reload would re-create the
    # module's classes and break `except ReconstructionCancelled` identity in
    # reconstruction.py for every test that runs afterwards.)
    code = (
        "import sys; sys.modules['torch'] = None; sys.modules['gsplat'] = None; "
        "import backend.services.splat_trainer as m; "
        "assert all(hasattr(m, n) for n in ('train_splats', 'render_thumbnail', "
        "'render_flythrough', 'TrainerConfig')); "
        "assert issubclass(m.ReconstructionCancelled, RuntimeError)"
    )
    subprocess.run(
        [sys.executable, "-c", code], check=True, cwd=Path(__file__).parents[2]
    )


def test_train_splats_without_torch_raises_colmap_only_guidance(tmp_path: Path):
    config = TrainerConfig.from_preset({"iterations": 1000})
    with (
        patch.dict(sys.modules, _NO_GPU_STACK),
        pytest.raises(RuntimeError, match="COLMAP sparse cloud only"),
    ):
        splat_trainer.train_splats(
            tmp_path, tmp_path / "splat.ply", config, _noop_progress, threading.Event()
        )


def test_render_thumbnail_without_torch_returns_none(tmp_path: Path):
    with patch.dict(sys.modules, _NO_GPU_STACK):
        result = splat_trainer.render_thumbnail(tmp_path / "splat.ply", tmp_path / "thumb.jpg")
    assert result is None


def test_render_flythrough_without_torch_mentions_browser_recording(tmp_path: Path):
    keyframes = [
        {"position": [0.0, 0.0, 0.0], "target": [0.0, 0.0, 1.0], "duration_s": 1.0},
        {"position": [1.0, 0.0, 0.0], "target": [1.0, 0.0, 1.0], "duration_s": 1.0},
    ]
    with (
        patch.dict(sys.modules, _NO_GPU_STACK),
        pytest.raises(
            RuntimeError,
            match="Use browser recording or install optional reconstruction dependencies",
        ),
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


def test_training_pct_maps_into_rebalanced_window():
    # COLMAP now owns 0-40%, so training's window starts at 40.0 and ends at 99.0
    # (leaving headroom at the end for LOD/thumbnail generation).
    from backend.services.splat_trainer import _training_pct

    assert splat_trainer._PROGRESS_START == 40.0
    assert splat_trainer._PROGRESS_END == 99.0
    assert _training_pct(0, 1000) == pytest.approx(40.0)
    assert _training_pct(1000, 1000) == pytest.approx(99.0)
    midpoint = _training_pct(500, 1000)
    assert 40.0 < midpoint < 99.0


class _ArrayTensor:
    def __init__(self, value):
        self._value = np.asarray(value)

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self._value


def test_write_cancel_checkpoint_persists_ply_and_sidecar(tmp_path: Path):
    params = {
        "means": _ArrayTensor([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
        "sh0": _ArrayTensor([[[0.1, 0.2, 0.3]], [[0.4, 0.5, 0.6]]]),
        "shN": _ArrayTensor(np.zeros((2, 0, 3), dtype=np.float32)),
        "opacities": _ArrayTensor([0.0, 1.0]),
        "scales": _ArrayTensor(np.zeros((2, 3), dtype=np.float32)),
        "quats": _ArrayTensor([[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]]),
    }
    output_path = tmp_path / "splat.ply"

    result = splat_trainer._write_cancel_checkpoint(
        output_path,
        params,
        completed_iterations=125,
        metrics=[{"iter": 100, "psnr": 12.3, "ssim": 0.45}],
    )

    assert result == output_path
    assert output_path.exists()
    cloud = splat_trainer.ply_io.read_3dgs_ply(output_path)
    assert cloud.means.shape == (2, 3)
    sidecar = json.loads((tmp_path / "splat.ply.checkpoint.json").read_text())
    assert sidecar == {
        "reason": "cancelled_by_user",
        "completed_iterations": 125,
        "gaussian_count": 2,
        "training_metrics": [{"iter": 100, "psnr": 12.3, "ssim": 0.45}],
    }
