"""Tests for splat_cleanup — statistical outlier, opacity, and floater removal."""
from __future__ import annotations

import numpy as np

from backend.services.ply_io import GaussianCloud, write_3dgs_ply
from backend.services.splat_cleanup import cleanup_cloud, cleanup_ply_file


def _make_cloud(n: int, seed: int = 0) -> GaussianCloud:
    rng = np.random.default_rng(seed)
    return GaussianCloud(
        means=rng.normal(scale=2.0, size=(n, 3)).astype(np.float32),
        sh0=rng.normal(size=(n, 3)).astype(np.float32),
        shN=rng.normal(size=(n, 0, 3)).astype(np.float32),
        opacities=rng.normal(size=(n,)).astype(np.float32),
        scales=rng.normal(scale=0.5, size=(n, 3)).astype(np.float32),
        quats=rng.normal(size=(n, 4)).astype(np.float32),
    )


# ---------------------------------------------------------------------------
# cleanup_cloud — synthetic unit tests
# ---------------------------------------------------------------------------


def test_cleanup_preserves_cloud_structure():
    """Basic round-trip: a tight cluster stays intact."""
    cloud = _make_cloud(100, seed=1)
    cleaned, stats = cleanup_cloud(
        cloud,
        opacity_keep_ratio=0.8,
        scale_std_threshold=5.0,
        outlier_k=20,
        outlier_std_threshold=4.0,
    )
    assert 0 < cleaned.means.shape[0] <= 100
    assert cleaned.means.shape[1] == 3
    assert cleaned.sh0.shape[1] == 3
    assert cleaned.scales.shape[1] == 3
    assert cleaned.quats.shape[1] == 4
    assert stats["n_before"] == 100
    assert stats["n_after_outlier"] == cleaned.means.shape[0]


def test_low_opacity_points_removed():
    """Points with very low opacity logit should be dropped."""
    n = 100
    cloud = _make_cloud(n, seed=2)
    # Force bottom 20% to have very negative opacities.
    cloud.opacities[:20] = -10.0
    cloud.opacities[20:] = np.linspace(0, 5, n - 20).astype(np.float32)
    # Tag means to know which rows survive.
    cloud.means = np.column_stack(
        [
            np.arange(n, dtype=np.float32),
            np.zeros(n, dtype=np.float32),
            np.zeros(n, dtype=np.float32),
        ]
    )

    cleaned, stats = cleanup_cloud(cloud, opacity_keep_ratio=0.7)
    # With keep ratio 0.7 and 100 points, we keep ~70.  The 20 low-opacity
    # points should all be below the cutoff.
    assert stats["opacity_keep"] <= 70
    # And none of the first 20 rows (indices 0..19) should survive.
    surviving_ids = cleaned.means[:, 0].astype(int)
    assert not any(sid < 20 for sid in surviving_ids)


def test_huge_scale_floaters_removed():
    """Gaussians with abnormally large log-scales should be dropped."""
    cloud = _make_cloud(100, seed=3)
    # Give 5 gaussians enormous scale; the rest stay normal.
    # Tag them with a unique means value so we can verify removal.
    for i in range(5):
        cloud.scales[i] = np.array([200.0, 200.0, 200.0], dtype=np.float32)
        cloud.means[i] = np.array([-9999.0, -9999.0, -9999.0], dtype=np.float32)

    cleaned, stats = cleanup_cloud(
        cloud, opacity_keep_ratio=1.0, scale_std_threshold=3.0,
        outlier_k=0,  # skip outlier step so we isolate scale filtering
    )
    assert stats["scale_clipped"] >= 5
    # None of the tagged points should survive.
    tagged_mask = (
        (cleaned.means[:, 0] == -9999.0)
        & (cleaned.means[:, 1] == -9999.0)
        & (cleaned.means[:, 2] == -9999.0)
    )
    assert not tagged_mask.any()


def test_statistical_outliers_removed():
    """A lone point far from a tight cluster should be removed."""
    # 99 points in a tight cluster at origin, 1 outlier far away.
    cluster = np.random.default_rng(4).normal(scale=0.5, size=(99, 3)).astype(np.float32)
    outlier = np.array([[50.0, 50.0, 50.0]], dtype=np.float32)
    means = np.vstack([cluster, outlier])

    cloud = GaussianCloud(
        means=means,
        sh0=np.zeros((100, 3), dtype=np.float32),
        shN=np.zeros((100, 0, 3), dtype=np.float32),
        opacities=np.ones(100, dtype=np.float32),
        scales=np.zeros((100, 3), dtype=np.float32),
        quats=np.zeros((100, 4), dtype=np.float32),
    )

    cleaned, stats = cleanup_cloud(
        cloud, opacity_keep_ratio=1.0, scale_std_threshold=100.0,
        outlier_k=10, outlier_std_threshold=4.0,
    )
    assert stats["outlier_clipped"] == 1
    assert cleaned.means.shape[0] == 99


def test_no_filters_given_keeps_everything():
    """Passing keep_ratio=1.0 and disabling scale/outlier steps keeps all."""
    cloud = _make_cloud(50, seed=5)
    cleaned, stats = cleanup_cloud(
        cloud, opacity_keep_ratio=1.0, scale_std_threshold=1e9,
        outlier_k=0,
    )
    assert cleaned.means.shape[0] == 50
    assert stats["n_before"] == 50
    assert stats["opacity_keep"] == 50
    assert stats["n_after_outlier"] == 50


