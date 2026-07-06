from __future__ import annotations

import json
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