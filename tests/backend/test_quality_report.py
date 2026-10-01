"""Tests for backend/services/quality_report.py — scorecard, GCP accuracy,
and held-out checkpoint validation with deterministic math.
"""

from __future__ import annotations

import json
import logging
import math
import struct
import sys
import types
from types import SimpleNamespace

import numpy as np
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
    assert result["status"] == "unavailable"
    assert "reason" in result


class _FakeRecWithMesh:
    mesh_glb_path = None
    splat_path = None
    pointcloud_path = None

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
#  Surface extraction failures (#951)
# ---------------------------------------------------------------------------

_ORIGIN = [SurveyedPoint("A", 0.0, 0.0, 0.0)]
_TRIANGLE = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)]


def _surface_rec(*, mesh=None, splat=None, pointcloud=None):
    return SimpleNamespace(
        mesh_glb_path=str(mesh) if mesh else None,
        splat_path=str(splat) if splat else None,
        pointcloud_path=str(pointcloud) if pointcloud else None,
    )


def _glb(gltf: dict | bytes, bin_chunk: bytes | None = None) -> bytes:
    """Assemble a GLB container from a JSON document and an optional BIN chunk."""
    json_bytes = gltf if isinstance(gltf, bytes) else json.dumps(gltf).encode()
    json_bytes += b" " * (-len(json_bytes) % 4)
    body = struct.pack("<I4s", len(json_bytes), b"JSON") + json_bytes
    if bin_chunk is not None:
        bin_chunk += b"\x00" * (-len(bin_chunk) % 4)
        body += struct.pack("<I4s", len(bin_chunk), b"BIN\x00") + bin_chunk
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def _positions_gltf(
    count: int,
    byte_length: int,
    *,
    byte_stride: int | None = None,
    accessor_offset: int = 0,
    component_type: int = 5126,
) -> dict:
    view: dict = {"buffer": 0, "byteOffset": 0, "byteLength": byte_length}
    if byte_stride is not None:
        view["byteStride"] = byte_stride
    return {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": byte_length}],
        "bufferViews": [view],
        "accessors": [
            {
                "bufferView": 0,
                "byteOffset": accessor_offset,
                "componentType": component_type,
                "count": count,
                "type": "VEC3",
            }
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
    }


def _triangle_glb() -> bytes:
    vertices = b"".join(struct.pack("<3f", *v) for v in _TRIANGLE)
    return _glb(_positions_gltf(len(_TRIANGLE), len(vertices)), vertices)


@pytest.fixture
def surface_warnings():
    """Capture WARNING records from the quality-report logger.

    A handler on the module logger itself keeps the capture independent of how
    the ``backend`` logger's propagation was left by earlier tests.
    """
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture(level=logging.WARNING)
    logger = logging.getLogger("backend.services.quality_report")
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)


def _assert_failed_check(result: dict, source: str, expected_error: str, tmp_path) -> None:
    assert result["available"] is False
    assert result["status"] == "failed"
    assert result["source"] == source
    assert expected_error in result["error"]
    assert result["error"] in result["reason"]
    assert "No surface source" not in result["reason"]
    # The reason is returned to API clients: name the file, not its server path.
    assert str(tmp_path) not in result["reason"]


def test_validate_checkpoints_reads_glb_mesh_positions(tmp_path):
    mesh = tmp_path / "mesh.glb"
    mesh.write_bytes(_triangle_glb())

    result = validate_held_out_checkpoints(
        _surface_rec(mesh=mesh), [SurveyedPoint("P", 10.0, 0.0, 1.0)]
    )

    assert result["available"] is True
    assert result["source"] == "mesh"
    assert result["surface_point_count"] == 3
    assert result["checkpoints"][0]["distance_m"] == pytest.approx(1.0)
    assert result["checkpoints"][0]["nearest_surface_point"] == "10.0000,0.0000,0.0000"


