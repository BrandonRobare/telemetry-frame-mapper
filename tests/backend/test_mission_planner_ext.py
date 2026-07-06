"""Tests for mission_planner service additions: validation, battery estimation,
segmentation, and gap-based re-fly plan generation."""

from __future__ import annotations

import json

from backend.services.mission_planner import (
    estimate_batteries,
    generate_lawnmower,
    generate_lawnmower_from_gaps,
    segment_plan,
    validate_plan,
)

_POLY = (
    '{"type":"Polygon","coordinates":'
    '[[[-80.5,35.0],[-80.4,35.0],[-80.4,35.1],[-80.5,35.1],[-80.5,35.0]]]}'
)


# ---------------------------------------------------------------------------
# validate_plan
# ---------------------------------------------------------------------------


def test_validate_plan_passes_for_standard_params():
    result = generate_lawnmower(
        target_geojson=_POLY,
        altitude_ft=200,
        side_overlap=0.7,
        forward_overlap=0.8,
    )
    v = validate_plan(
        lanes_geojson=result["lanes_geojson"],
        altitude_ft=200,
        side_overlap=0.7,
        forward_overlap=0.8,
    )
    assert v.valid is True
    assert v.violations == []


def test_validate_plan_warns_on_excessive_distance():
    result = generate_lawnmower(
        target_geojson=_POLY,
        altitude_ft=200,
        side_overlap=0.7,
        forward_overlap=0.8,
    )
    v = validate_plan(
        lanes_geojson=result["lanes_geojson"],
        altitude_ft=200,
        side_overlap=0.7,
        forward_overlap=0.8,
        battery_range_m=1,  # impossibly small
    )
    assert any("exceeds battery range" in w for w in v.warnings)


def test_validate_plan_rejects_empty_lanes():
    v = validate_plan(
        lanes_geojson='{"type":"GeometryCollection","geometries":[]}',
        altitude_ft=200,
        side_overlap=0.7,
        forward_overlap=0.8,
    )
    assert not v.valid
    assert any("No lanes" in viol for viol in v.violations)


def test_validate_plan_warns_single_lane():
    single_lane = json.dumps({
        "type": "GeometryCollection",
        "geometries": [
            {"type": "LineString", "coordinates": [[-80.5, 35.0], [-80.4, 35.1]]}
        ],
    })
    v = validate_plan(
        lanes_geojson=single_lane,
        altitude_ft=200,
        side_overlap=0.7,
        forward_overlap=0.8,
    )
    assert v.valid
    assert any("Single-lane" in w for w in v.warnings)


def test_validate_plan_rejects_bad_forward_overlap():
    result = generate_lawnmower(
        target_geojson=_POLY,
        altitude_ft=200,
        side_overlap=0.7,
        forward_overlap=0.8,
    )
    v = validate_plan(
        lanes_geojson=result["lanes_geojson"],
        altitude_ft=200,
        side_overlap=0.7,
        forward_overlap=1.0,  # 100% overlap = zero waypoint spacing
    )
    assert not v.valid
    assert any("Forward overlap" in viol for viol in v.violations)


# ---------------------------------------------------------------------------
# estimate_batteries
# ---------------------------------------------------------------------------


def test_estimate_batteries_zero_distance():
    assert estimate_batteries(0) == 0.0


def test_estimate_batteries_exactly_one():
    # 10 m/s * 1200 s = 12000 m
    assert estimate_batteries(12000) == 1.0


def test_estimate_batteries_rounds():
    assert estimate_batteries(15000) == 1.25


def test_estimate_batteries_custom_params():
    assert estimate_batteries(5000, flight_speed_ms=5, battery_flight_time_s=1000) == 1.0


# ---------------------------------------------------------------------------
# segment_plan
# ---------------------------------------------------------------------------


