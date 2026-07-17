from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services.camera_calibration import (
    build_calibration_drift_report,
    calibration_profile_for_images,
    dimension_fov_warnings,
    focal_pixels_from_metadata,
    match_camera_profile,
    normalize_profiles,
    suggest_colmap_camera_model,
)


def _camera(camera_id, params):
    return SimpleNamespace(
        camera_id=camera_id, model="PINHOLE", width=2000, height=1000, params=params
    )


def test_calibration_drift_report_is_stable_for_close_colmap_estimates():
    report = build_calibration_drift_report(
        [_camera(1, [1000, 1000, 1000, 500]), _camera(2, [1005, 1005, 1001, 500])]
    )

    assert report["available"] is True
    assert report["status"] == "stable"
    assert report["metrics"]["focal_length_relative_range_pct"] < 1.0


def test_calibration_drift_report_flags_divergent_colmap_estimates():
    report = build_calibration_drift_report(
        [_camera(1, [1000, 1000, 1000, 500]), _camera(2, [1040, 1040, 1010, 500])]
    )

    assert report["status"] == "unstable"
    assert report["metrics"]["focal_length_relative_range_pct"] > 1.0


def test_calibration_drift_report_is_unavailable_without_multiple_estimates():
    report = build_calibration_drift_report([_camera(1, [1000, 1000, 1000, 500])])

    assert report["available"] is False
    assert report["status"] == "unavailable"
    assert "two COLMAP camera estimates" in report["reason"]


def test_match_camera_profile_by_make_model_and_lens():
    image = SimpleNamespace(camera_make="DJI", camera_model="FC3582", lens_model="24mm F1.7")
    profiles = [
        {"name": "other", "make": "DJI", "model": "FC3411"},
        {"name": "mini", "make": "DJI", "model": "FC3582", "lens_model": "24mm"},
    ]

    match = match_camera_profile(image, profiles)
    assert match is not None
    assert match["name"] == "mini"


def test_suggest_colmap_camera_model_prefers_profile_then_lens_hint():
    image = SimpleNamespace(
        camera_model="ActionCam",
        lens_model="wide fisheye",
        focal_length_mm=None,
    )

    assert suggest_colmap_camera_model(image, {"colmap_camera_model": "opencv"}) == "OPENCV"
    assert suggest_colmap_camera_model(image, None) == "SIMPLE_RADIAL"


def test_focal_pixels_uses_exif_focal_length_and_profile_sensor_width():
    image = SimpleNamespace(width=4000, focal_length_mm=6.72)
    profile = {"sensor_width_mm": 6.4, "fov_horizontal_deg": 73.4}

    assert focal_pixels_from_metadata(image, profile, 83) == pytest.approx(4200.0)


def test_dimension_fov_warnings_report_config_mismatches():
    images = [SimpleNamespace(width=5280, height=3956), SimpleNamespace(width=5200, height=3900)]
    warnings = dimension_fov_warnings(
        images,
        configured_width=4000,
        configured_height=3000,
        configured_fov_horizontal_deg=83,
        configured_fov_vertical_deg=53,
        profile={"fov_horizontal_deg": 70.0, "fov_vertical_deg": 40.0},
    )

    assert any("mixed dimensions" in warning for warning in warnings)
    assert any("does not match imported images" in warning for warning in warnings)
    assert any("horizontal FOV" in warning for warning in warnings)
    assert any("vertical FOV" in warning for warning in warnings)


def test_calibration_profile_for_images_summarizes_suggestion_and_warnings():
    image = SimpleNamespace(
        width=5280,
        height=3956,
        camera_make="DJI",
        camera_model="FC3582",
        lens_model="24mm F1.7",
        focal_length_mm=6.72,
    )
    profiles = [
        {
            "name": "mini",
            "make": "DJI",
            "model": "FC3582",
            "sensor_width_mm": 6.4,
            "fov_horizontal_deg": 73.4,
            "fov_vertical_deg": 52.2,
            "colmap_camera_model": "PINHOLE",
        }
    ]

    summary = calibration_profile_for_images(
        [image],
        profiles,
        4000,
        3000,
        83,
        53,
        "SIMPLE_PINHOLE",
    )

    assert summary["profile"]["name"] == "mini"
    assert summary["suggested_colmap_camera_model"] == "PINHOLE"
    assert summary["width"] == 5280
    assert summary["height"] == 3956
    assert summary["focal_px"] == pytest.approx(5544.0)
    assert any("Configured image size" in warning for warning in summary["warnings"])


def test_normalize_profiles_falls_back_to_defaults_for_invalid_input():
    assert normalize_profiles(None)
    assert normalize_profiles([{"make": "DJI", "model": "FC0000"}]) == [
        {"name": "DJI FC0000", "make": "DJI", "model": "FC0000"}
    ]
