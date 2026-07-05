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
        {"label": "P1", "x": 1.0, "y": 2.0, "z": 3.0},
        {"x": 10.0, "y": 20.0, "z": 30.0},
    ]
    points = parse_surveyed_points_3d(items)
    assert len(points) == 2
    assert points[0].label == "P1"
    assert points[0].x == 1.0
    assert points[0].y == 2.0
    assert points[0].z == 3.0
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


def test_gcp_accuracy_identity_transform():
    """With scale=1 and translation at origin, residuals are just point coordinates."""
    points = [
        SurveyedPoint("A", 0.0, 0.0, 0.0),
        SurveyedPoint("B", 3.0, 4.0, 0.0),
    ]
    result = compute_gcp_accuracy({"scale": 1.0, "translation": [0.0, 0.0, 0.0]}, points)

    assert result["point_count"] == 2
    assert result["rmse"]["x_m"] == pytest.approx(math.sqrt((0 + 9) / 2), abs=1e-4)
    assert result["rmse"]["y_m"] == pytest.approx(math.sqrt((0 + 16) / 2), abs=1e-4)
    assert result["rmse"]["3d_m"] == pytest.approx(math.sqrt((0 + 25) / 2), abs=1e-4)
    # B distance: 5.0
    assert result["residuals"][1]["distance_3d_m"] == 5.0


def test_gcp_accuracy_with_translation():
    """Points close to translation should have small residuals."""
    tx, ty, tz = 500_000.0, 4_500_000.0, 100.0
    geo = {"scale": 1.0, "translation": [tx, ty, tz]}
    # A point at exactly the translation
    points = [
        SurveyedPoint("at_origin", tx, ty, tz),
        SurveyedPoint("offset", tx + 1.5, ty + 2.0, tz - 0.5),
    ]
    result = compute_gcp_accuracy(geo, points)

    # At origin: dx = tx - tx = 0
    assert result["residuals"][0]["dx_m"] == 0.0
    assert result["residuals"][0]["dy_m"] == 0.0
    assert result["residuals"][0]["dz_m"] == 0.0

    # Offset: dx = (tx+1.5) - tx = 1.5
    assert result["residuals"][1]["dx_m"] == 1.5
    assert result["residuals"][1]["dy_m"] == 2.0
    assert result["residuals"][1]["dz_m"] == -0.5

    rmse_x = math.sqrt((0 + 1.5**2) / 2)
    rmse_y = math.sqrt((0 + 2.0**2) / 2)
    assert result["rmse"]["x_m"] == pytest.approx(rmse_x, abs=1e-4)
    assert result["rmse"]["y_m"] == pytest.approx(rmse_y, abs=1e-4)


def test_gcp_accuracy_with_scale():
    """Scale > 1 reduces local residuals proportionally."""
    geo = {"scale": 2.0, "translation": [0.0, 0.0, 0.0]}
    points = [
        SurveyedPoint("P", 10.0, 10.0, 0.0),
    ]
    result = compute_gcp_accuracy(geo, points)
    # Expected: translation divided by scale = 0.0, so dx = 10.0 - 0 = 10.0
    assert result["residuals"][0]["dx_m"] == 10.0
    # rmse_x = 10.0
    assert result["rmse"]["x_m"] == 10.0


def test_gcp_accuracy_3d_distance():
    geo = {"scale": 1.0, "translation": [100.0, 200.0, 50.0]}
    points = [
        SurveyedPoint("P", 100.0, 200.0, 50.0),   # 0.0 distance
        SurveyedPoint("Q", 103.0, 204.0, 50.0),   # 3-4-0 → 5.0
    ]
    result = compute_gcp_accuracy(geo, points)
    assert result["residuals"][0]["distance_3d_m"] == 0.0
    assert result["residuals"][1]["distance_3d_m"] == 5.0


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

    def __init__(self, path):
        self.splat_path = str(path)


def test_validate_checkpoints_with_splat(tmp_path):
    """With a simple splat, returns distances to nearest Gaussian."""
    import numpy as np

    from backend.services import ply_io

    splat_file = tmp_path / "test.ply"
    rec = _FakeRecWithMesh(str(splat_file))

    means = np.array(
        [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]], dtype=np.float32
    )
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