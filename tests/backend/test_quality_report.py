"""Tests for backend/services/quality_report.py — scorecard, GCP accuracy,
and held-out checkpoint validation with deterministic math.
"""

from __future__ import annotations

import math

import pytest

from backend.services.quality_report import (
    CheckpointValidation,
    SurveyedPoint,
    _rmse,
    build_quality_scorecard,
    compute_gcp_accuracy,
    parse_surveyed_points_3d,
    validate_held_out_checkpoints,
)

# ---------------------------------------------------------------------------
#  _rmse
# ---------------------------------------------------------------------------


def test_rmse_empty():
    assert _rmse([]) == 0.0


def test_rmse_single():
    assert _rmse([5.0]) == pytest.approx(5.0)


def test_rmse_known():
    # RMSE of [3, 4] = sqrt((9+16)/2) = sqrt(12.5) = 3.5355...
    assert _rmse([3.0, 4.0]) == pytest.approx(3.5355339, abs=1e-6)


# ---------------------------------------------------------------------------
#  parse_surveyed_points_3d
# ---------------------------------------------------------------------------


def test_parse_surveyed_points():
    items = [
        {
            "label": "P1",
            "x": 1.0,
            "y": 2.0,
            "z": 3.0,
            "reconstructed_x": 0.5,
            "reconstructed_y": 1.0,
            "reconstructed_z": 1.5,
        },
        {"x": 10.0, "y": 20.0, "z": 30.0},
    ]
    points = parse_surveyed_points_3d(items)
    assert len(points) == 2
    assert points[0].label == "P1"
    assert points[0].x == 1.0
    assert points[0].y == 2.0
    assert points[0].z == 3.0
    assert points[0].reconstructed_x == 0.5
    assert points[1].label == "point_1"  # auto-generated


# ---------------------------------------------------------------------------
#  build_quality_scorecard
# ---------------------------------------------------------------------------


class _FakeRec:
    def __init__(self):
        self.id = 101
        self.frames_used = 10
        self.frames_registered = 8
        self.gaussian_count = 50000
        self.psnr = 32.5
        self.ssim = 0.95


class _FakeFrame:
    def __init__(self, colmap_error_px):
        self.colmap_error_px = colmap_error_px


def test_build_quality_scorecard_minimal():
    rec = _FakeRec()
    frames = [_FakeFrame(1.2), _FakeFrame(0.9), _FakeFrame(1.5), _FakeFrame(None)]
    result = build_quality_scorecard(rec, frames, training_metrics=None, coverage_gaps=None)

    assert result["reconstruction_id"] == 101
    assert result["frame_counts"]["frames_used"] == 10
    assert result["frame_counts"]["frames_registered"] == 8
    assert result["frame_counts"]["registration_completeness_pct"] == 80.0
    assert result["density"]["gaussian_count"] == 50000
    assert result["quality"]["psnr_final"] == 32.5
    assert result["quality"]["ssim_final"] == 0.95
    assert result["reprojection_error"]["mean_px"] == 1.2
    assert result["reprojection_error"]["frame_count_with_data"] == 3
    assert result["reprojection_error"]["min_px"] == 0.9
    assert result["reprojection_error"]["max_px"] == 1.5


def test_build_quality_scorecard_with_training_metrics():
    rec = _FakeRec()
    frames: list = []
    training = [
        {"iter": 0, "psnr": 20.0, "ssim": 0.70},
        {"iter": 100, "psnr": 30.0, "ssim": 0.85},
        {"iter": 200, "psnr": 32.5, "ssim": 0.95},
    ]
    result = build_quality_scorecard(rec, frames, training_metrics=training, coverage_gaps=None)

    assert result["quality"]["training_metric_points"] == 3
    assert result["quality"]["psnr_trend"]["start"] == 20.0
    assert result["quality"]["psnr_trend"]["end"] == 32.5
    assert result["quality"]["psnr_trend"]["delta"] == 12.5


