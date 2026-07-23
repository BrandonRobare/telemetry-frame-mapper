"""In-process COLMAP-world -> UTM georeferencing solve (issue #496).

COLMAP reconstructs in an arbitrary local frame with arbitrary scale. To place
the model on the map we fit a similarity transform (scale + rotation +
translation) from each registered camera centre to the frame's GPS position in
UTM. This is a classic Umeyama least-squares fit — no COLMAP binary, no torch,
version-independent, and testable in isolation (only numpy + pyproj + the
pure-numpy :mod:`colmap_io` reader are imported).

The resulting ``geo_transform.json`` matches the schema
``reconstruction._world_points_to_utm`` consumes: a UTM point is
``scale * (R @ p_world) + translation + [utm_origin_e, utm_origin_n, 0]``.

Altitude note: DJI frames store *relative* altitude (above take-off), so the
solved Z origin is take-off level rather than MSL. Umeyama absorbs that constant
offset into the translation; horizontal placement and metric scale are correct.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pyproj

from backend.services import colmap_io

logger = logging.getLogger(__name__)

# Reject a fit whose source camera centres do not span a plane: a single
# straight flight line (rank-1 spread) cannot constrain roll about the track.
# ponytail: fixed ratio on the 2nd singular value — revisit only if real flights
# with genuine 2D extent get wrongly rejected.
_MIN_COLLINEARITY_RATIO = 1e-3
_MIN_CORRESPONDENCES = 3
_TRIM_SIGMA = 3.0


def umeyama(src: np.ndarray, dst: np.ndarray) -> tuple[float, np.ndarray, np.ndarray] | None:
    """Fit ``dst ~= scale * R @ src + t`` (Umeyama 1991, with scale).

    Returns ``(scale, R, t)`` or ``None`` when the source points are degenerate
    (fewer than 3 points, near-zero spread, or near-collinear).
    """
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    n = src.shape[0]
    if n < _MIN_CORRESPONDENCES or dst.shape[0] != n:
        return None

    mu_src = src.mean(axis=0)
    mu_dst = dst.mean(axis=0)
    src_c = src - mu_src
    dst_c = dst - mu_dst

    var_src = float((src_c**2).sum() / n)
    if var_src < 1e-12:
        return None  # all cameras at the same point

    singular = np.linalg.svd(src_c, compute_uv=False)
    if singular[0] <= 0.0 or singular[1] / singular[0] < _MIN_COLLINEARITY_RATIO:
        return None  # collinear: no 2D spread to constrain the rotation

    cov = (dst_c.T @ src_c) / n
    u, d, vt = np.linalg.svd(cov)
    s = np.eye(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        s[2, 2] = -1.0
    rotation = u @ s @ vt
    scale = float((d * np.diag(s)).sum() / var_src)
    translation = mu_dst - scale * (rotation @ mu_src)
    return scale, rotation, translation


def _solve_with_trim(
    src: np.ndarray, dst: np.ndarray
) -> tuple[float, np.ndarray, np.ndarray] | None:
    """Umeyama with one robustness pass: drop >3 sigma residuals and re-solve."""
    solution = umeyama(src, dst)
    if solution is None:
        return None
    scale, rotation, translation = solution
    predicted = scale * (src @ rotation.T) + translation
    residual = np.linalg.norm(dst - predicted, axis=1)
    sigma = float(residual.std())
    if sigma <= 0.0:
        return solution
    keep = np.abs(residual - np.median(residual)) <= _TRIM_SIGMA * sigma
    # ponytail: single trim pass — full RANSAC if flight GPS proves noisier than this.
    if keep.all() or keep.sum() < 4:
        return solution
    retried = umeyama(src[keep], dst[keep])
    return retried or solution


def _utm_zone_str(lon: float, lat: float) -> tuple[str, pyproj.Transformer]:
    """Return the UTM zone label (e.g. "17N") and a WGS84->UTM transformer."""
    zone = int((lon + 180) / 6) + 1
    southern = lat < 0.0
    crs = pyproj.CRS.from_dict({"proj": "utm", "zone": zone, "south": southern})
    transformer = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    return f"{zone}{'S' if southern else 'N'}", transformer


def _correspondences(sparse_dir: Path, images: list) -> tuple[np.ndarray, np.ndarray] | None:
    """Build (camera_centres, gps_lonlatalt) for registered, GPS-tagged frames."""
    gps = {
        img.filename: (img.longitude, img.latitude, img.altitude_m)
        for img in images
        if img.latitude is not None and img.longitude is not None and img.altitude_m is not None
    }
    if not gps:
        return None
    try:
        model = colmap_io.read_model(sparse_dir)
    except (RuntimeError, OSError, ValueError) as exc:
        logger.warning("Georeferencing: sparse model unreadable at %s: %s", sparse_dir, exc)
        return None

    centres: list[np.ndarray] = []
    lonlatalt: list[tuple[float, float, float]] = []
    for image in model.images:
        coords = gps.get(image.name)
        if coords is None:
            continue
        centres.append(colmap_io.camera_center(image))
        lonlatalt.append(coords)
    if len(centres) < _MIN_CORRESPONDENCES:
        return None
    return np.array(centres, dtype=np.float64), np.array(lonlatalt, dtype=np.float64)


def compute_geo_transform(colmap_dir: Path, sparse_dir: Path, images: list) -> dict | None:
    """Solve COLMAP-world -> UTM and write ``geo_transform.json``.

    ``images`` are the DB ``Image`` rows for the reconstruction (need
    ``filename``, ``latitude``, ``longitude``, ``altitude_m``). Returns the
    transform dict on success (and writes the file); returns ``None`` on any
    failure without writing, logging the reason at WARNING.
    """
    built = _correspondences(sparse_dir, images)
    if built is None:
        logger.warning(
            "Georeferencing failed: fewer than %d GPS-tagged registered frames",
            _MIN_CORRESPONDENCES,
        )
        return None
    centres, lonlatalt = built

    mean_lon = float(lonlatalt[:, 0].mean())
    mean_lat = float(lonlatalt[:, 1].mean())
    utm_zone, transformer = _utm_zone_str(mean_lon, mean_lat)
    easting, northing = transformer.transform(lonlatalt[:, 0], lonlatalt[:, 1])
    origin_e = float(np.mean(easting))
    origin_n = float(np.mean(northing))
    dst = np.column_stack([easting - origin_e, northing - origin_n, lonlatalt[:, 2]])

    solution = _solve_with_trim(centres, dst)
    if solution is None:
        logger.warning("Georeferencing failed: degenerate camera-centre geometry")
        return None
    scale, rotation, translation = solution

    geo = {
        "scale": scale,
        "rotation": rotation.tolist(),
        "translation": translation.tolist(),
        "utm_zone": utm_zone,
        "utm_origin": [origin_e, origin_n],
    }
    (colmap_dir / "geo_transform.json").write_text(json.dumps(geo, indent=2), encoding="utf-8")
    return geo