def test_segment_small_plan_returns_one_segment():
    # Use a narrow enough polygon to fit in one battery segment
    result = generate_lawnmower(
        target_geojson=_POLY,
        altitude_ft=400,  # Higher altitude = wider swath = fewer lanes
        side_overlap=0.3,
        forward_overlap=0.5,
    )
    segments = segment_plan(
        lanes_geojson=result["lanes_geojson"],
        total_distance_m=result["total_distance_m"],
        battery_range_m=999999,
    )
    assert len(segments) == 1
    assert segments[0].index == 0
    assert segments[0].from_lane == 0


def test_segment_handles_empty_geometries():
    empty = '{"type":"GeometryCollection","geometries":[]}'
    segments = segment_plan(
        lanes_geojson=empty,
        total_distance_m=1000,
    )
    assert segments == []


def test_segment_large_plan_splits():
    result = generate_lawnmower(
        target_geojson=_POLY,
        altitude_ft=200,
        side_overlap=0.1,
        forward_overlap=0.2,
    )
    # Force segmentation by giving a tiny battery range
    segments = segment_plan(
        lanes_geojson=result["lanes_geojson"],
        total_distance_m=result["total_distance_m"],
        battery_range_m=1,  # force every lane to be its own segment
    )
    assert len(segments) > 1
    assert segments[0].index == 0
    # Each segment should cover a contiguous range of lanes
    for i in range(len(segments) - 1):
        assert segments[i].to_lane + 1 == segments[i + 1].from_lane


def test_segment_landing_resume_waypoints():
    result = generate_lawnmower(
        target_geojson=_POLY,
        altitude_ft=200,
        side_overlap=0.1,
        forward_overlap=0.2,
    )
    segments = segment_plan(
        lanes_geojson=result["lanes_geojson"],
        total_distance_m=result["total_distance_m"],
        battery_range_m=1,
    )
    # Middle segments should have landing and resume waypoints
    assert len(segments) > 1
    if len(segments) > 1:
        middle = segments[0]
        # Not the last segment: should have landing_wpt and resume_wpt
        if middle.to_lane < segments[-1].from_lane:
            assert middle.landing_wpt is not None
            assert middle.resume_wpt is not None
        # Last segment: no landing/resume needed
        assert segments[-1].landing_wpt is None
        assert segments[-1].resume_wpt is None


# ---------------------------------------------------------------------------
# generate_lawnmower_from_gaps
# ---------------------------------------------------------------------------


def test_gap_re_fly_returns_none_for_empty():
    assert generate_lawnmower_from_gaps("", 200, 0.7, 0.8) is None
    assert generate_lawnmower_from_gaps("null", 200, 0.7, 0.8) is None
    assert generate_lawnmower_from_gaps("{}", 200, 0.7, 0.8) is None


def test_gap_re_fly_with_polygon():
    polygon = [[
        [-80.51, 35.0],
        [-80.49, 35.0],
        [-80.49, 35.05],
        [-80.51, 35.05],
        [-80.51, 35.0],
    ]]
    gap = json.dumps({
        "type": "Polygon",
        "coordinates": polygon,
    })
    result = generate_lawnmower_from_gaps(gap, 200, 0.7, 0.8)
    assert result is not None
    assert result["source"] == "gap_re_fly"
    assert result["lane_count"] > 0
    assert result["total_distance_m"] > 0


def test_gap_re_fly_with_feature_collection():
    polygon = [[
        [-80.51, 35.0],
        [-80.49, 35.0],
        [-80.49, 35.05],
        [-80.51, 35.05],
        [-80.51, 35.0],
    ]]
    gap = json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": polygon,
            },
        }],
    })
    result = generate_lawnmower_from_gaps(gap, 200, 0.7, 0.8)
    assert result is not None
    assert result["source"] == "gap_re_fly"


def test_gap_re_fly_returns_none_for_non_polygon():
    gap = '{"type":"Point","coordinates":[-80.5,35.0]}'
    assert generate_lawnmower_from_gaps(gap, 200, 0.7, 0.8) is None