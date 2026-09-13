from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from backend.services.ply_io import GaussianCloud, write_3dgs_ply
from backend.services.splat_backends.base import TrainerConfig


def _valid_ply(path: Path, rows: int) -> None:
    """Write a real, finite INRIA 3DGS PLY so validated harness exports parse."""
    rng = np.random.default_rng(7)
    cloud = GaussianCloud(
        means=rng.random((rows, 3)).astype(np.float32),
        sh0=rng.random((rows, 3)).astype(np.float32),
        shN=np.zeros((rows, 0, 3), dtype=np.float32),
        opacities=rng.random((rows,)).astype(np.float32),
        scales=np.zeros((rows, 3), dtype=np.float32),
        quats=np.tile(np.array([1.0, 0, 0, 0], dtype=np.float32), (rows, 1)),
    )
    write_3dgs_ply(path, cloud)


def _config(*, iterations: int = 3, max_gaussians: int = 100) -> TrainerConfig:
    return TrainerConfig(
        iterations=iterations,
        sh_degree=2,
        downscale_factor=2,
        max_gaussians=max_gaussians,
        refine_start_iter=500,
        refine_stop_iter=2_000,
        refine_every=100,
        reset_every=3_000,
        eval_every=1_000,
        eval_views=4,
        ssim_lambda=0.2,
        init_opacity=0.1,
        sh_warmup_every=1_000,
    )


def _runtime(tmp_path: Path, counts: list[int], *, start_iteration: int = 0):
    dataset = SimpleNamespace(num_train=0)
    runtime = SimpleNamespace(
        load_dataset=MagicMock(return_value=dataset),
        TrainingConfig=MagicMock(return_value="native-config"),
        sync=MagicMock(),
    )
    trainer = MagicMock()
    trainer.iteration = start_iteration
    trainer.splat_count = counts[0]
    state = {"index": 0}

    def step():
        state["index"] += 1
        trainer.iteration = start_iteration + state["index"]
        trainer.splat_count = counts[min(state["index"], len(counts) - 1)]
        return SimpleNamespace(
            iteration=trainer.iteration,
            splat_count=trainer.splat_count,
            ms_per_step=1.0,
        )

    trainer.step.side_effect = step
    trainer.export_ply.side_effect = lambda path: _valid_ply(Path(path), int(trainer.splat_count))
    trainer.save_checkpoint.side_effect = lambda path: Path(path).write_bytes(b"checkpoint")
    runtime.GaussianTrainer = MagicMock(return_value=trainer)
    return runtime, trainer


def test_metal_probe_is_cached_and_fails_closed(monkeypatch) -> None:
    from backend.services.splat_backends import metal_msplat

    runtime = SimpleNamespace(
        GaussianTrainer=MagicMock(),
        TrainingConfig=MagicMock(),
        load_dataset=MagicMock(),
        sync=MagicMock(),
    )
    load = MagicMock(return_value=runtime)
    monkeypatch.setattr(metal_msplat, "_load_msplat", load)
    monkeypatch.setattr(metal_msplat, "_platform_supported", lambda: True)
    metal_msplat.is_available.cache_clear()

    assert metal_msplat.is_available() is True
    assert metal_msplat.is_available() is True
    load.assert_called_once_with()

    monkeypatch.setattr(metal_msplat, "_load_msplat", MagicMock(side_effect=ImportError))
    metal_msplat.is_available.cache_clear()
    assert metal_msplat.is_available() is False
    metal_msplat.is_available.cache_clear()


