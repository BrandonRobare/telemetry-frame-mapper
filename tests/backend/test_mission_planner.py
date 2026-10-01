from __future__ import annotations

import json
import math

import pytest
from shapely import make_valid
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform, unary_union

from backend.services.mission_planner import generate_lawnmower

_POLY = (
    '{"type":"Polygon","coordinates":'
    '[[[-80.5,35.0],[-80.4,35.0],[-80.4,35.1],[-80.5,35.1],[-80.5,35.0]]]}'
)

# The test square with its north-east quadrant cut away.
_L_SHAPE = {
    "type": "Polygon",
    "coordinates": [[
        [-80.5, 35.0], [-80.4, 35.0], [-80.4, 35.03], [-80.47, 35.03],
        [-80.47, 35.1], [-80.5, 35.1], [-80.5, 35.0],
    ]],
}
# A U opening east: every sweep through the two arms is split in two by the notch.
_U_SHAPE = {
    "type": "Polygon",
    "coordinates": [[
        [-80.5, 35.0], [-80.4, 35.0], [-80.4, 35.03], [-80.47, 35.03],
        [-80.47, 35.07], [-80.4, 35.07], [-80.4, 35.1], [-80.5, 35.1], [-80.5, 35.0],
    ]],
}
# A square rotated 45 degrees, like a diagonal parcel.
_DIAMOND = {
    "type": "Polygon",
    "coordinates": [[
        [-80.45, 35.0], [-80.4, 35.05], [-80.45, 35.1], [-80.5, 35.05], [-80.45, 35.0],
    ]],
}
_AREAS = pytest.mark.parametrize(
    "area", [_L_SHAPE, _U_SHAPE, _DIAMOND], ids=["l-shape", "u-shape", "diamond"]
)


def _to_local_m(geom, lat0: float):
    """Project lon/lat onto a local flat grid in metres, the planner's own approximation."""
    m_per_deg_lon = 111_320 * math.cos(math.radians(lat0))
    return transform(lambda x, y, z=None: (x * m_per_deg_lon, y * 111_320), geom)


def _lane_spacing_m(altitude_ft: float, side_overlap: float, fov_h_deg: float = 84.0) -> float:
    altitude_m = altitude_ft * 0.3048
    return 2 * altitude_m * math.tan(math.radians(fov_h_deg / 2)) * (1 - side_overlap)


def _lanes(result: dict) -> list[list[list[float]]]:
    return [g["coordinates"] for g in json.loads(result["lanes_geojson"])["geometries"]]


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


@pytest.mark.parametrize("altitude_ft", [0, -1])
def test_non_positive_altitude_is_rejected_before_lane_generation(monkeypatch, altitude_ft):
    from backend.services import mission_planner

    class EmptyPolygon:
        bounds = (1, 0, 0, 1)

        class centroid:
            y = 0

    monkeypatch.setattr(mission_planner, "shape", lambda _: EmptyPolygon())
    with pytest.raises(ValueError, match="lane spacing"):
        generate_lawnmower(
            target_geojson=_POLY,
            altitude_ft=altitude_ft,
            side_overlap=0.7,
            forward_overlap=0.8,
        )


def test_near_zero_lane_spacing_is_rejected_before_millions_of_lanes(monkeypatch):
    from backend.services import mission_planner

    monkeypatch.setattr(mission_planner, "_MAX_LANES", 1)
    with pytest.raises(ValueError, match="too many lanes"):
        generate_lawnmower(
            target_geojson=_POLY,
            altitude_ft=200,
            side_overlap=0.9999999,
            forward_overlap=0.8,
        )


def test_lane_limit_is_enforced_during_generation(monkeypatch):
    from backend.services import mission_planner

    monkeypatch.setattr(mission_planner, "_MAX_LANES", 1)
    with pytest.raises(ValueError, match="too many lanes"):
        generate_lawnmower(
            target_geojson=_POLY,
            altitude_ft=200,
            side_overlap=0.7,
            forward_overlap=0.8,
        )