def test_build_quality_scorecard_with_coverage_gaps():
    rec = _FakeRec()
    frames: list = []
    gaps = [
        {"x": 0, "y": 0, "z": 0, "size": 0.5, "level": "sparse"},
        {"x": 1, "y": 1, "z": 1, "size": 0.5, "level": "thin"},
        {"x": 2, "y": 2, "z": 2, "size": 0.5, "level": "sparse"},
    ]
    result = build_quality_scorecard(rec, frames, training_metrics=None, coverage_gaps=gaps)

    assert result["coverage_gaps"] is not None
    assert result["coverage_gaps"]["total_gaps"] == 3
    assert result["coverage_gaps"]["by_level"] == {"sparse": 2, "thin": 1}
    assert result["coverage_gaps"]["voxel_size_m"] == 0.5


# ---------------------------------------------------------------------------
#  compute_gcp_accuracy
# ---------------------------------------------------------------------------

SAMPLE_GEO_TRANSFORM = {
    "scale": 1.0,
    "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    "translation": [500000.0, 4500000.0, 100.0],
    "utm_zone": "17N",
    "utm_origin": [0.0, 0.0],
}


def test_gcp_accuracy_uses_paired_reconstructed_coordinates():
    points = [
        SurveyedPoint("A", 100.0, 200.0, 50.0, 100.0, 200.0, 50.0),
        SurveyedPoint("B", 103.0, 204.0, 50.0, 100.0, 200.0, 50.0),
    ]
    result = compute_gcp_accuracy(SAMPLE_GEO_TRANSFORM, points)

    assert result["point_count"] == 2
    assert result["residuals"][0]["distance_3d_m"] == 0.0
    assert result["residuals"][1]["dx_m"] == 3.0
    assert result["residuals"][1]["dy_m"] == 4.0
    assert result["residuals"][1]["distance_3d_m"] == 5.0
    assert result["rmse"]["x_m"] == pytest.approx(math.sqrt((0 + 9) / 2), abs=1e-4)
    assert result["rmse"]["3d_m"] == pytest.approx(math.sqrt((0 + 25) / 2), abs=1e-4)


def test_gcp_accuracy_rejects_unpaired_points():
    points = [SurveyedPoint("A", 1.0, 2.0, 3.0)]
    with pytest.raises(ValueError, match="paired reconstructed"):
        compute_gcp_accuracy(SAMPLE_GEO_TRANSFORM, points)


# ---------------------------------------------------------------------------
#  Held-out checkpoint validation (unit tests)
# ---------------------------------------------------------------------------


def test_validate_checkpoints_no_surface_available():
    """When no mesh/splat/pointcloud exists, returns available=False."""

    class _NoArtifacts:
        mesh_glb_path = None
        splat_path = None
        pointcloud_path = None

    points = [SurveyedPoint("A", 0.0, 0.0, 0.0)]
    result = validate_held_out_checkpoints(_NoArtifacts(), points)
    assert result["available"] is False
    assert "reason" in result


class _FakeRecWithMesh:
    mesh_glb_path = None
    splat_path = None
    pointcloud_path = None
    # Georeferenced with the identity similarity, so UTM coordinates equal COLMAP ones.
    geo_transform = (
        '{"scale": 1.0, "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],'
        ' "translation": [0, 0, 0], "utm_zone": "33N", "utm_origin": [0, 0]}'
    )

    def __init__(self, path):
        self.splat_path = str(path)


