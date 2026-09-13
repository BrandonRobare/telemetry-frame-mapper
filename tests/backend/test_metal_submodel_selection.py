"""Selected-COLMAP-submodel view for the Metal trainer (#855).

msplat 1.1.4's COLMAP loader resolves ``sparse/0`` unconditionally; the
application selects the submodel with the most registered images everywhere
else. These tests prove the Metal adapter mirrors that shared policy by
loading through a temporary symlinked view of the selected model without ever
mutating the COLMAP workspace.
"""

from __future__ import annotations

import shutil
import struct
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from backend.services.ply_io import GaussianCloud, write_3dgs_ply
from backend.services.splat_backends.base import TrainerConfig


def _write_model(sparse: Path, number: int, count: int) -> None:
    """Create one numbered submodel dir with cameras.bin + images.bin headers."""
    model_dir = sparse / str(number)
    model_dir.mkdir(parents=True, exist_ok=False)
    (model_dir / "cameras.bin").write_bytes(struct.pack("<Q", 0))
    (model_dir / "images.bin").write_bytes(struct.pack("<Q", count))
    (model_dir / "points3D.bin").write_bytes(struct.pack("<Q", 0))


def _valid_ply(path: Path, rows: int) -> None:
    """Persist a real, finite INRIA 3DGS PLY for the mock trainer's export."""
    rng = np.random.default_rng(42)
    cloud = GaussianCloud(
        means=rng.random((rows, 3)).astype(np.float32),
        sh0=rng.random((rows, 3)).astype(np.float32),
        shN=np.zeros((rows, 0, 3), dtype=np.float32),
        opacities=rng.random((rows,)).astype(np.float32),
        scales=np.zeros((rows, 3), dtype=np.float32),
        quats=np.tile(np.array([1.0, 0, 0, 0], dtype=np.float32), (rows, 1)),
    )
    write_3dgs_ply(path, cloud)


def _runtime(tmp_path: Path, *, rows: int = 3):
    dataset = SimpleNamespace(num_train=0)
    record: dict[str, object] = {"loaded_root": None, "cameras_resolve": None}
    runtime = SimpleNamespace(
        load_dataset=MagicMock(return_value=dataset),
        TrainingConfig=MagicMock(return_value="native-config"),
        sync=MagicMock(),
    )

    def load(path: str, **kwargs):
        record["loaded_root"] = Path(path)
        cameras = Path(path) / "cameras.bin"
        record["cameras_resolve"] = (
            cameras.resolve() if cameras.exists() else None
        )
        return dataset

    runtime.load_dataset.side_effect = load
    trainer = MagicMock()
    trainer.iteration = 0
    trainer.splat_count = rows
    state = {"steps": 0}

    def step():
        state["steps"] += 1
        trainer.iteration = state["steps"]
        trainer.splat_count = rows
        return SimpleNamespace(iteration=state["steps"], splat_count=rows, ms_per_step=1.0)

    trainer.step.side_effect = step
    trainer.export_ply.side_effect = lambda path: _valid_ply(Path(path), rows)
    trainer.save_checkpoint.side_effect = lambda path: Path(path).write_bytes(b"checkpoint")
    runtime.GaussianTrainer = MagicMock(return_value=trainer)
    return runtime, record


def _config() -> TrainerConfig:
    config = TrainerConfig(
        iterations=3,
        sh_degree=0,
        downscale_factor=2,
        max_gaussians=100,
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
    config.refine_start_iter = 0
    config.refine_every = 1
    return config


def test_selected_model_view_points_cameras_at_selected_submodel(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    colmap = tmp_path / "colmap"
    _write_model(colmap / "sparse", 0, 1)
    _write_model(colmap / "sparse", 1, 2)
    _write_model(colmap / "sparse", 5, 4)
    (colmap / "images").mkdir()

    view = metal_msplat._selected_model_view(colmap)
    try:
        assert view is not None
        cameras = (view / "cameras.bin").resolve()
        assert cameras == (colmap / "sparse" / "5" / "cameras.bin").resolve()
        images_bin = (view / "images.bin").resolve()
        assert images_bin == (colmap / "sparse" / "5" / "images.bin").resolve()
        assert (view / "images").resolve() == (colmap / "images").resolve()
        points = (view / "points3D.bin").resolve()
        assert points == (colmap / "sparse" / "5" / "points3D.bin").resolve()
    finally:
        if view is not None:
            shutil.rmtree(view)


def test_selected_model_view_none_without_real_models(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    assert metal_msplat._selected_model_view(tmp_path / "colmap") is None


def test_train_loads_selected_submodel_through_view_and_cleans_up(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    colmap = tmp_path / "colmap"
    _write_model(colmap / "sparse", 0, 1)
    _write_model(colmap / "sparse", 5, 4)
    (colmap / "images").mkdir()
    runtime, record = _runtime(tmp_path)
    output = tmp_path / "out" / "splat.ply"

    result = metal_msplat._train(runtime, colmap, output, _config(), MagicMock(), threading.Event())

    loaded = record["loaded_root"]
    assert loaded is not None
    assert loaded.name.startswith("metal-colmap-view-")
    assert record["cameras_resolve"] == (colmap / "sparse" / "5" / "cameras.bin").resolve()
    # The temporary view was removed, and the workspace's sparse/0 was never
    # created, replaced, or shadowed.
    assert not loaded.exists()
    assert (colmap / "sparse" / "0").is_dir()
    assert not (colmap / "sparse" / "0").is_symlink()
    assert result["gaussian_count"] == 3


def test_train_without_fragmentation_loads_workspace_root_directly(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    colmap = tmp_path / "colmap"  # no sparse dir at all — msplat fallback path
    runtime, record = _runtime(tmp_path)

    metal_msplat._train(
        runtime, colmap, tmp_path / "out" / "splat.ply", _config(), MagicMock(), threading.Event()
    )

    assert record["loaded_root"] == colmap


def test_train_with_selected_zero_still_uses_view_and_keeps_workspace_clean(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    colmap = tmp_path / "colmap"
    _write_model(colmap / "sparse", 0, 4)
    _write_model(colmap / "sparse", 1, 1)
    (colmap / "images").mkdir()
    runtime, record = _runtime(tmp_path)

    metal_msplat._train(runtime, colmap, tmp_path / "out" / "splat.ply", _config(), MagicMock(), threading.Event())

    loaded = record["loaded_root"]
    assert loaded is not None and loaded != colmap
    assert record["cameras_resolve"] == (colmap / "sparse" / "0" / "cameras.bin").resolve()
    assert not loaded.exists()