def test_validate_checkpoints_honours_interleaved_glb_positions(tmp_path):
    # Each vertex is NORMAL then POSITION (24-byte stride); POSITION starts 12 bytes in.
    data = b"".join(struct.pack("<6f", 0.0, 0.0, 1.0, *v) for v in _TRIANGLE)
    mesh = tmp_path / "mesh.glb"
    mesh.write_bytes(
        _glb(_positions_gltf(3, len(data), byte_stride=24, accessor_offset=12), data)
    )

    result = validate_held_out_checkpoints(
        _surface_rec(mesh=mesh), [SurveyedPoint("P", 0.0, 10.0, 0.0)]
    )

    assert result["available"] is True
    assert result["surface_point_count"] == 3
    assert result["checkpoints"][0]["distance_m"] == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        pytest.param(b"PK\x03\x04 this is a zip, not a mesh", "glTF magic", id="not-glb"),
        pytest.param(b"glTF\x02\x00\x00\x00", "truncated", id="truncated-header"),
        pytest.param(_glb(b"{not json"), "JSON", id="corrupt-json-chunk"),
        pytest.param(_glb(_positions_gltf(3, 36)), "BIN chunk", id="missing-bin-chunk"),
        pytest.param(
            _glb(_positions_gltf(3, 36), b"\x00" * 12), "truncated", id="truncated-buffer"
        ),
        pytest.param(
            _glb(_positions_gltf(3, 18, component_type=5123), b"\x00" * 20),
            "componentType 5123",
            id="unsupported-accessor",
        ),
    ],
)
def test_validate_checkpoints_corrupt_glb_fails_with_parser_error(
    tmp_path, surface_warnings, payload, expected_error
):
    mesh = tmp_path / "mesh.glb"
    mesh.write_bytes(payload)

    result = validate_held_out_checkpoints(_surface_rec(mesh=mesh), _ORIGIN)

    _assert_failed_check(result, "mesh", expected_error, tmp_path)
    assert "mesh.glb" in result["reason"]
    assert any(record.exc_info for record in surface_warnings), (
        "a surface extraction failure must be logged with its traceback"
    )


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(_glb({"asset": {"version": "2.0"}}), id="no-meshes"),
        pytest.param(_glb(_positions_gltf(0, 0), b""), id="zero-vertices"),
    ],
)
def test_validate_checkpoints_glb_without_vertices_is_empty_not_failed(
    tmp_path, surface_warnings, payload
):
    mesh = tmp_path / "mesh.glb"
    mesh.write_bytes(payload)

    result = validate_held_out_checkpoints(_surface_rec(mesh=mesh), _ORIGIN)

    assert result["available"] is False
    assert result["status"] == "empty"
    assert result["source"] == "mesh"
    assert "contains no points" in result["reason"]
    assert "error" not in result
    assert not surface_warnings


def test_validate_checkpoints_corrupt_splat_fails_with_reader_error(tmp_path, surface_warnings):
    splat = tmp_path / "splat.ply"
    splat.write_bytes(b"ply\nformat ascii 1.0\nelement vertex 0\nend_header\n")

    result = validate_held_out_checkpoints(_surface_rec(splat=splat), _ORIGIN)

    _assert_failed_check(result, "splat", "binary_little_endian", tmp_path)
    assert any(record.exc_info for record in surface_warnings)


def test_validate_checkpoints_pointcloud_without_laspy_names_the_install(
    tmp_path, monkeypatch, surface_warnings
):
    cloud = tmp_path / "cloud.las"
    cloud.write_bytes(b"LASF")
    monkeypatch.setitem(sys.modules, "laspy", None)  # import laspy -> ImportError

    result = validate_held_out_checkpoints(_surface_rec(pointcloud=cloud), _ORIGIN)

    _assert_failed_check(result, "pointcloud", "laspy", tmp_path)
    assert "uv sync --group backend --group reconstruction" in result["reason"]
    assert any(record.exc_info for record in surface_warnings)


def _fake_laspy(read) -> types.ModuleType:
    module = types.ModuleType("laspy")
    module.read = read
    return module


def test_validate_checkpoints_corrupt_las_fails_with_reader_error(
    tmp_path, monkeypatch, surface_warnings
):
    cloud = tmp_path / "cloud.las"
    cloud.write_bytes(b"not a las file")

    def _read(path):
        raise RuntimeError(f"Invalid file signature in {path}")

    monkeypatch.setitem(sys.modules, "laspy", _fake_laspy(_read))

    result = validate_held_out_checkpoints(_surface_rec(pointcloud=cloud), _ORIGIN)

    _assert_failed_check(result, "pointcloud", "Invalid file signature", tmp_path)
    assert "cloud.las" in result["error"]
    assert any(record.exc_info for record in surface_warnings)


def test_validate_checkpoints_las_with_zero_points_is_empty_not_failed(
    tmp_path, monkeypatch, surface_warnings
):
    cloud = tmp_path / "cloud.las"
    cloud.write_bytes(b"LASF")
    empty = np.array([], dtype=np.float64)
    monkeypatch.setitem(
        sys.modules, "laspy", _fake_laspy(lambda path: SimpleNamespace(x=empty, y=empty, z=empty))
    )

    result = validate_held_out_checkpoints(_surface_rec(pointcloud=cloud), _ORIGIN)

    assert result["available"] is False
    assert result["status"] == "empty"
    assert result["source"] == "pointcloud"
    assert "error" not in result
    assert not surface_warnings


# ---------------------------------------------------------------------------
#  CheckpointValidation dataclass
# ---------------------------------------------------------------------------


def test_checkpoint_validation_accepts_coordinate_string():
    cv = CheckpointValidation(label="X", distance_m=1.0, surface_point="12.3456,67.8901,0.0000")
    assert cv.surface_point == "12.3456,67.8901,0.0000"


def test_checkpoint_validation_none_source():
    cv = CheckpointValidation(label="X", distance_m=1.0, surface_point=None)
    assert cv.surface_point is None