def test_validate_checkpoints_with_splat(tmp_path):
    """With a simple splat, returns distances to nearest Gaussian."""
    import numpy as np

    from backend.services import ply_io

    splat_file = tmp_path / "test.ply"
    rec = _FakeRecWithMesh(str(splat_file))

    means = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]], dtype=np.float32)
    # Build a minimal GaussianCloud
    n = 3
    cloud = ply_io.GaussianCloud(
        means=means,
        sh0=np.zeros((n, 3), dtype=np.float32),
        shN=np.zeros((n, 0, 3), dtype=np.float32),
        opacities=np.zeros(n, dtype=np.float32),
        scales=np.zeros((n, 3), dtype=np.float32),
        quats=np.zeros((n, 4), dtype=np.float32),
    )
    ply_io.write_3dgs_ply(splat_file, cloud)

    points = [SurveyedPoint("P", 0.0, 0.0, 0.0), SurveyedPoint("Q", 10.0, 0.0, 0.0)]
    result = validate_held_out_checkpoints(rec, points)

    assert result["available"] is True
    assert result["source"] == "splat"
    assert result["point_count"] == 2
    assert len(result["checkpoints"]) == 2
    # P should be very close to (0,0,0)
    assert result["checkpoints"][0]["distance_m"] == pytest.approx(0.0, abs=1e-4)
    # Q should be close to (10,0,0)
    assert result["checkpoints"][1]["distance_m"] == pytest.approx(0.0, abs=1e-4)
    assert result["summary"]["rmse_m"] == pytest.approx(0.0, abs=1e-4)


# ---------------------------------------------------------------------------
#  CheckpointValidation dataclass
# ---------------------------------------------------------------------------


def test_checkpoint_validation_accepts_coordinate_string():
    cv = CheckpointValidation(label="X", distance_m=1.0, surface_point="12.3456,67.8901,0.0000")
    assert cv.surface_point == "12.3456,67.8901,0.0000"


def test_checkpoint_validation_none_source():
    cv = CheckpointValidation(label="X", distance_m=1.0, surface_point=None)
    assert cv.surface_point is None


# ---------------------------------------------------------------------------
#  Checkpoint frame (#950): surveyed UTM checkpoints vs COLMAP-frame surfaces
# ---------------------------------------------------------------------------

# COLMAP-frame surface vertices, all exactly representable in float32.
_SURFACE_COLMAP = [(0.0, 0.0, 0.0), (4.0, -2.0, 1.5), (-6.0, 3.0, 0.25)]


def _checkpoint_geo() -> dict:
    """A solved COLMAP->UTM 33N similarity: yawed, tilted, scaled 2.5x and translated."""
    import numpy as np

    a, b = math.radians(40.0), math.radians(15.0)
    rz = [[math.cos(a), -math.sin(a), 0.0], [math.sin(a), math.cos(a), 0.0], [0.0, 0.0, 1.0]]
    rx = [[1.0, 0.0, 0.0], [0.0, math.cos(b), -math.sin(b)], [0.0, math.sin(b), math.cos(b)]]
    return {
        "scale": 2.5,
        "rotation": (np.array(rz) @ np.array(rx)).tolist(),
        "translation": [3.0, -7.0, 12.0],
        "utm_zone": "33N",
        "utm_origin": [650123.0, 4649776.0],
    }


def _utm_of(geo: dict, point) -> tuple[float, float, float]:
    """Where a COLMAP point is in absolute UTM, computed without the service."""
    import numpy as np

    local = geo["scale"] * (np.array(geo["rotation"]) @ np.array(point)) + geo["translation"]
    return (
        float(local[0] + geo["utm_origin"][0]),
        float(local[1] + geo["utm_origin"][1]),
        float(local[2]),
    )


def _georef_rec(geo: dict | None, **paths):
    import json
    from types import SimpleNamespace

    return SimpleNamespace(
        id=7,
        geo_transform=json.dumps(geo) if geo is not None else None,
        mesh_glb_path=str(paths["mesh"]) if paths.get("mesh") else None,
        splat_path=str(paths["splat"]) if paths.get("splat") else None,
        pointcloud_path=str(paths["pointcloud"]) if paths.get("pointcloud") else None,
    )


def _write_splat(path, points) -> None:
    import numpy as np

    from backend.services import ply_io

    n = len(points)
    ply_io.write_3dgs_ply(
        path,
        ply_io.GaussianCloud(
            means=np.array(points, dtype=np.float32),
            sh0=np.zeros((n, 3), dtype=np.float32),
            shN=np.zeros((n, 0, 3), dtype=np.float32),
            opacities=np.zeros(n, dtype=np.float32),
            scales=np.zeros((n, 3), dtype=np.float32),
            quats=np.zeros((n, 4), dtype=np.float32),
        ),
    )