def test_metal_training_maps_config_steps_syncs_and_exports(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    runtime, trainer = _runtime(tmp_path, [8, 9, 10, 11])
    progress = MagicMock()
    output = tmp_path / "out" / "splat.ply"

    result = metal_msplat._train(
        runtime,
        tmp_path / "colmap",
        output,
        _config(),
        progress,
        threading.Event(),
    )

    runtime.load_dataset.assert_called_once_with(
        str(tmp_path / "colmap"), downscale_factor=2.0, eval_mode=False
    )
    kwargs = runtime.TrainingConfig.call_args.kwargs
    assert kwargs == {
        "iterations": 3,
        "sh_degree": 2,
        "sh_degree_interval": 1_000,
        "ssim_weight": 0.2,
        "num_downscales": 0,
        "refine_every": 100,
        "warmup_length": 500,
        "reset_alpha_every": 30,
        "densify_grad_thresh": 0.0002,
        "stop_screen_size_at": 2_000,
        "downscale_factor": 2.0,
        "keep_crs": True,
        "output": str(output.parent),
        "save_every": -1,
    }
    assert trainer.step.call_count == 3
    assert runtime.sync.call_count >= 4
    trainer.export_ply.assert_called_once_with(str(output))
    assert output.exists()
    assert result == {
        "gaussian_count": 11,
        "psnr": None,
        "ssim": None,
        "training_metrics": None,
    }
    assert progress.call_args_list[-1].args == ("exporting splat PLY", 99.0)


def test_metal_training_freezes_densification_and_completes_at_gaussian_cap(
    tmp_path: Path,
) -> None:
    from backend.services.splat_backends import metal_msplat

    runtime, adaptive = _runtime(tmp_path, [20, 40])
    _unused, frozen = _runtime(tmp_path, [40] * 8, start_iteration=1)
    runtime.GaussianTrainer.side_effect = [adaptive, frozen]
    progress = MagicMock()
    config = _config(iterations=8, max_gaussians=100)
    config.refine_start_iter = 0
    config.refine_every = 1
    config.reset_every = 10
    output = tmp_path / "splat.ply"
    result = metal_msplat._train(
        runtime,
        tmp_path / "colmap",
        output,
        config,
        progress,
        threading.Event(),
    )

    assert adaptive.step.call_count == 1
    assert frozen.step.call_count == 7
    assert frozen.load_checkpoint.called
    assert runtime.TrainingConfig.call_count == 2
    frozen_kwargs = runtime.TrainingConfig.call_args_list[1].kwargs
    assert frozen_kwargs["warmup_length"] == config.iterations + 1
    assert frozen_kwargs["densify_grad_thresh"] == float("inf")
    assert frozen_kwargs["keep_crs"] is True
    assert not output.with_suffix(".ply.cap-freeze.msplat").exists()
    assert result["gaussian_count"] == 40
    assert any("densification frozen" in call.args[0] for call in progress.call_args_list)


def test_metal_training_rejects_initial_cloud_above_cap(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    runtime, trainer = _runtime(tmp_path, [101])
    trainer = runtime.GaussianTrainer.return_value
    with pytest.raises(RuntimeError, match="initialized 101 Gaussians.*cap of 100"):
        metal_msplat._train(
            runtime,
            tmp_path / "colmap",
            tmp_path / "splat.ply",
            _config(max_gaussians=100),
            MagicMock(),
            threading.Event(),
        )
    trainer.step.assert_not_called()


class _CancelAfterOneStep:
    def __init__(self) -> None:
        self.calls = 0

    def is_set(self) -> bool:
        self.calls += 1
        return self.calls > 1


def test_metal_cancellation_exports_viewable_ply_and_native_checkpoint(tmp_path: Path) -> None:
    from backend.services.splat_backends import ReconstructionCancelled, metal_msplat

    runtime, trainer = _runtime(tmp_path, [8, 9, 10])
    output = tmp_path / "splat.ply"

    with pytest.raises(ReconstructionCancelled, match="Cancelled by user"):
        metal_msplat._train(
            runtime,
            tmp_path / "colmap",
            output,
            _config(),
            MagicMock(),
            _CancelAfterOneStep(),  # type: ignore[arg-type]
        )

    checkpoint = output.with_suffix(".ply.checkpoint.msplat")
    sidecar = output.with_suffix(".ply.checkpoint.json")
    trainer.save_checkpoint.assert_called_once_with(str(checkpoint))
    trainer.export_ply.assert_called_once_with(str(output))
    assert output.exists() and checkpoint.exists() and sidecar.exists()
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    assert metadata == {
        "reason": "cancelled_by_user",
        "completed_iterations": 1,
        "gaussian_count": 9,
        "native_checkpoint": checkpoint.name,
    }
    assert runtime.sync.called


def test_metal_backend_uses_shared_gpu_lock_and_full_contract(monkeypatch, tmp_path: Path) -> None:
    from backend.services.splat_backends import cuda_gsplat, metal_msplat

    runtime = object()
    expected = {"gaussian_count": 7, "psnr": None, "ssim": None, "training_metrics": None}
    train = MagicMock(return_value=expected)
    monkeypatch.setattr(metal_msplat, "_load_msplat", lambda: runtime)
    monkeypatch.setattr(metal_msplat, "_train", train)
    config = _config()
    progress = MagicMock()
    cancel = threading.Event()

    result = metal_msplat.METAL_MSPLAT_BACKEND.train(
        tmp_path / "colmap", tmp_path / "splat.ply", config, progress, cancel
    )

    assert metal_msplat._GPU_LOCK is cuda_gsplat._GPU_LOCK
    assert result == expected
    train.assert_called_once_with(
        runtime, tmp_path / "colmap", tmp_path / "splat.ply", config, progress, cancel
    )


def test_metal_backend_missing_dependency_degrades_to_colmap_only(
    monkeypatch, tmp_path: Path
) -> None:
    from backend.services.splat_backends import metal_msplat

    monkeypatch.setattr(metal_msplat, "_load_msplat", MagicMock(side_effect=ImportError))
    with pytest.raises(RuntimeError, match="msplat.*COLMAP sparse cloud only"):
        metal_msplat.METAL_MSPLAT_BACKEND.train(
            tmp_path / "colmap",
            tmp_path / "splat.ply",
            _config(),
            MagicMock(),
            threading.Event(),
        )


# ---------------------------------------------------------------------------
# Exported-PLY validity gate (#851/#849)
# ---------------------------------------------------------------------------


def _cloud(**overrides) -> GaussianCloud:
    rng = np.random.default_rng(11)
    rows = overrides.pop("rows", 5)
    cloud = GaussianCloud(
        means=rng.random((rows, 3)).astype(np.float32),
        sh0=rng.random((rows, 3)).astype(np.float32),
        shN=np.zeros((rows, 0, 3), dtype=np.float32),
        opacities=rng.random((rows,)).astype(np.float32),
        scales=np.zeros((rows, 3), dtype=np.float32),
        quats=np.tile(np.array([1.0, 0, 0, 0], dtype=np.float32), (rows, 1)),
    )
    for name, value in overrides.items():
        setattr(cloud, name, value)
    return cloud


def _corrupt_ply(path: Path, **overrides) -> None:
    write_3dgs_ply(path, _cloud(**overrides))


def test_validate_exported_ply_accepts_finite_cloud(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    path = tmp_path / "splat.ply"
    _valid_ply(path, rows=5)
    assert metal_msplat.validate_exported_ply(path, expected_count=5) == 5
    assert metal_msplat.validate_exported_ply(path, expected_count=None) == 5


def test_validate_exported_ply_rejects_non_finite_means(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    path = tmp_path / "splat.ply"
    rng = np.random.default_rng(2)
    means = rng.random((5, 3)).astype(np.float32)
    means[3][1] = np.nan
    _corrupt_ply(path, means=means)

    with pytest.raises(RuntimeError, match="means=1"):
        metal_msplat.validate_exported_ply(path, expected_count=5)


def test_validate_exported_ply_rejects_infinite_scales(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    path = tmp_path / "splat.ply"
    scales = np.zeros((5, 3), dtype=np.float32)
    scales[0][0] = np.inf
    _corrupt_ply(path, scales=scales)

    with pytest.raises(RuntimeError, match="scales=1"):
        metal_msplat.validate_exported_ply(path, expected_count=5)


def test_validate_exported_ply_rejects_overflowing_exponentiated_scales(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    path = tmp_path / "splat.ply"
    scales = np.zeros((5, 3), dtype=np.float32)
    scales[2][2] = 100.0  # finite value, but exp(100) overflows float32/float64 output
    _corrupt_ply(path, scales=scales)

    with pytest.raises(RuntimeError, match="exponentiated_scales=1"):
        metal_msplat.validate_exported_ply(path, expected_count=5)


def test_validate_exported_ply_rejects_zero_norm_quaternions(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    path = tmp_path / "splat.ply"
    quats = np.tile(np.array([1.0, 0, 0, 0], dtype=np.float32), (5, 1))
    quats[4] = [0.0, 0.0, 0.0, 0.0]
    _corrupt_ply(path, quats=quats)

    with pytest.raises(RuntimeError, match="zero_norm_quaternions=1"):
        metal_msplat.validate_exported_ply(path, expected_count=5)


def test_validate_exported_ply_rejects_count_mismatch(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    path = tmp_path / "splat.ply"
    _valid_ply(path, rows=5)
    with pytest.raises(RuntimeError, match="count=5 expected=6"):
        metal_msplat.validate_exported_ply(path, expected_count=6)


def test_train_fails_closed_when_export_contains_non_finite_rows(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    runtime, trainer = _runtime(tmp_path, [4])
    rng = np.random.default_rng(3)
    means = rng.random((4, 3)).astype(np.float32)
    means[1][0] = np.inf

    def bad_export(path: str) -> None:
        _corrupt_ply(Path(path), rows=4, means=means)

    trainer.export_ply.side_effect = bad_export
    output = tmp_path / "out" / "splat.ply"

    with pytest.raises(RuntimeError, match="means=1"):
        metal_msplat._train(
            runtime, tmp_path / "colmap", output, _config(), MagicMock(), threading.Event()
        )
    # The invalid artifact is retained for diagnostics, never silently dropped.
    assert output.exists()


def test_train_fails_closed_on_serialized_count_mismatch(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    runtime, trainer = _runtime(tmp_path, [4])
    trainer.export_ply.side_effect = lambda path: _valid_ply(Path(path), rows=3)
    output = tmp_path / "out" / "splat.ply"

    with pytest.raises(RuntimeError, match="count=3 expected=4"):
        metal_msplat._train(
            runtime, tmp_path / "colmap", output, _config(), MagicMock(), threading.Event()
        )
