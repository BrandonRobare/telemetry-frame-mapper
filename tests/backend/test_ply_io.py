from __future__ import annotations

import json
from unittest.mock import MagicMock

import numpy as np
import pytest

from backend.services.ply_io import (
    GaussianCloud,
    ply_property_names,
    prune_by_opacity,
    read_3dgs_ply,
    write_3dgs_ply,
)

_SH_C0 = 0.28209479177387814


def _make_cloud(n: int, num_rest_coeffs: int, seed: int = 0) -> GaussianCloud:
    rng = np.random.default_rng(seed)
    return GaussianCloud(
        means=rng.normal(size=(n, 3)).astype(np.float32),
        sh0=rng.normal(size=(n, 3)).astype(np.float32),
        shN=rng.normal(size=(n, num_rest_coeffs, 3)).astype(np.float32),
        opacities=rng.normal(size=(n,)).astype(np.float32),
        scales=rng.normal(size=(n, 3)).astype(np.float32),
        quats=rng.normal(size=(n, 4)).astype(np.float32),
    )


@pytest.mark.parametrize("sh_degree", [0, 2])
def test_write_read_roundtrip_preserves_all_attributes(tmp_path, sh_degree):
    num_rest_coeffs = (sh_degree + 1) ** 2 - 1
    cloud = _make_cloud(7, num_rest_coeffs, seed=sh_degree)

    path = write_3dgs_ply(tmp_path / "splat.ply", cloud)
    assert path == tmp_path / "splat.ply"
    loaded = read_3dgs_ply(path)

    assert loaded.shN.shape == (7, num_rest_coeffs, 3)
    np.testing.assert_array_equal(loaded.means, cloud.means)
    np.testing.assert_array_equal(loaded.sh0, cloud.sh0)
    np.testing.assert_array_equal(loaded.shN, cloud.shN)
    np.testing.assert_array_equal(loaded.opacities, cloud.opacities)
    np.testing.assert_array_equal(loaded.scales, cloud.scales)
    np.testing.assert_array_equal(loaded.quats, cloud.quats)
    for attr in ("means", "sh0", "shN", "opacities", "scales", "quats"):
        assert getattr(loaded, attr).dtype == np.float32


def test_header_property_order_matches_inria_layout(tmp_path):
    expected = (
        ["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2"]
        + [f"f_rest_{i}" for i in range(24)]
        + ["opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]
    )
    assert ply_property_names(2) == expected

    # A written degree-2 file (K = 8 rest coefficients) must list the same
    # properties, in the same order, all as `property float`.
    path = write_3dgs_ply(tmp_path / "deg2.ply", _make_cloud(3, 8))
    header = path.read_bytes().split(b"end_header")[0].decode("ascii")
    lines = header.splitlines()
    assert lines[0] == "ply"
    assert lines[1] == "format binary_little_endian 1.0"
    assert lines.count("element vertex 3") == 1
    prop_lines = [line for line in lines if line.startswith("property")]
    assert prop_lines == [f"property float {name}" for name in expected]


def test_f_rest_is_channel_major(tmp_path):
    # One Gaussian, K=3 rest coefficients: rows are coefficients, columns R/G/B.
    shn = np.array([[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]]], dtype=np.float32)
    cloud = GaussianCloud(
        means=np.zeros((1, 3), dtype=np.float32),
        sh0=np.zeros((1, 3), dtype=np.float32),
        shN=shn,
        opacities=np.zeros((1,), dtype=np.float32),
        scales=np.zeros((1, 3), dtype=np.float32),
        quats=np.zeros((1, 4), dtype=np.float32),
    )
    path = write_3dgs_ply(tmp_path / "rest.ply", cloud)

    data = path.read_bytes()
    marker = b"end_header\n"
    body = data[data.index(marker) + len(marker):]
    floats = np.frombuffer(body, dtype="<f4")
    # Layout: x y z nx ny nz f_dc(3) | f_rest(9) | opacity scale(3) rot(4).
    f_rest = floats[9:18]
    # Channel-major (INRIA): all R coefficients, then all G, then all B.
    np.testing.assert_array_equal(
        f_rest,
        np.array([1.0, 4.0, 7.0, 2.0, 5.0, 8.0, 3.0, 6.0, 9.0], dtype=np.float32),
    )
    # Normals are written as zeros.
    np.testing.assert_array_equal(floats[3:6], np.zeros(3, dtype=np.float32))


def test_prune_by_opacity_keeps_top_fraction(tmp_path):
    n = 10
    cloud = _make_cloud(n, 0, seed=3)
    cloud.opacities = np.arange(n, dtype=np.float32)  # raw logits 0..9
    # Tag means so row alignment after pruning is verifiable.
    cloud.means = np.column_stack(
        [np.arange(n), np.zeros(n), np.zeros(n)]
    ).astype(np.float32)

    src = write_3dgs_ply(tmp_path / "full.ply", cloud)
    dst = prune_by_opacity(src, tmp_path / "pruned.ply", keep_ratio=0.3)
    assert dst == tmp_path / "pruned.ply"

    pruned = read_3dgs_ply(dst)
    assert pruned.opacities.shape == (3,)
    assert pruned.opacities.tolist() == [9.0, 8.0, 7.0]  # sorted descending
    # Attribute rows travel together with their opacity.
    np.testing.assert_array_equal(pruned.means[:, 0], pruned.opacities)


def test_prune_keeps_at_least_one(tmp_path):
    cloud = _make_cloud(5, 0, seed=4)
    cloud.opacities = np.array([-2.0, 3.0, 0.5, -1.0, 1.0], dtype=np.float32)

    src = write_3dgs_ply(tmp_path / "full.ply", cloud)
    dst = prune_by_opacity(src, tmp_path / "one.ply", keep_ratio=0.0)

    pruned = read_3dgs_ply(dst)
    assert pruned.opacities.shape == (1,)
    assert pruned.opacities[0] == pytest.approx(3.0)


def test_written_ply_readable_by_existing_loader(tmp_path, monkeypatch):
    from backend.services.reconstruction import (
        _compute_coverage_gaps,
        _load_ply_positions_and_colors,
    )

    monkeypatch.setattr(
        "backend.services.reconstruction.get_config",
        lambda: MagicMock(exports_dir=str(tmp_path)),
    )

    n = 50
    cloud = _make_cloud(n, 8, seed=11)
    cloud.means = np.random.default_rng(11).uniform(-5.0, 5.0, size=(n, 3)).astype(np.float32)
    path = write_3dgs_ply(tmp_path / "splat.ply", cloud)

    # LAS-export path: positions plus SH-DC-derived colors.
    xyz, rgb = _load_ply_positions_and_colors(path)
    assert xyz.shape == (n, 3)
    np.testing.assert_array_equal(xyz, cloud.means.astype(np.float64))
    assert rgb is not None
    expected_rgb = np.clip(0.5 + _SH_C0 * cloud.sh0.astype(np.float64), 0.0, 1.0) * 255.0
    np.testing.assert_allclose(rgb, expected_rgb, atol=1e-9)

    # Coverage-gap path: the header/dtype scan must accept the written layout.
    cells, output_path = _compute_coverage_gaps(path, 7)
    assert output_path == tmp_path.resolve() / "coverage_gaps_7.json"
    assert output_path.exists()
    assert json.loads(output_path.read_text()) == cells
