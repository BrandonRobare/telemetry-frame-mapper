"""#852: one invalid Gaussian row must fail the Metal release gate."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from backend.services.ply_io import GaussianCloud, write_3dgs_ply


def _evidence(root: Path, rows: int, nan_row: int | None = None) -> None:
    rng = np.random.default_rng(852)
    means = rng.random((rows, 3)).astype(np.float32)
    if nan_row is not None:
        means[nan_row][0] = np.nan
    cloud = GaussianCloud(
        means=means,
        sh0=rng.random((rows, 3)).astype(np.float32),
        shN=np.zeros((rows, 0, 3), dtype=np.float32),
        opacities=rng.random((rows,)).astype(np.float32),
        scales=np.zeros((rows, 3), dtype=np.float32),
        quats=np.tile(np.array([1.0, 0, 0, 0], dtype=np.float32), (rows, 1)),
    )
    write_3dgs_ply(root / "splat.ply", cloud)
    (root / "gate.json").write_text(json.dumps({"gaussian_count": rows}))


def test_one_invalid_row_fails_the_gate(tmp_path: Path) -> None:
    from scripts.metal_release_gate import main

    _evidence(tmp_path, rows=4, nan_row=2)

    assert main(["validate", "--evidence", str(tmp_path)]) == 1
    validation = json.loads((tmp_path / "gate.json").read_text())["validation"]
    assert validation["ok"] is False
    assert "means=1" in validation["detail"]
    assert (tmp_path / "splat.ply").exists(), "invalid artifact is retained"


def test_finite_export_passes_the_gate(tmp_path: Path) -> None:
    from scripts.metal_release_gate import main

    _evidence(tmp_path, rows=4)

    assert main(["validate", "--evidence", str(tmp_path)]) == 0
    assert json.loads((tmp_path / "gate.json").read_text())["validation"] == {
        "ok": True,
        "rows": 4,
    }
    sums = (tmp_path / "SHA256SUMS").read_text().split()
    assert sums[1::2] == ["gate.json", "splat.ply"]
