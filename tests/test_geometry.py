from __future__ import annotations

import json

import pytest

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