# ---------------------------------------------------------------------------
# cleanup_ply_file — end-to-end file tests
# ---------------------------------------------------------------------------


def test_cleanup_ply_file_roundtrip(tmp_path):
    """Write a cloud, clean it, verify the output PLY is readable and correct."""
    n = 20
    cloud = _make_cloud(n, seed=6)
    # Mix of opacities: some low, some high.
    cloud.opacities[:5] = -5.0
    cloud.opacities[5:] = np.arange(5, 20).astype(np.float32)
    cloud.means = np.column_stack(
        [
            np.arange(n, dtype=np.float32),
            np.zeros(n, dtype=np.float32),
            np.zeros(n, dtype=np.float32),
        ]
    )

    src = write_3dgs_ply(tmp_path / "in.ply", cloud)
    dst = tmp_path / "out.ply"

    stats, n_before, n_after = cleanup_ply_file(
        src, dst,
        opacity_keep_ratio=0.5,
        scale_std_threshold=1e9,
        outlier_k=0,
    )
    assert n_before == n
    assert n_after < n  # dropped low-opacity points
    assert dst.exists()
    assert stats["n_before"] == n
    assert stats["n_after_outlier"] == n_after

    # Original file untouched.
    from backend.services.ply_io import read_3dgs_ply
    original = read_3dgs_ply(src)
    assert original.means.shape[0] == n

    # Cleaned file readable.
    cleaned = read_3dgs_ply(dst)
    assert cleaned.means.shape[0] == n_after


def test_cleanup_empty_cloud_survives(tmp_path):
    """Three-point cloud: shouldn't crash even if filters are aggressive."""
    cloud = GaussianCloud(
        means=np.zeros((3, 3), dtype=np.float32),
        sh0=np.zeros((3, 3), dtype=np.float32),
        shN=np.zeros((3, 0, 3), dtype=np.float32),
        opacities=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        scales=np.zeros((3, 3), dtype=np.float32),
        quats=np.zeros((3, 4), dtype=np.float32),
    )
    src = write_3dgs_ply(tmp_path / "in.ply", cloud)
    stats, n_before, n_after = cleanup_ply_file(src, tmp_path / "out.ply")
    assert n_before == 3
    assert n_after >= 1  # keep_ratio default 0.05 → at least 1
    assert stats["n_after_outlier"] == n_after


def test_all_filter_phases_contribute(tmp_path):
    """Ensure all three filter phases can fire on a crafted cloud."""
    n = 200
    rng = np.random.default_rng(7)
    # Tight cluster in the middle.
    means = rng.normal(scale=1.0, size=(n, 3)).astype(np.float32)
    # Inject 5 huge-scale floaters.
    scales = rng.normal(scale=0.3, size=(n, 3)).astype(np.float32)
    scales[:5] = np.array([100.0, 100.0, 100.0], dtype=np.float32)
    # Inject 10 low-opacity points.
    opacities = rng.normal(size=(n,)).astype(np.float32) + 2.0
    opacities[5:15] = -10.0
    # Inject 3 spatial outliers.
    means[15:18] = np.array([200.0, 200.0, 200.0], dtype=np.float32)
    # Inject 2 more that are both low-opacity AND huge-scale to confirm
    # ordering: opacity drops them first, then scale filter sees fewer points.
    opacities[18:20] = -10.0
    scales[18:20] = np.array([100.0, 100.0, 100.0], dtype=np.float32)

    cloud = GaussianCloud(
        means=means,
        sh0=np.zeros((n, 3), dtype=np.float32),
        shN=np.zeros((n, 0, 3), dtype=np.float32),
        opacities=opacities,
        scales=scales,
        quats=np.zeros((n, 4), dtype=np.float32),
    )

    src = write_3dgs_ply(tmp_path / "in.ply", cloud)
    stats, n_before, n_after = cleanup_ply_file(
        src, tmp_path / "out.ply",
        opacity_keep_ratio=0.85,
        scale_std_threshold=4.0,
        outlier_k=10,
        outlier_std_threshold=3.0,
    )
    assert n_before == n
    assert n_after < n
    assert stats["opacity_keep"] < n
    assert stats["scale_clipped"] > 0
    assert stats["outlier_clipped"] > 0

def test_target_area_crop_removes_points_outside_polygon():
    cloud = GaussianCloud(
        means=np.array([[0.5, 0.5, 0.0], [1.5, 0.5, 0.0], [0.5, 1.5, 0.0]], dtype=np.float32),
        sh0=np.zeros((3, 3), dtype=np.float32),
        shN=np.zeros((3, 0, 3), dtype=np.float32),
        opacities=np.ones(3, dtype=np.float32),
        scales=np.zeros((3, 3), dtype=np.float32),
        quats=np.zeros((3, 4), dtype=np.float32),
    )
    polygon = '{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'

    cleaned, stats = cleanup_cloud(
        cloud,
        opacity_keep_ratio=1.0,
        outlier_k=0,
        scale_std_threshold=1e9,
        target_area_geojson=polygon,
    )

    assert cleaned.means.shape[0] == 1
    assert cleaned.means[0].tolist() == [0.5, 0.5, 0.0]
    assert stats["target_area_clipped"] == 2
    assert stats["n_after_outlier"] == 1