@pytest.mark.parametrize("overlap", [-0.1, 1.0])
@pytest.mark.parametrize("name", ["side_overlap", "forward_overlap"])
def test_overlap_outside_zero_to_one_is_rejected(name, overlap):
    kwargs = {"side_overlap": 0.7, "forward_overlap": 0.8, name: overlap}
    with pytest.raises(ValueError, match=name):
        generate_lawnmower(target_geojson=_POLY, altitude_ft=200, **kwargs)


# ---------------------------------------------------------------------------
# Lanes are clipped to the drawn area (#949)
# ---------------------------------------------------------------------------


@_AREAS
def test_every_waypoint_lies_inside_the_area_plus_one_lane_spacing(area):
    """Lanes spanned the polygon's bounding box, so waypoints left the drawn area (#949)."""
    result = generate_lawnmower(
        target_geojson=json.dumps(area), altitude_ft=200, side_overlap=0.7, forward_overlap=0.8
    )
    polygon = shape(area)
    lat0 = polygon.centroid.y
    allowed = _to_local_m(polygon, lat0).buffer(_lane_spacing_m(200, 0.7))

    lanes = _lanes(result)
    assert lanes
    for lane in lanes:
        for lon, lat in lane:
            assert allowed.contains(_to_local_m(Point(lon, lat), lat0)), (lon, lat)


@_AREAS
def test_no_lane_leaves_the_drawn_area(area):
    """A lane is flown end to end, so the whole segment has to stay inside (#949)."""
    result = generate_lawnmower(
        target_geojson=json.dumps(area), altitude_ft=200, side_overlap=0.7, forward_overlap=0.8
    )
    inside = shape(area).buffer(1e-9)
    for lane in _lanes(result):
        assert inside.contains(LineString(lane)), lane


@_AREAS
def test_clipped_lanes_still_image_the_whole_area(area):
    """Clipping must not open coverage holes: every point of the area is within half a
    camera footprint of some lane."""
    altitude_ft, fov_h, fov_v = 200, 84.0, 64.0
    result = generate_lawnmower(
        target_geojson=json.dumps(area),
        altitude_ft=altitude_ft,
        side_overlap=0.7,
        forward_overlap=0.8,
        fov_h_deg=fov_h,
        fov_v_deg=fov_v,
    )
    polygon = shape(area)
    lat0 = polygon.centroid.y
    altitude_m = altitude_ft * 0.3048
    half_footprint_m = altitude_m * math.tan(math.radians(min(fov_h, fov_v) / 2))
    imaged = unary_union(
        [_to_local_m(LineString(lane), lat0).buffer(half_footprint_m) for lane in _lanes(result)]
    )
    area_m = _to_local_m(polygon, lat0)
    assert area_m.difference(imaged).area / area_m.area < 1e-6


def test_split_sweeps_are_flown_cell_by_cell_not_across_the_notch():
    """Sweeps through a concave area split in two. Zig-zagging between the two pieces on
    every sweep would cross the notch (outside the area) once per lane; flying one arm
    and then the other crosses it at most once."""
    result = generate_lawnmower(
        target_geojson=json.dumps(_U_SHAPE),
        altitude_ft=200,
        side_overlap=0.7,
        forward_overlap=0.8,
    )
    polygon = shape(_U_SHAPE)
    lat0 = polygon.centroid.y
    allowed = _to_local_m(polygon, lat0).buffer(_lane_spacing_m(200, 0.7))
    lanes = _lanes(result)

    crossings = [
        (prev[-1], nxt[0])
        for prev, nxt in zip(lanes, lanes[1:], strict=False)
        if not allowed.contains(_to_local_m(LineString([prev[-1], nxt[0]]), lat0))
    ]
    assert len(crossings) <= 1, crossings


def test_rectangle_keeps_its_full_height_serpentine():
    result = generate_lawnmower(
        target_geojson=_POLY, altitude_ft=200, side_overlap=0.7, forward_overlap=0.8
    )
    lanes = _lanes(result)
    assert result["lane_count"] == len(lanes) > 1
    for i, ((x0, y0), (x1, y1)) in enumerate(lanes):
        assert x0 == x1
        assert {y0, y1} == {35.0, 35.1}
        assert (y0 < y1) == (i % 2 == 0), "lanes must alternate north and south"
    xs = [lane[0][0] for lane in lanes]
    assert xs == sorted(xs)


