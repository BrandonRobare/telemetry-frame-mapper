"""Nearest-Gaussian search: bounded memory and unchanged results (#633)."""

import tracemalloc

import numpy as np

from backend.services import reconstruction
from backend.services.reconstruction import _nearest_gaussian_indices


def _brute_force(points_xyz, gaussian_xyz):
    """Reference: the full (points, gaussians, 3) broadcast used before #633."""
    distances = ((points_xyz[:, None, :] - gaussian_xyz[None, :, :]) ** 2).sum(axis=2)
    return np.argmin(distances, axis=1)


def test_matches_brute_force_on_fixture_cloud():
    rng = np.random.default_rng(1234)
    points = rng.random((300, 3)) * 50.0
    gaussians = rng.random((800, 3)) * 50.0

    result = _nearest_gaussian_indices(points, gaussians)

    assert result.dtype == np.int64
    np.testing.assert_array_equal(result, _brute_force(points, gaussians))


def test_matches_brute_force_across_block_boundaries(monkeypatch):
    monkeypatch.setattr(reconstruction, "_NEAREST_BLOCK", 5)
    rng = np.random.default_rng(99)
    points = rng.random((23, 3)) * 10.0
    gaussians = rng.random((17, 3)) * 10.0

    result = _nearest_gaussian_indices(points, gaussians)

    np.testing.assert_array_equal(result, _brute_force(points, gaussians))


def test_matches_brute_force_for_a_tight_cloud_far_from_origin():
    """A dense cloud at UTM coordinates: this is what the centering buys.

    Without subtracting a common origin the ‖b‖² and 2·a·b terms are ~2e13 while
    the distances being compared are ~1e-4, and the expansion picks Gaussians up
    to 65x farther away than the nearest (39 of these 40 points).
    """
    rng = np.random.default_rng(11)
    origin = np.array([512_345.0, 4_567_890.0, 1_234.0])
    points = origin + rng.normal(size=(40, 3)) * 0.02
    gaussians = origin + rng.normal(size=(120, 3)) * 0.02

    result = _nearest_gaussian_indices(points, gaussians)

    np.testing.assert_array_equal(result, _brute_force(points, gaussians))


def test_duplicate_gaussians_resolve_to_the_lowest_index(monkeypatch):
    monkeypatch.setattr(reconstruction, "_NEAREST_BLOCK", 2)
    points = np.array([[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]])
    # Index 1 and 4 are the same point, and land in different blocks.
    gaussians = np.array([
        [9.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [8.0, 0.0, 0.0],
        [5.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
    ])

    result = _nearest_gaussian_indices(points, gaussians)

    np.testing.assert_array_equal(result, [1, 3])


def test_equidistant_distinct_gaussians_pick_a_true_nearest():
    """Only equal *coordinates* tie bit for bit; equal distances may go either way."""
    points = np.array([[0.0, 0.0, 0.0]])
    gaussians = np.array([[2.0, 0.0, 0.0], [-2.0, 0.0, 0.0]])

    assert _nearest_gaussian_indices(points, gaussians).tolist() in ([0], [1])


def test_no_gaussians_yields_sentinel_indices():
    points = np.zeros((4, 3))

    result = _nearest_gaussian_indices(points, np.zeros((0, 3)))

    np.testing.assert_array_equal(result, [-1, -1, -1, -1])


def test_no_points_yields_empty_indices():
    result = _nearest_gaussian_indices(np.zeros((0, 3)), np.zeros((3, 3)))

    assert result.shape == (0,)


def test_peak_allocation_is_bounded_for_a_large_gaussian_count():
    rng = np.random.default_rng(5)
    points = rng.random((2048, 3)) * 100.0
    gaussians = rng.random((120_000, 3)) * 100.0
    # Pre-#633 this allocated (512, G, 3) float64 on every chunk.
    naive_bytes = 512 * len(gaussians) * 3 * 8

    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        before = tracemalloc.get_traced_memory()[0]
        indices = _nearest_gaussian_indices(points, gaussians)
        peak = tracemalloc.get_traced_memory()[1] - before
    finally:
        tracemalloc.stop()

    assert indices.shape == (len(points),)
    assert peak < 64 * 1024**2, (
        f"peak {peak / 1e6:.1f} MB for {len(gaussians)} gaussians "
        f"(the old broadcast needed {naive_bytes / 1e9:.1f} GB per chunk)"
    )
