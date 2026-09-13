from __future__ import annotations

import importlib.util
import json
import platform
import struct
import sys
import threading
import time
from pathlib import Path
from typing import cast

import pytest
from PIL import Image

from backend.services import ply_io
from backend.services.splat_backends import ReconstructionCancelled, TrainerConfig

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin"
    or platform.machine().lower() not in {"arm64", "aarch64"}
    or importlib.util.find_spec("msplat") is None,
    reason="requires msplat on Apple Silicon",
)

def _write_colmap_fixture(root: Path) -> Path:
    images_dir = root / "images"
    sparse = root / "sparse" / "0"
    images_dir.mkdir(parents=True)
    sparse.mkdir(parents=True)

    names = ["frame-01.png", "frame-02.png", "frame-03.png"]
    for index, name in enumerate(names):
        image = Image.new("RGB", (32, 32), (60 + index * 50, 90, 150 - index * 30))
        image.save(images_dir / name)

    camera = struct.pack("<IIQQdddd", 1, 1, 32, 32, 26.0, 26.0, 16.0, 16.0)
    (sparse / "cameras.bin").write_bytes(struct.pack("<Q", 1) + camera)

    image_bytes = bytearray(struct.pack("<Q", len(names)))
    translations = [(0.12, 0.0, 0.0), (0.0, 0.0, 0.0), (-0.12, 0.0, 0.0)]
    for image_id, (name, translation) in enumerate(
        zip(names, translations, strict=True), start=1
    ):
        image_bytes.extend(
            struct.pack("<I7dI", image_id, 1.0, 0.0, 0.0, 0.0, *translation, 1)
        )
        image_bytes.extend(name.encode("utf-8") + b"\0")
        image_bytes.extend(struct.pack("<Q", 0))
    (sparse / "images.bin").write_bytes(image_bytes)

    points = bytearray(struct.pack("<Q", 18))
    for point_id in range(1, 19):
        x = ((point_id - 1) % 6 - 2.5) * 0.08
        y = ((point_id - 1) // 6 - 1.0) * 0.08
        z = 1.5 + (point_id % 3) * 0.05
        points.extend(
            struct.pack(
                "<QdddBBBdQ",
                point_id,
                x,
                y,
                z,
                80 + point_id * 5,
                100,
                180 - point_id * 4,
                0.1,
                0,
            )
        )
    (sparse / "points3D.bin").write_bytes(points)
    return root

def _config(*, iterations: int, max_gaussians: int = 2_000) -> TrainerConfig:
    return TrainerConfig(
        iterations=iterations,
        sh_degree=0,
        downscale_factor=1,
        max_gaussians=max_gaussians,
        refine_start_iter=500,
        refine_stop_iter=4_000,
    )


def test_real_msplat_trains_and_exports_viewer_compatible_ply(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    workspace = _write_colmap_fixture(tmp_path / "colmap")
    output = tmp_path / "splat.ply"
    progress: list[tuple[str, float]] = []

    try:
        result = metal_msplat.METAL_MSPLAT_BACKEND.train(
            workspace,
            output,
            _config(iterations=3),
            lambda message, pct: progress.append((message, pct)),
            threading.Event(),
        )
    except RuntimeError as exc:
        # #849: msplat 1.1.4 exports non-finite Gaussians on real arm64.
        # #851's gate rejects that output; this is the fail-safe branch and the
        # artifact must be retained for diagnostics. XPASS strict when msplat
        # is fixed and training completes finitely.
        assert "invalid splat PLY" in str(exc)
        assert output.exists()
        pytest.xfail(f"#849 msplat exports invalid Gaussians; gate rejected: {exc}")
    else:
        cloud = ply_io.read_3dgs_ply(output)
        assert output.stat().st_size > 0
        assert cloud.means.shape == (result["gaussian_count"], 3)
        assert result["gaussian_count"] == 18
        assert progress[-1] == ("exporting splat PLY", 99.0)


def test_real_msplat_cancels_mid_training_with_recoverable_outputs(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    workspace = _write_colmap_fixture(tmp_path / "cancel-colmap")
    output = tmp_path / "cancelled.ply"
    cancel = threading.Event()
    timer: threading.Timer | None = None

    def progress(message: str, _pct: float) -> None:
        nonlocal timer
        if message.startswith("training 1/") and timer is None:
            timer = threading.Timer(0.02, cancel.set)
            timer.start()

    started = time.monotonic()
    with pytest.raises(ReconstructionCancelled, match="Cancelled by user"):
        metal_msplat.METAL_MSPLAT_BACKEND.train(
            workspace,
            output,
            _config(iterations=20_000),
            progress,
            cancel,
        )
    if timer is not None:
        timer.join(timeout=1)

    checkpoint = output.with_suffix(".ply.checkpoint.msplat")
    sidecar = output.with_suffix(".ply.checkpoint.json")
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    assert time.monotonic() - started < 10
    assert timer is not None
    assert metadata["completed_iterations"] > 0
    assert metadata["native_checkpoint"] == checkpoint.name
    assert checkpoint.exists() and output.exists()
    assert ply_io.read_3dgs_ply(output).means.shape[0] == metadata["gaussian_count"]


def test_real_msplat_freezes_before_cap_and_finishes_training(tmp_path: Path) -> None:
    from backend.services.splat_backends import metal_msplat

    workspace = _write_colmap_fixture(tmp_path / "cap-colmap")
    output = tmp_path / "capped.ply"
    progress: list[str] = []

    try:
        result = metal_msplat.METAL_MSPLAT_BACKEND.train(
            workspace,
            output,
            _config(iterations=1_300, max_gaussians=50),
            lambda message, _pct: progress.append(message),
            threading.Event(),
        )
    except RuntimeError as exc:
        # #849: invalid frozen-phase export on real arm64; #851 rejects it.
        assert "invalid splat PLY" in str(exc)
        assert output.exists()
        pytest.xfail(f"#849 msplat exports invalid Gaussians; gate rejected: {exc}")
    else:
        gaussian_count = cast(int, result["gaussian_count"])
        assert gaussian_count <= 50
        assert any("densification frozen" in message for message in progress)
        assert progress[-1] == "exporting splat PLY"
        assert ply_io.read_3dgs_ply(output).means.shape[0] == gaussian_count