def test_area_narrower_than_one_lane_spacing_still_gets_a_lane():
    """A strip narrower than half a lane spacing used to produce no lane at all."""
    strip = {
        "type": "Polygon",
        "coordinates": [[
            [-80.5, 35.0], [-80.4999, 35.0], [-80.4999, 35.01], [-80.5, 35.01], [-80.5, 35.0],
        ]],
    }
    result = generate_lawnmower(
        target_geojson=json.dumps(strip), altitude_ft=200, side_overlap=0.7, forward_overlap=0.8
    )
    lanes = _lanes(result)
    assert len(lanes) == 1
    assert shape(strip).buffer(1e-9).contains(LineString(lanes[0]))


def test_self_intersecting_area_is_planned_instead_of_crashing():
    bowtie = {
        "type": "Polygon",
        "coordinates": [[
            [-80.5, 35.0], [-80.4, 35.1], [-80.4, 35.0], [-80.5, 35.1], [-80.5, 35.0],
        ]],
    }
    result = generate_lawnmower(
        target_geojson=json.dumps(bowtie), altitude_ft=200, side_overlap=0.7, forward_overlap=0.8
    )
    assert result["lane_count"] > 0
    inside = make_valid(shape(bowtie)).buffer(1e-9)
    for lane in _lanes(result):
        assert inside.contains(LineString(lane)), lane


# ---------------------------------------------------------------------------
# Terrain-following tests
# ---------------------------------------------------------------------------


class TestTerrainFollowingDefault:
    """When terrain_follow is False (default), output is unchanged 2-D lanes."""

    def test_lanes_are_2d_by_default(self):
        result = generate_lawnmower(
            target_geojson=_POLY,
            altitude_ft=300,
            side_overlap=0.6,
            forward_overlap=0.7,
        )
        geojson = json.loads(result["lanes_geojson"])
        for geom in geojson["geometries"]:
            for coord in geom["coordinates"]:
                assert len(coord) == 2, f"Expected 2-D coordinate, got {coord}"


class TestTerrainFollowingWithMock:
    """When terrain_follow=True, lanes get 3-D coords with ground elevation."""

    def test_lanes_are_3d_with_terrain_follow(self):
        from backend.services.terrain import ElevationResult, TerrainService

        class _MockTerrain(TerrainService):
            def elevation(self, lat, lon):
                return ElevationResult(elevation_m=100.0, source="mock")

            def elevation_batch(self, points):
                return [ElevationResult(elevation_m=100.0, source="mock") for _ in points]

        result = generate_lawnmower(
            target_geojson=_POLY,
            altitude_ft=200,
            side_overlap=0.7,
            forward_overlap=0.8,
            terrain_follow=True,
            terrain_service=_MockTerrain(),
        )
        geojson = json.loads(result["lanes_geojson"])
        agl_m = 200 * 0.3048
        expected_msl = agl_m + 100.0
        for geom in geojson["geometries"]:
            for coord in geom["coordinates"]:
                assert len(coord) == 3, f"Expected 3-D coordinate, got {coord}"
                assert coord[2] == pytest.approx(expected_msl, abs=0.1)

    def test_oob_point_falls_back_to_agl(self):
        from backend.services.terrain import ElevationResult, TerrainService

        class _MockTerrainOob(TerrainService):
            def elevation(self, lat, lon):
                return ElevationResult(elevation_m=0.0, source="mock", out_of_bounds=True)

            def elevation_batch(self, points):
                return [
                    ElevationResult(elevation_m=0.0, source="mock", out_of_bounds=True)
                    for _ in points
                ]

        result = generate_lawnmower(
            target_geojson=_POLY,
            altitude_ft=200,
            side_overlap=0.7,
            forward_overlap=0.8,
            terrain_follow=True,
            terrain_service=_MockTerrainOob(),
        )
        geojson = json.loads(result["lanes_geojson"])
        agl_m = 200 * 0.3048
        for geom in geojson["geometries"]:
            for coord in geom["coordinates"]:
                # OOB -> ground=0, so MSL = AGL
                assert coord[2] == pytest.approx(agl_m, abs=0.1)

    def test_mixed_elevations_per_point(self):
        from backend.services.terrain import ElevationResult, TerrainService

        class _MockTerrainMixed(TerrainService):
            def __init__(self):
                self._call = 0

            def elevation(self, lat, lon):
                self._call += 1
                return ElevationResult(elevation_m=50.0 + (self._call * 10.0), source="mock")

            def elevation_batch(self, points):
                results = []
                for _ in points:
                    self._call += 1
                    elev = 50.0 + (self._call * 10.0)
                    results.append(ElevationResult(elevation_m=elev, source="mock"))
                return results

        result = generate_lawnmower(
            target_geojson=_POLY,
            altitude_ft=300,
            side_overlap=0.7,
            forward_overlap=0.8,
            terrain_follow=True,
            terrain_service=_MockTerrainMixed(),
        )
        geojson = json.loads(result["lanes_geojson"])
        agl_m = 300 * 0.3048
        altitudes = []
        for geom in geojson["geometries"]:
            for coord in geom["coordinates"]:
                altitudes.append(coord[2])
        # At least two distinct altitudes (different ground elevations)
        assert len(set(altitudes)) >= 2
        # All altitudes should be above AGL
        for a in altitudes:
            assert a > agl_m

