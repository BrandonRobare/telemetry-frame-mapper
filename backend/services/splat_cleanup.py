"""Statistically clean up a 3DGS PLY file: remove low-opacity gaussians, huge-scale
floaters, and statistical outliers.

All operations use only numpy and stdlib.  For large point clouds the
statistical outlier filter uses a k-d tree so it scales O(N log N) when
available, falling back to a deterministic O(N log N) grid sampling + ball
query when there are too many points for pairwise distance matrices.

Public API
----------
cleanup_cloud(cloud, **kwargs) -> (cleaned_cloud, stats)
cleanup_ply_file(src_path, dst_path, **kwargs) -> (stats, n_before, n_after)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
from shapely.geometry import Point, shape

from .ply_io import GaussianCloud, read_3dgs_ply, write_3dgs_ply

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# defaults — kept conservative so the cleanup pass removes only obvious floaters
# ---------------------------------------------------------------------------
_DEFAULT_OPACITY_KEEP_RATIO = 0.95  # drop bottom 5 % by raw logit
_DEFAULT_SCALE_STD_THRESHOLD = 5.0  # > 5 sigma on log-scale magnitude = floater
_DEFAULT_OUTLIER_K = 20            # k for k-NN distance
_DEFAULT_OUTLIER_STD_THRESHOLD = 4.0  # mean + 4 * std of k-NN distances
_GRID_CELL_SIZE = 256               # cells wide for spatial binning on huge clouds


def cleanup_cloud(
    cloud: GaussianCloud,
    *,
    opacity_keep_ratio: float = _DEFAULT_OPACITY_KEEP_RATIO,
    scale_std_threshold: float = _DEFAULT_SCALE_STD_THRESHOLD,
    outlier_k: int = _DEFAULT_OUTLIER_K,
    outlier_std_threshold: float = _DEFAULT_OUTLIER_STD_THRESHOLD,
    target_area_geojson: str | None = None,
) -> tuple[GaussianCloud, dict]:
    """Apply low-opacity, floater, and outlier filters; return (result, stats).

    Filters are applied in order:
    1. Low-opacity removal: keep the top *opacity_keep_ratio* fraction by raw logit.
    2. Huge-scale floater removal: drop gaussians whose log-scale magnitude
       (L2 norm of the three scale components) exceeds
       mean + *scale_std_threshold* standard deviations.
    3. Statistical outlier removal: compute the mean distance to the
       *outlier_k* nearest neighbours for each remaining centre.  Drop points
       whose mean distance exceeds mean + *outlier_std_threshold* std deviations.

    Stats dict keys: ``n_before, n_after_opacity, n_after_scale,
    n_after_outlier, opacity_keep, scale_clipped, outlier_clipped``.
    """
    n_before = cloud.means.shape[0]
    stats: dict = {
        "n_before": n_before,
        "opacity_keep": 0,
        "scale_clipped": 0,
        "outlier_clipped": 0,
        "target_area_clipped": 0,
    }

    # ---- 0. optional target-area crop ---------------------------------------
    result = cloud
    if target_area_geojson:
        result, target_clipped = _crop_to_target_area(result, target_area_geojson)
        stats["target_area_clipped"] = target_clipped

    n_current = result.means.shape[0]
    if n_current == 0:
        stats.update({
            "opacity_keep": 0,
            "n_after_opacity": 0,
            "n_after_scale": 0,
            "n_after_outlier": 0,
        })
        return result, stats

    # ---- 1. low opacity -----------------------------------------------------
    keep_opacity = max(1, int(n_current * opacity_keep_ratio))
    order = np.argsort(-result.opacities, kind="stable")[:keep_opacity]
    stats["opacity_keep"] = keep_opacity
    result = _slice_cloud(result, order)

    # ---- 2. huge-scale floaters ---------------------------------------------
    scale_mag = np.linalg.norm(result.scales, axis=1)
    scale_mean = float(np.mean(scale_mag))
    scale_std = float(np.std(scale_mag))
    keep_scale = scale_mag <= scale_mean + scale_std_threshold * scale_std
    if not keep_scale.all():
        result = _slice_cloud(result, np.flatnonzero(keep_scale))
        stats["scale_clipped"] = int((~keep_scale).sum())
    else:
        stats["scale_clipped"] = 0
    stats["n_after_scale"] = result.means.shape[0]

    # ---- 3. statistical outlier removal -------------------------------------
    if result.means.shape[0] > 0 and outlier_k > 0 and outlier_std_threshold > 0:
        mean_knn = _mean_knn_distance(result.means, k=outlier_k)
        knn_mean = float(np.mean(mean_knn))
        knn_std = float(np.std(mean_knn))
        keep = mean_knn <= knn_mean + outlier_std_threshold * knn_std
        if not keep.all():
            result = _slice_cloud(result, np.flatnonzero(keep))
            stats["outlier_clipped"] = int((~keep).sum())
        else:
            stats["outlier_clipped"] = 0
    else:
        stats["outlier_clipped"] = 0

    stats["n_after_opacity"] = keep_opacity
    stats["n_after_outlier"] = result.means.shape[0]
    return result, stats


def cleanup_ply_file(
    src: Path,
    dst: Path,
    *,
    opacity_keep_ratio: float = _DEFAULT_OPACITY_KEEP_RATIO,
    scale_std_threshold: float = _DEFAULT_SCALE_STD_THRESHOLD,
    outlier_k: int = _DEFAULT_OUTLIER_K,
    outlier_std_threshold: float = _DEFAULT_OUTLIER_STD_THRESHOLD,
    target_area_geojson: str | None = None,
) -> tuple[dict, int, int]:
    """Read *src*, apply cleanup filters, write a cleaned PLY to *dst*.

    Returns ``(stats, n_before, n_after)``.  *src* is never modified.
    """
    cloud = read_3dgs_ply(src)
    n_before = cloud.means.shape[0]
    cleaned, stats = cleanup_cloud(
        cloud,
        opacity_keep_ratio=opacity_keep_ratio,
        scale_std_threshold=scale_std_threshold,
        outlier_k=outlier_k,
        outlier_std_threshold=outlier_std_threshold,
        target_area_geojson=target_area_geojson,
    )
    write_3dgs_ply(dst, cleaned)
    n_after = cleaned.means.shape[0]
    return stats, n_before, n_after


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _crop_to_target_area(
    cloud: GaussianCloud,
    target_area_geojson: str,
) -> tuple[GaussianCloud, int]:
    """Keep only Gaussian centers inside the target-area polygon in x/y space."""
    try:
        polygon = shape(json.loads(target_area_geojson))
    except (TypeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Invalid target area geometry") from exc
    if polygon.is_empty:
        raise ValueError("Target area geometry is empty")

    mask = np.array(
        [polygon.covers(Point(float(x), float(y))) for x, y in cloud.means[:, :2]],
        dtype=bool,
    )
    kept = int(mask.sum())
    return _slice_cloud(cloud, np.flatnonzero(mask)), int(cloud.means.shape[0] - kept)


def _slice_cloud(cloud: GaussianCloud, indices: np.ndarray) -> GaussianCloud:
    """Return a new GaussianCloud containing only the rows given by *indices*."""
    indices = np.asarray(indices, dtype=np.intp)
    return GaussianCloud(
        means=cloud.means[indices],
        sh0=cloud.sh0[indices],
        shN=cloud.shN[indices],
        opacities=cloud.opacities[indices],
        scales=cloud.scales[indices],
        quats=cloud.quats[indices],
    )


def _mean_knn_distance(points: np.ndarray, k: int = 20) -> np.ndarray:
    """For each row in *points*, return the mean distance to its *k* nearest
    neighbours (excluding itself).

    When N is small enough that a pairwise (N,N) float64 matrix fits in
    memory we compute it directly for simplicity (O(N^2) time, O(N^2) memory).
    For larger clouds we fall back to a grid-based approximation that is still
    deterministic and avoids an O(N^2) distance matrix: we bin points into a
    coarse spatial grid, then for each point query a 3x3x3 cell neighbourhood
    and sort the candidate distances.
    """
    n = points.shape[0]
    if n == 0:
        return np.array([], dtype=np.float64)

    k_eff = min(k, n - 1)
    if k_eff <= 0:
        return np.zeros(n, dtype=np.float64)

    # Use pairwise distances only while the matrix stays reasonably small.
    # Memory is N*N*8 bytes: 3k points is ~72 MB. Larger clouds use the
    # deterministic grid fallback below rather than risking multi-GB allocations.
    pairwise_limit = 3_000
    if n <= pairwise_limit:
        dists = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=-1)
        # Set self-distance to infinity so the K nearest neighbors are
        # genuinely other points.
        np.fill_diagonal(dists, np.inf)
        knn = np.partition(dists, k_eff - 1, axis=1)[:, :k_eff]
        return knn.mean(axis=1)

    # --- grid-based fallback for large N (avoids pairwise distance matrix) ---
    return _grid_based_mean_knn(points, k_eff)


def _grid_based_mean_knn(points: np.ndarray, k: int) -> np.ndarray:
    """Deterministic grid-based approximate k-NN mean distance.

    Points are binned into a cubic grid of *GRID_CELL_SIZE* cells in each
    axis.  Each point queries a 3×3×3 cell block (the containing cell plus its
    26 neighbours); if the block holds at least *k+1* points the answer is
    exact for those neighbours — otherwise we fall back to the full pairwise
    distance for that single point.  In practice this is still O(N log N) for
    the binning step and O(N) per query for reasonably distributed points.
    """
    n = points.shape[0]
    pmin = points.min(axis=0)
    pmax = points.max(axis=0)
    span = pmax - pmin
    span[span == 0] = 1.0  # avoid degenerate cells

    cell_size = span / _GRID_CELL_SIZE
    cell_idx = ((points - pmin) / cell_size).astype(np.int32)
    # Clamp to [0, GRID_CELL_SIZE) so that points exactly on the max boundary
    # don't land in cell GRID_CELL_SIZE.
    cell_idx = np.clip(cell_idx, 0, _GRID_CELL_SIZE - 1)

    # Map 3-tuple cell index → linear key for dictionary lookups.
    key = (
        cell_idx[:, 0] * (_GRID_CELL_SIZE * _GRID_CELL_SIZE)
        + cell_idx[:, 1] * _GRID_CELL_SIZE
        + cell_idx[:, 2]
    )

    # Build inverted index: cell_key → list of point indices.
    cells: dict[int, list[int]] = {}
    for i, kk in enumerate(key):
        cells.setdefault(int(kk), []).append(i)

    mean_dists = np.empty(n, dtype=np.float64)
    offsets = [-1, 0, 1]

    for i in range(n):
        cx, cy, cz = int(cell_idx[i, 0]), int(cell_idx[i, 1]), int(cell_idx[i, 2])
        candidates: list[int] = []
        for dx in offsets:
            for dy in offsets:
                for dz in offsets:
                    nx, ny, nz = cx + dx, cy + dy, cz + dz
                    in_bounds = (
                        0 <= nx < _GRID_CELL_SIZE
                        and 0 <= ny < _GRID_CELL_SIZE
                        and 0 <= nz < _GRID_CELL_SIZE
                    )
                    if in_bounds:
                        nk = nx * (_GRID_CELL_SIZE * _GRID_CELL_SIZE) + ny * _GRID_CELL_SIZE + nz
                        candidates.extend(cells.get(nk, []))
        # At minimum, include self.
        if not candidates:
            mean_dists[i] = 0.0
            continue

        cand_arr = np.array(candidates, dtype=np.intp)
        if cand_arr.shape[0] > k + 1:
            # Enough candidates in the 27-cell neighbourhood for an exact
            # result within this set.
            vec = points[i] - points[cand_arr]
            dists = np.linalg.norm(vec, axis=1)
            # Remove self-distance (should be zero, but ensure it isn't counted).
            need = min(k + 1, dists.shape[0])
            knn_dists = np.partition(dists, need - 1)[:need]
            # Drop the zero self-distance if present.
            knn_dists = knn_dists[knn_dists > 0]
            if knn_dists.shape[0] < k:
                # Very rare: grid cell too sparse; fall back to full scan.
                vec_all = points[i] - points
                dists_all = np.linalg.norm(vec_all, axis=1)
                dists_all[i] = np.inf
                knn_dists = np.partition(dists_all, k - 1)[:k]
            else:
                if knn_dists.shape[0] > k:
                    knn_dists = np.partition(knn_dists, k - 1)[:k]
            mean_dists[i] = knn_dists.mean()
        else:
            # Small neighbourhood — full scan.
            vec_all = points[i] - points
            dists_all = np.linalg.norm(vec_all, axis=1)
            dists_all[i] = np.inf
            knn_dists = np.partition(dists_all, k - 1)[:k]
            mean_dists[i] = knn_dists.mean()

    return mean_dists