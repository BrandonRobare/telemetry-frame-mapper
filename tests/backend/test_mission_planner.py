from __future__ import annotations

import math

import pytest

from backend.services.mission_planner import generate_lawnmower

_POLY = (
    '{"type":"Polygon","coordinates":'
    '[[[-80.5,35.0],[-80.4,35.0],[-80.4,35.1],[-80.5,35.1],[-80.5,35.0]]]}'
)


def test_waypoint_spacing_present():
    result = generate_lawnmower(
        target_geojson=_POLY,
        altitude_ft=200,
        side_overlap=0.7,
        forward_overlap=0.8,
        fov_h_deg=84.0,
        fov_v_deg=64.0,
    )
    assert "waypoint_spacing_m" in result
    assert result["waypoint_spacing_m"] > 0


def test_waypoint_spacing_value():
    result = generate_lawnmower(
        target_geojson=_POLY,
        altitude_ft=200,
        side_overlap=0.7,
        forward_overlap=0.8,
        fov_h_deg=84.0,
        fov_v_deg=64.0,
    )
    altitude_m = 200 * 0.3048
    ground_height_m = 2 * altitude_m * math.tan(math.radians(64.0 / 2))
    expected = round(ground_height_m * (1 - 0.8), 2)
    assert abs(result["waypoint_spacing_m"] - expected) < 0.01


def test_higher_overlap_gives_shorter_spacing():
    r_low = generate_lawnmower(
        target_geojson=_POLY,
        altitude_ft=200,
        side_overlap=0.7,
        forward_overlap=0.6,
    )
    r_high = generate_lawnmower(
        target_geojson=_POLY,
        altitude_ft=200,
        side_overlap=0.7,
        forward_overlap=0.8,
    )
    assert r_high["waypoint_spacing_m"] < r_low["waypoint_spacing_m"]


def test_forward_overlap_must_be_less_than_one():
    with pytest.raises(ValueError, match="forward_overlap"):
        generate_lawnmower(
            target_geojson=_POLY,
            altitude_ft=200,
            side_overlap=0.7,
            forward_overlap=1.0,
        )