class TestTerrainDegradedSignal:
    """A DEM that yields no usable elevations must not pass as terrain following (#646)."""

    def _broken_dem_service(self):
        """Terrain service behaving like a DEM whose every sample fails to read."""
        from backend.services.terrain import ElevationResult, TerrainService

        class _BrokenDem(TerrainService):
            def elevation(self, lat, lon):
                return ElevationResult(elevation_m=0.0, source="dem", out_of_bounds=True)

            def elevation_batch(self, points):
                return [self.elevation(lat, lon) for lat, lon in points]

        return _BrokenDem()

    def test_unusable_dem_flags_terrain_degraded(self):
        """An unreadable DEM sets terrain_degraded instead of silently using ground 0 (#646)."""
        result = generate_lawnmower(
            target_geojson=_POLY,
            altitude_ft=200,
            side_overlap=0.7,
            forward_overlap=0.8,
            terrain_follow=True,
            terrain_service=self._broken_dem_service(),
        )
        assert result["terrain_degraded"] is True

    def test_usable_dem_is_not_degraded(self):
        """A DEM returning real elevations reports terrain following as intact (#646)."""
        from backend.services.terrain import ElevationResult, TerrainService

        class _GoodDem(TerrainService):
            def elevation(self, lat, lon):
                return ElevationResult(elevation_m=120.0, source="dem")

            def elevation_batch(self, points):
                return [self.elevation(lat, lon) for lat, lon in points]

        result = generate_lawnmower(
            target_geojson=_POLY,
            altitude_ft=200,
            side_overlap=0.7,
            forward_overlap=0.8,
            terrain_follow=True,
            terrain_service=_GoodDem(),
        )
        assert result["terrain_degraded"] is False

    def test_plan_generation_and_rth_check_agree(self):
        """Both consumers of the same broken DEM report terrain data as unusable (#646)."""
        from backend.services.mission_planner import evaluate_rth_terrain_safety

        svc = self._broken_dem_service()
        result = generate_lawnmower(
            target_geojson=_POLY,
            altitude_ft=200,
            side_overlap=0.7,
            forward_overlap=0.8,
            terrain_follow=True,
            terrain_service=svc,
        )
        rth = evaluate_rth_terrain_safety(
            lanes_geojson=result["lanes_geojson"],
            altitude_ft=200,
            rth_altitude_ft=100,
            terrain_service=svc,
        )
        assert result["terrain_degraded"] is True
        assert any("Terrain data unavailable" in msg for msg in rth.info)
