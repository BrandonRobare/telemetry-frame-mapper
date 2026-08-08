"""Unit + integration tests for the in-process COLMAP->UTM solve (issue #496).

These run without COLMAP or torch: the solve reads a hand-built TXT sparse
model and plain objects standing in for DB Image rows.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from backend.services import colmap_io
from backend.services.georeferencing_solve import (
    _solve_with_trim,
    _utm_zone_str,
    compute_geo_transform,
    umeyama,
)

# ---------------------------------------------------------------------------
# umeyama
# ---------------------------------------------------------------------------


def _random_rotation(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    q, _ = np.linalg.qr(rng.standard_normal((3, 3)))
    if np.linalg.det(q) < 0:
        q[:, 0] = -q[:, 0]
    return q


def test_umeyama_recovers_known_similarity():
    rng = np.random.default_rng(0)
    src = rng.standard_normal((30, 3)) * 10.0
    scale_true = 2.5
    rot_true = _random_rotation(1)
    trans_true = np.array([100.0, -50.0, 7.0])
    dst = scale_true * (src @ rot_true.T) + trans_true

    scale, rot, trans = umeyama(src, dst)

    assert scale == pytest.approx(scale_true, rel=1e-9)
    np.testing.assert_allclose(rot, rot_true, atol=1e-9)
    np.testing.assert_allclose(trans, trans_true, atol=1e-6)


def test_umeyama_recovers_similarity_under_noise():
    rng = np.random.default_rng(2)
    src = rng.standard_normal((200, 3)) * 20.0
    scale_true = 0.8
    rot_true = _random_rotation(3)
    trans_true = np.array([500.0, 300.0, -12.0])
    dst = scale_true * (src @ rot_true.T) + trans_true
    dst += rng.standard_normal(dst.shape) * 0.05  # small GPS-scale noise

    scale, rot, trans = umeyama(src, dst)

    assert scale == pytest.approx(scale_true, rel=1e-2)
    np.testing.assert_allclose(rot, rot_true, atol=1e-2)


def test_umeyama_too_few_points_returns_none():
    assert umeyama(np.zeros((2, 3)), np.zeros((2, 3))) is None


def test_umeyama_collinear_returns_none():
    t = np.linspace(0, 100, 20)
    src = np.column_stack([t, 2 * t, -t])  # a straight line in 3D
    dst = src * 1.5 + np.array([10.0, 20.0, 30.0])
    assert umeyama(src, dst) is None


def test_umeyama_coincident_points_returns_none():
    src = np.ones((5, 3))
    dst = np.arange(15, dtype=float).reshape(5, 3)
    assert umeyama(src, dst) is None


def test_solve_with_trim_reports_applied_points():
    rng = np.random.default_rng(4)
    src = rng.standard_normal((11, 3))
    dst = src.copy()
    dst[-1] += 1_000.0

    solved = _solve_with_trim(src, dst)

    assert solved is not None
    (scale, rotation, translation), trimmed_point_count = solved
    assert trimmed_point_count == 1
    assert scale == pytest.approx(1.0, rel=1e-6)
    np.testing.assert_allclose(rotation, np.eye(3), atol=1e-6)
    np.testing.assert_allclose(translation, np.zeros(3), atol=1e-6)


# ---------------------------------------------------------------------------
# compute_geo_transform
# ---------------------------------------------------------------------------


def _write_sparse_model(sparse_dir: Path, centres_by_name: dict[str, np.ndarray]) -> None:
    """Write a minimal TXT COLMAP model with identity rotation and given centres.

    With qvec = identity, tvec = -centre, so camera_center() recovers `centre`.
    """
    sparse_dir.mkdir(parents=True, exist_ok=True)
    (sparse_dir / "cameras.txt").write_text("1 PINHOLE 640 480 500 500 320 240\n")
    (sparse_dir / "points3D.txt").write_text("")
    lines = []
    for image_id, (name, centre) in enumerate(centres_by_name.items(), start=1):
        tx, ty, tz = (-centre).tolist()
        lines.append(f"{image_id} 1 0 0 0 {tx} {ty} {tz} 1 {name}")
        lines.append("")  # POINTS2D line (skipped by the reader)
    (sparse_dir / "images.txt").write_text("\n".join(lines) + "\n")


def _image(name: str, lon: float, lat: float, alt: float) -> SimpleNamespace:
    return SimpleNamespace(filename=name, longitude=lon, latitude=lat, altitude_m=alt)


def test_compute_geo_transform_writes_file_and_round_trips(tmp_path):
    # A small 2D grid of GPS points near Charlotte, NC (UTM zone 17N).
    gps = {
        "f1.jpg": (-80.8430, 35.2270, 210.0),
        "f2.jpg": (-80.8420, 35.2270, 212.0),
        "f3.jpg": (-80.8430, 35.2280, 214.0),
        "f4.jpg": (-80.8420, 35.2280, 216.0),
        "f5.jpg": (-80.8425, 35.2275, 213.0),
    }
    zone, transformer = _utm_zone_str(-80.8425, 35.2275)
    origin_e, origin_n = None, None
    eastings, northings = [], []
    for lon, lat, _alt in gps.values():
        e, n = transformer.transform(lon, lat)
        eastings.append(e)
        northings.append(n)
    origin_e = float(np.mean(eastings))
    origin_n = float(np.mean(northings))

    # Camera centres = the UTM-local targets (identity similarity, scale 1).
    centres = {
        name: np.array([e - origin_e, n - origin_n, alt])
        for (name, (lon, lat, alt)), e, n in zip(gps.items(), eastings, northings, strict=True)
    }

    colmap_dir = tmp_path / "colmap"
    sparse_dir = colmap_dir / "sparse" / "0"
    _write_sparse_model(sparse_dir, centres)

    images = [_image(name, lon, lat, alt) for name, (lon, lat, alt) in gps.items()]
    geo = compute_geo_transform(colmap_dir, sparse_dir, images)

    assert geo is not None
    assert geo["utm_zone"] == zone == "17N"
    assert geo["scale"] == pytest.approx(1.0, rel=1e-6)
    assert geo["rmse_m"] == pytest.approx(0.0, abs=1e-6)
    assert geo["trimmed_point_count"] == 0
    np.testing.assert_allclose(geo["rotation"], np.eye(3), atol=1e-6)
    # File written for the reader.
    written = json.loads((colmap_dir / "geo_transform.json").read_text())
    assert written["utm_zone"] == "17N"

    # Round-trip: applying the transform to a camera centre recovers its GPS UTM.
    rot = np.array(geo["rotation"])
    trans = np.array(geo["translation"])
    origin = np.array([geo["utm_origin"][0], geo["utm_origin"][1], 0.0])
    for name, (lon, lat, alt) in gps.items():
        e, n = transformer.transform(lon, lat)
        predicted = geo["scale"] * (rot @ centres[name]) + trans + origin
        np.testing.assert_allclose(predicted, [e, n, alt], atol=1e-3)


def test_compute_geo_transform_recovers_nontrivial_scale_and_rotation(tmp_path):
    gps = {
        "a.jpg": (-80.8430, 35.2270, 210.0),
        "b.jpg": (-80.8415, 35.2272, 214.0),
        "c.jpg": (-80.8428, 35.2285, 208.0),
        "d.jpg": (-80.8410, 35.2288, 220.0),
        "e.jpg": (-80.8420, 35.2278, 212.0),
        "f.jpg": (-80.8435, 35.2282, 216.0),
    }
    _zone, transformer = _utm_zone_str(-80.842, 35.228)
    eastings, northings = [], []
    for lon, lat, _alt in gps.values():
        e, n = transformer.transform(lon, lat)
        eastings.append(e)
        northings.append(n)
    origin_e, origin_n = float(np.mean(eastings)), float(np.mean(northings))
    targets = np.column_stack(
        [np.array(eastings) - origin_e, np.array(northings) - origin_n,
         [alt for *_p, alt in gps.values()]]
    )

    # Apply a known inverse similarity to get COLMAP-world camera centres.
    scale_true = 0.5
    rot_true = _random_rotation(7)
    trans_true = np.array([3.0, -4.0, 1.0])
    centres_arr = (targets - trans_true) @ rot_true / scale_true  # inverse of s R x + t
    centres = {name: centres_arr[i] for i, name in enumerate(gps)}

    colmap_dir = tmp_path / "colmap"
    sparse_dir = colmap_dir / "sparse" / "0"
    _write_sparse_model(sparse_dir, centres)
    images = [_image(name, lon, lat, alt) for name, (lon, lat, alt) in gps.items()]

    geo = compute_geo_transform(colmap_dir, sparse_dir, images)
    assert geo is not None
    assert geo["scale"] == pytest.approx(scale_true, rel=1e-6)
    np.testing.assert_allclose(geo["rotation"], rot_true, atol=1e-6)


def test_compute_geo_transform_too_few_gps_returns_none_no_file(tmp_path):
    gps = {"f1.jpg": (-80.843, 35.227, 210.0), "f2.jpg": (-80.842, 35.227, 212.0)}
    _zone, transformer = _utm_zone_str(-80.8425, 35.227)
    centres = {}
    es, ns = [], []
    for lon, lat, _a in gps.values():
        e, n = transformer.transform(lon, lat)
        es.append(e)
        ns.append(n)
    oe, on = float(np.mean(es)), float(np.mean(ns))
    for (name, (_lon, _lat, alt)), e, n in zip(gps.items(), es, ns, strict=True):
        centres[name] = np.array([e - oe, n - on, alt])

    colmap_dir = tmp_path / "colmap"
    sparse_dir = colmap_dir / "sparse" / "0"
    _write_sparse_model(sparse_dir, centres)
    images = [_image(name, lon, lat, alt) for name, (lon, lat, alt) in gps.items()]

    assert compute_geo_transform(colmap_dir, sparse_dir, images) is None
    assert not (colmap_dir / "geo_transform.json").exists()


def test_compute_geo_transform_missing_altitude_excluded(tmp_path):
    # Two of three frames lack altitude -> only one usable correspondence -> None.
    colmap_dir = tmp_path / "colmap"
    sparse_dir = colmap_dir / "sparse" / "0"
    _write_sparse_model(
        sparse_dir,
        {
            "a.jpg": np.array([0.0, 0.0, 0.0]),
            "b.jpg": np.array([10.0, 0.0, 1.0]),
            "c.jpg": np.array([0.0, 10.0, 2.0]),
        },
    )
    images = [
        _image("a.jpg", -80.84, 35.22, 210.0),
        _image("b.jpg", -80.83, 35.22, None),
        _image("c.jpg", -80.84, 35.23, None),
    ]
    assert compute_geo_transform(colmap_dir, sparse_dir, images) is None


def test_compute_geo_transform_missing_model_returns_none(tmp_path):
    colmap_dir = tmp_path / "colmap"
    sparse_dir = colmap_dir / "sparse" / "0"  # never created
    images = [_image("a.jpg", -80.84, 35.22, 210.0)]
    assert compute_geo_transform(colmap_dir, sparse_dir, images) is None


def test_camera_center_recovers_position():
    # tvec = -R @ C  =>  camera_center = -R^T tvec = C
    rot = _random_rotation(9)
    centre = np.array([3.0, -7.0, 2.0])
    tvec = -rot @ centre
    qvec = _rotmat_to_qvec(rot)
    image = colmap_io.ColmapImage(image_id=1, qvec=qvec, tvec=tvec, camera_id=1, name="x.jpg")
    np.testing.assert_allclose(colmap_io.camera_center(image), centre, atol=1e-9)


def _rotmat_to_qvec(rot: np.ndarray) -> np.ndarray:
    trace = np.trace(rot)
    w = np.sqrt(max(0.0, 1.0 + trace)) / 2.0
    x = (rot[2, 1] - rot[1, 2]) / (4 * w)
    y = (rot[0, 2] - rot[2, 0]) / (4 * w)
    z = (rot[1, 0] - rot[0, 1]) / (4 * w)
    return np.array([w, x, y, z])
