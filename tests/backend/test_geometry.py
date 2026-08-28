from __future__ import annotations

import json

import pytest
from pyproj import Geod

from backend.services.geometry import compute_footprint

TARGET_CRS = "EPSG:32617"
LAT, LON = 41.153, -81.341
ALT_M = 60.96
FOV_H, FOV_V = 83, 53


def test_footprint_returns_required_keys():
    result = compute_footprint(LAT, LON, ALT_M, FOV_H, FOV_V, None, TARGET_CRS)
    expected_keys = [
        "geom_wkt", "geom_geojson", "ground_width_m", "ground_height_m", "heading_estimated"
    ]
    for key in expected_keys:
        assert key in result


def test_footprint_ground_dimensions_at_200ft():
    result = compute_footprint(LAT, LON, ALT_M, FOV_H, FOV_V, None, TARGET_CRS)
    assert result["ground_width_m"] == pytest.approx(107.5, abs=2.0)
    # 2 * 60.96 * tan(26.5°) ≈ 60.8 m
    assert result["ground_height_m"] == pytest.approx(60.8, abs=2.0)


def test_footprint_no_yaw_is_estimated():
    result = compute_footprint(LAT, LON, ALT_M, FOV_H, FOV_V, None, TARGET_CRS)
    assert result["heading_estimated"] is True


def test_footprint_with_yaw_not_estimated():
    result = compute_footprint(LAT, LON, ALT_M, FOV_H, FOV_V, 45.0, TARGET_CRS)
    assert result["heading_estimated"] is False


def test_footprint_geojson_is_polygon():
    result = compute_footprint(LAT, LON, ALT_M, FOV_H, FOV_V, None, TARGET_CRS)
    geojson = json.loads(result["geom_geojson"])
    assert geojson["type"] == "Polygon"
    assert len(geojson["coordinates"][0]) == 5


def test_footprint_center_near_input_coords():
    result = compute_footprint(LAT, LON, ALT_M, FOV_H, FOV_V, None, TARGET_CRS)
    geojson = json.loads(result["geom_geojson"])
    coords = geojson["coordinates"][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    centroid_lon = sum(lons) / len(lons)
    centroid_lat = sum(lats) / len(lats)
    assert abs(centroid_lat - LAT) < 0.001
    assert abs(centroid_lon - LON) < 0.001


def _ground_width_m(result: dict) -> float:
    """Real-world distance along the polygon's bottom edge, from the WGS84 output."""
    coords = json.loads(result["geom_geojson"])["coordinates"][0]
    (lon_a, lat_a), (lon_b, lat_b) = coords[0], coords[1]
    return Geod(ellps="WGS84").inv(lon_a, lat_a, lon_b, lat_b)[2]


def test_footprint_outside_configured_zone_matches_ground_width():
    """A flight far from the configured zone must not be inflated by it (#640)."""
    # Denver (105°W) with the shipped default EPSG:32617 (central meridian 81°W).
    result = compute_footprint(39.74, -104.99, ALT_M, FOV_H, FOV_V, None, TARGET_CRS)
    assert _ground_width_m(result) == pytest.approx(result["ground_width_m"], rel=0.005)


def test_footprint_inside_configured_zone_still_uses_it():
    """An explicit target_crs that does cover the flight is still honoured (#640)."""
    result = compute_footprint(LAT, LON, ALT_M, FOV_H, FOV_V, None, TARGET_CRS)
    assert _ground_width_m(result) == pytest.approx(result["ground_width_m"], rel=0.005)


def test_footprint_without_target_crs_derives_zone():
    """target_crs is optional; the local UTM zone is derived from lat/lon (#640)."""
    result = compute_footprint(39.74, -104.99, ALT_M, FOV_H, FOV_V, None)
    assert _ground_width_m(result) == pytest.approx(result["ground_width_m"], rel=0.005)


# ---------------------------------------------------------------------------
# Terrain-aware footprint tests (ground_elevation_m parameter)
# ---------------------------------------------------------------------------


class TestFootprintWithGroundElevation:
    """Footprint dimensions shrink when ground elevation is subtracted from MSL altitude."""

    def test_high_ground_reduces_agl_and_footprint(self):
        # Drone at 100 m MSL, ground at 50 m → AGL = 50 m
        result_flat = compute_footprint(LAT, LON, 100.0, FOV_H, FOV_V, None, TARGET_CRS)
        result_high = compute_footprint(
            LAT, LON, 100.0, FOV_H, FOV_V, None, TARGET_CRS, ground_elevation_m=50.0
        )
        # High ground → smaller footprint
        assert result_high["ground_width_m"] < result_flat["ground_width_m"]
        assert result_high["ground_height_m"] < result_flat["ground_height_m"]

    def test_zero_ground_elevation_is_noop(self):
        result_default = compute_footprint(
            LAT, LON, ALT_M, FOV_H, FOV_V, None, TARGET_CRS
        )
        result_explicit = compute_footprint(
            LAT, LON, ALT_M, FOV_H, FOV_V, None, TARGET_CRS, ground_elevation_m=0.0
        )
        assert result_default["ground_width_m"] == pytest.approx(
            result_explicit["ground_width_m"]
        )
        assert result_default["ground_height_m"] == pytest.approx(
            result_explicit["ground_height_m"]
        )

    def test_negative_ground_clamped_to_1m_agl(self):
        # Drone at 50 m MSL, ground at 100 m (drone below terrain) — clamp to 1 m AGL
        result = compute_footprint(
            LAT, LON, 50.0, FOV_H, FOV_V, None, TARGET_CRS, ground_elevation_m=100.0
        )
        # With AGL clamped to 1 m, footprint should be very small
        assert result["ground_width_m"] < 5.0
        assert result["ground_height_m"] < 5.0

    def test_oblique_with_ground_elevation(self):
        """Oblique footprint also uses AGL altitude accounting for ground elevation."""
        result_flat = compute_footprint(
            LAT, LON, 100.0, FOV_H, FOV_V, 45.0, TARGET_CRS, gimbal_pitch=-60
        )
        result_high = compute_footprint(
            LAT, LON, 100.0, FOV_H, FOV_V, 45.0, TARGET_CRS,
            gimbal_pitch=-60, ground_elevation_m=30.0
        )
        assert result_high["ground_width_m"] < result_flat["ground_width_m"]
        assert result_high["ground_height_m"] < result_flat["ground_height_m"]
        # Both should still be flagged as oblique
        assert result_high["pitch_oblique"] is True
        assert result_flat["pitch_oblique"] is True