def _write_glb(path, vertices) -> None:
    """A minimal single-primitive GLB whose POSITION accessor holds *vertices*."""
    import json
    import struct

    bin_chunk = b"".join(struct.pack("<3f", *v) for v in vertices)
    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(bin_chunk)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(bin_chunk)}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(vertices), "type": "VEC3"}
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
    }
    json_bytes = json.dumps(gltf).encode()
    json_bytes += b" " * (-len(json_bytes) % 4)
    body = struct.pack("<I4s", len(json_bytes), b"JSON") + json_bytes
    body += struct.pack("<I4s", len(bin_chunk), b"BIN\x00") + bin_chunk
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)


def _offset(point, dx=0.0, dy=0.0, dz=0.0) -> SurveyedPoint:
    return SurveyedPoint("CP", point[0] + dx, point[1] + dy, point[2] + dz)


@pytest.mark.parametrize("source", ["splat", "mesh"])
def test_validate_checkpoints_maps_colmap_surfaces_into_the_utm_checkpoint_frame(
    tmp_path, source
):
    geo = _checkpoint_geo()
    if source == "splat":
        path = tmp_path / "splat.ply"
        _write_splat(path, _SURFACE_COLMAP)
    else:
        path = tmp_path / "mesh.glb"
        _write_glb(path, _SURFACE_COLMAP)
    on_surface = _utm_of(geo, _SURFACE_COLMAP[1])
    # Checkpoints are surveyed in UTM; 1 m off must read as 1 m whatever COLMAP's scale.
    checkpoints = [
        SurveyedPoint("ON", *on_surface),
        _offset(_utm_of(geo, _SURFACE_COLMAP[2]), dz=1.0),
        _offset(_utm_of(geo, _SURFACE_COLMAP[0]), dx=0.6, dy=-0.8),
    ]

    result = validate_held_out_checkpoints(_georef_rec(geo, **{source: path}), checkpoints)

    assert result["available"] is True
    assert result["source"] == source
    assert result["frame"]["crs"] == "EPSG:32633"
    assert result["frame"]["utm_zone"] == "33N"
    distances = [c["distance_m"] for c in result["checkpoints"]]
    assert distances == pytest.approx([0.0, 1.0, 1.0], abs=1e-3)
    easting, northing, height = (
        float(v) for v in result["checkpoints"][0]["nearest_surface_point"].split(",")
    )
    assert (easting, northing, height) == pytest.approx(on_surface, abs=1e-3)


def test_validate_checkpoints_uses_the_utm_point_cloud_as_is(tmp_path, monkeypatch):
    """The LAS export is already written in UTM; mapping it again would misplace it."""
    from backend.services import quality_report

    geo = _checkpoint_geo()
    cloud = tmp_path / "pointcloud.las"
    cloud.write_bytes(b"LASF")
    utm_points = [_utm_of(geo, p) for p in _SURFACE_COLMAP]
    monkeypatch.setattr(
        quality_report, "_extract_pointcloud_surface_points", lambda path: list(utm_points)
    )

    result = validate_held_out_checkpoints(
        _georef_rec(geo, pointcloud=cloud), [_offset(utm_points[1], dx=1.0)]
    )

    assert result["available"] is True
    assert result["source"] == "pointcloud"
    assert result["checkpoints"][0]["distance_m"] == pytest.approx(1.0, abs=1e-3)


def test_validate_checkpoints_refuses_a_reconstruction_that_is_not_georeferenced(tmp_path):
    splat = tmp_path / "splat.ply"
    _write_splat(splat, _SURFACE_COLMAP)

    result = validate_held_out_checkpoints(
        _georef_rec(None, splat=splat), [SurveyedPoint("CP", 0.0, 0.0, 0.0)]
    )

    assert result["available"] is False
    assert result["status"] == "not_georeferenced"
    assert "not georeferenced" in result["reason"]
    assert "checkpoints" not in result
