"""Tests for mission_planner service additions: validation, battery estimation,
segmentation, and gap-based re-fly plan generation."""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET

import pytest
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import transform, unary_union

from backend.services.coverage import run_coverage
from backend.services.mission_planner import (
    estimate_batteries,
    generate_lawnmower,
    generate_lawnmower_from_gaps,
    segment_plan,
    validate_plan,
    write_gpx,
    write_kml,
)
from backend.services.terrain import ElevationResult, TerrainService

_POLY = (
    '{"type":"Polygon","coordinates":'
    '[[[-80.5,35.0],[-80.4,35.0],[-80.4,35.1],[-80.5,35.1],[-80.5,35.0]]]}'
)
_KML_NS = {"k": "http://www.opengis.net/kml/2.2"}
_GPX_NS = {"g": "http://www.topografix.com/GPX/1/1"}


def _to_local_m(geom, lat0: float):
    """Project lon/lat onto a local flat grid in metres, the planner's own approximation."""
    m_per_deg_lon = 111_320 * math.cos(math.radians(lat0))
    return transform(lambda x, y, z=None: (x * m_per_deg_lon, y * 111_320), geom)


def _lanes(result: dict) -> list[list[list[float]]]:
    return [g["coordinates"] for g in json.loads(result["lanes_geojson"])["geometries"]]


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


def _two_gap_coverage_result() -> str:
    """gap_geojson of a real coverage run whose one footprint covers the middle band of
    the target, leaving a western and an eastern gap."""
    target = {
        "type": "Polygon",
        "coordinates": [[
            [-80.5, 35.0], [-80.4, 35.0], [-80.4, 35.1], [-80.5, 35.1], [-80.5, 35.0],
        ]],
    }
    footprint = {
        "type": "Polygon",
        "coordinates": [[
            [-80.47, 34.99], [-80.43, 34.99], [-80.43, 35.11], [-80.47, 35.11], [-80.47, 34.99],
        ]],
    }
    return run_coverage([json.dumps(footprint)], json.dumps(target))["gap_geojson"]


def _wrap_gaps(gap_geojson: str, wrapper: str) -> str:
    parts = list(shape(json.loads(gap_geojson)).geoms)
    if wrapper == "multipolygon":
        return gap_geojson
    if wrapper == "feature_collection":
        return json.dumps({
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {}, "geometry": mapping(p)} for p in parts
            ],
        })
    return json.dumps({"type": "GeometryCollection", "geometries": [mapping(p) for p in parts]})


@pytest.mark.parametrize("wrapper", ["multipolygon", "feature_collection", "geometry_collection"])
def test_gap_re_fly_plans_lanes_over_every_gap_and_nowhere_else(wrapper):
    """Only the first gap was planned, and a MultiPolygon was planned over the bounding
    box of all gaps, re-flying the covered area between them (#949)."""
    gap_geojson = _two_gap_coverage_result()
    gaps = list(shape(json.loads(gap_geojson)).geoms)
    assert len(gaps) == 2

    result = generate_lawnmower_from_gaps(_wrap_gaps(gap_geojson, wrapper), 200, 0.7, 0.8)

    assert result is not None
    lanes = [LineString(lane) for lane in _lanes(result)]
    for gap in gaps:
        assert any(lane.intersects(gap) for lane in lanes), f"no lane over gap {gap.bounds}"

    lat0 = unary_union(gaps).centroid.y
    lane_spacing_m = 2 * 200 * 0.3048 * math.tan(math.radians(84.0 / 2)) * (1 - 0.7)
    allowed = _to_local_m(unary_union(gaps), lat0).buffer(lane_spacing_m)
    for lane in lanes:
        for lon, lat in lane.coords:
            assert allowed.contains(_to_local_m(Point(lon, lat), lat0)), (lon, lat)


def test_gap_re_fly_covers_a_gap_narrower_than_one_lane_spacing():
    """The typical gap is a thin strip between two flown lanes; it used to get no lane."""
    def strip(west: float) -> list:
        east = west + 0.0001  # ~9 m, well under the ~33 m lane spacing
        return [[[west, 35.0], [east, 35.0], [east, 35.01], [west, 35.01], [west, 35.0]]]

    strips = {"type": "MultiPolygon", "coordinates": [strip(-80.5), strip(-80.49)]}
    result = generate_lawnmower_from_gaps(json.dumps(strips), 200, 0.7, 0.8)

    assert result is not None
    lanes = [LineString(lane) for lane in _lanes(result)]
    for gap in shape(strips).geoms:
        assert any(lane.intersects(gap) for lane in lanes), f"no lane over gap {gap.bounds}"


# ---------------------------------------------------------------------------
# KML / GPX export
# ---------------------------------------------------------------------------


class _SlopedTerrain(TerrainService):
    """Ground that rises to the north-east, so every vertex gets its own altitude."""

    def elevation(self, lat, lon):
        ground_m = 100 + (lat - 35.0) * 900 + (lon + 80.5) * 400
        return ElevationResult(elevation_m=ground_m, source="dem")

    def elevation_batch(self, points):
        return [self.elevation(lat, lon) for lat, lon in points]


def _kml_linestrings(path):
    return ET.parse(path).getroot().findall(".//k:LineString", _KML_NS)


def test_kml_and_gpx_carry_the_terrain_following_altitudes(tmp_path):
    """write_kml hard-coded altitude 0 and write_gpx emitted no <ele> (#949)."""
    result = generate_lawnmower(
        target_geojson=_POLY,
        altitude_ft=200,
        side_overlap=0.7,
        forward_overlap=0.8,
        terrain_follow=True,
        terrain_service=_SlopedTerrain(),
    )
    expected = [coord[2] for lane in _lanes(result) for coord in lane]
    assert len(set(expected)) > 2

    kml_altitudes = []
    for line in _kml_linestrings(write_kml(1, result["lanes_geojson"], tmp_path)):
        assert line.findtext("k:altitudeMode", namespaces=_KML_NS) == "absolute"
        for triple in line.findtext("k:coordinates", namespaces=_KML_NS).split():
            kml_altitudes.append(float(triple.split(",")[2]))
    assert kml_altitudes == expected

    gpx = ET.parse(write_gpx(1, result["lanes_geojson"], tmp_path)).getroot()
    gpx_elevations = [
        pt.findtext("g:ele", namespaces=_GPX_NS) for pt in gpx.iterfind(".//g:trkpt", _GPX_NS)
    ]
    assert [float(e) if e is not None else None for e in gpx_elevations] == expected


def test_kml_and_gpx_of_a_2d_plan_claim_no_absolute_altitude(tmp_path):
    """Without terrain following there is no MSL altitude to export; writing
    altitudeMode=absolute (or <ele>) with 0 would send the aircraft to sea level."""
    result = generate_lawnmower(
        target_geojson=_POLY, altitude_ft=200, side_overlap=0.7, forward_overlap=0.8
    )

    for line in _kml_linestrings(write_kml(1, result["lanes_geojson"], tmp_path)):
        assert line.find("k:altitudeMode", _KML_NS) is None
    gpx = ET.parse(write_gpx(1, result["lanes_geojson"], tmp_path)).getroot()
    assert gpx.find(".//g:ele", _GPX_NS) is None
