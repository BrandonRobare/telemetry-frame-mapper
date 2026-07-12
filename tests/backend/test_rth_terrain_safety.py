"""Tests for evaluate_rth_terrain_safety: RTH/obstacle sanity checks for
planned flights (issue #382).

Covers:
  - RTH altitude vs. terrain relief on the direct return path from the
    farthest waypoint back to home.
  - Home-point elevation vs. the highest terrain in the survey area.
  - Battery/RTH distance reserve (only when battery data is supplied).
  - Graceful degradation to an informational message when the terrain
    service has no data for the area.
"""

from __future__ import annotations

import json

from backend.services.mission_planner import evaluate_rth_terrain_safety
from backend.services.terrain import ElevationResult, NoopTerrainService, TerrainService

# Simple two-lane plan: home at (35.0, -80.5); farthest waypoint at (35.0, -80.3)
# is flat; a nearby-but-not-farthest waypoint (35.02, -80.48) is a tall peak that
# is NOT on the direct home<->farthest return path, letting checks 1 and 2 be
# tested in isolation.
_LANES_WITH_OFFPATH_PEAK = json.dumps({
    "type": "GeometryCollection",
    "geometries": [
        {"type": "LineString", "coordinates": [[-80.5, 35.0], [-80.3, 35.0]]},
        {"type": "LineString", "coordinates": [[-80.48, 35.02], [-80.48, 35.0]]},
    ],
})

# Two-lane plan where the farthest waypoint from home sits on a ridge
# (lat > 35.05), so the direct return path climbs over it.
_LANES_WITH_RIDGE_ON_PATH = json.dumps({
    "type": "GeometryCollection",
    "geometries": [
        {"type": "LineString", "coordinates": [[-80.5, 35.0], [-80.4, 35.1]]},
        {"type": "LineString", "coordinates": [[-80.45, 35.1], [-80.45, 35.0]]},
    ],
})

_EMPTY_LANES = json.dumps({"type": "GeometryCollection", "geometries": []})


class _FlatTerrain(TerrainService):
    """Every point returns 0 m elevation, in-bounds, DEM-backed."""

    def elevation(self, lat, lon):
        return ElevationResult(elevation_m=0.0, source="dem")

    def elevation_batch(self, points):
        return [self.elevation(lat, lon) for lat, lon in points]


class _RidgeTerrain(TerrainService):
    """A ridge at lat > 35.05 rises to 500 m; everything else is 0 m."""

    def elevation(self, lat, lon):
        elev = 500.0 if lat > 35.05 else 0.0
        return ElevationResult(elevation_m=elev, source="dem")

    def elevation_batch(self, points):
        return [self.elevation(lat, lon) for lat, lon in points]


class _OffPathPeakTerrain(TerrainService):
    """A single tall peak at (35.02, -80.48); flat (0 m) everywhere else."""

    def __init__(self, peak=(35.02, -80.48), peak_elev=800.0):
        self._peak = (round(peak[0], 4), round(peak[1], 4))
        self._peak_elev = peak_elev

    def elevation(self, lat, lon):
        if (round(lat, 4), round(lon, 4)) == self._peak:
            return ElevationResult(elevation_m=self._peak_elev, source="dem")
        return ElevationResult(elevation_m=0.0, source="dem")

    def elevation_batch(self, points):
        return [self.elevation(lat, lon) for lat, lon in points]


class _AllOutOfBoundsTerrain(TerrainService):
    """A DEM is configured but this area falls completely outside its coverage."""

    def elevation(self, lat, lon):
        return ElevationResult(elevation_m=0.0, source="dem", out_of_bounds=True)

    def elevation_batch(self, points):
        return [self.elevation(lat, lon) for lat, lon in points]


# ---------------------------------------------------------------------------
# Structural / degenerate input
# ---------------------------------------------------------------------------


def test_no_lanes_returns_violation():
    result = evaluate_rth_terrain_safety(
        lanes_geojson=_EMPTY_LANES,
        altitude_ft=200,
        rth_altitude_ft=100,
        terrain_service=_FlatTerrain(),
    )
    assert result.valid is False
    assert any("No lanes" in v for v in result.violations)


# ---------------------------------------------------------------------------
# Terrain-data-unavailable degradation
# ---------------------------------------------------------------------------


def test_noop_terrain_service_degrades_to_info():
    result = evaluate_rth_terrain_safety(
        lanes_geojson=_LANES_WITH_RIDGE_ON_PATH,
        altitude_ft=200,
        rth_altitude_ft=100,
        terrain_service=NoopTerrainService(),
    )
    assert result.valid is True
    assert result.warnings == []
    assert result.violations == []
    assert any("Terrain data unavailable" in msg for msg in result.info)


def test_all_out_of_bounds_degrades_to_info():
    result = evaluate_rth_terrain_safety(
        lanes_geojson=_LANES_WITH_RIDGE_ON_PATH,
        altitude_ft=200,
        rth_altitude_ft=100,
        terrain_service=_AllOutOfBoundsTerrain(),
    )
    assert result.valid is True
    assert result.warnings == []
    assert result.violations == []
    assert any("Terrain data unavailable" in msg for msg in result.info)


# ---------------------------------------------------------------------------
# Check 1: RTH altitude vs. terrain relief on the direct return path
# ---------------------------------------------------------------------------


def test_rth_altitude_clips_ridge_on_return_path_is_violation():
    result = evaluate_rth_terrain_safety(
        lanes_geojson=_LANES_WITH_RIDGE_ON_PATH,
        altitude_ft=2000,  # high cruise altitude so check 2 stays quiet
        rth_altitude_ft=50,  # ~15.2 m AGL from home -> well below the 500 m ridge
        terrain_service=_RidgeTerrain(),
    )
    assert result.valid is False
    assert any("RTH altitude" in v for v in result.violations)


def test_rth_altitude_within_margin_of_ridge_warns():
    # rth_altitude_ft chosen so RTH MSL clears the ridge by ~2 m (< 5 m margin).
    result = evaluate_rth_terrain_safety(
        lanes_geojson=_LANES_WITH_RIDGE_ON_PATH,
        altitude_ft=2000,
        rth_altitude_ft=1646.3,  # 1646.3 ft * 0.3048 = ~501.8 m -> ~1.8 m clearance
        terrain_service=_RidgeTerrain(),
    )
    assert result.valid is True
    assert any("clears the highest terrain" in w for w in result.warnings)


def test_rth_altitude_comfortably_clears_ridge_no_issue():
    result = evaluate_rth_terrain_safety(
        lanes_geojson=_LANES_WITH_RIDGE_ON_PATH,
        altitude_ft=2000,
        rth_altitude_ft=2000,  # ~609.6 m -> well above the 500 m ridge
        terrain_service=_RidgeTerrain(),
    )
    assert result.valid is True
    assert result.warnings == []
    assert result.violations == []


# ---------------------------------------------------------------------------
# Check 2: home-point elevation vs. highest terrain in the survey area
# ---------------------------------------------------------------------------


def test_home_below_offpath_peak_and_cruise_does_not_clear_warns():
    result = evaluate_rth_terrain_safety(
        lanes_geojson=_LANES_WITH_OFFPATH_PEAK,
        altitude_ft=100,  # ~30.5 m AGL -> stays below the 800 m peak
        rth_altitude_ft=100000,  # absurdly high so check 1 stays quiet
        terrain_service=_OffPathPeakTerrain(),
    )
    assert result.valid is True
    assert any("Home point sits" in w for w in result.warnings)


def test_home_below_offpath_peak_but_cruise_clears_no_warning():
    result = evaluate_rth_terrain_safety(
        lanes_geojson=_LANES_WITH_OFFPATH_PEAK,
        altitude_ft=3000,  # ~914 m AGL -> clears the 800 m peak comfortably
        rth_altitude_ft=100000,
        terrain_service=_OffPathPeakTerrain(),
    )
    assert result.valid is True
    assert not any("Home point sits" in w for w in result.warnings)


def test_home_at_or_above_terrain_no_home_warning():
    result = evaluate_rth_terrain_safety(
        lanes_geojson=_LANES_WITH_RIDGE_ON_PATH,
        altitude_ft=2000,
        rth_altitude_ft=2000,
        terrain_service=_FlatTerrain(),
    )
    assert not any("Home point sits" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Check 3: battery/RTH distance reserve (only when battery data is supplied)
# ---------------------------------------------------------------------------


def test_battery_reserve_warns_when_insufficient():
    result = evaluate_rth_terrain_safety(
        lanes_geojson=_LANES_WITH_OFFPATH_PEAK,
        altitude_ft=3000,
        rth_altitude_ft=100000,
        terrain_service=_OffPathPeakTerrain(),
        total_distance_m=2900,
        battery_range_m=3000,
        mission_buffer_pct=0.10,  # reserved range = 2700 m < required
    )
    assert result.valid is True
    assert any("battery reserve" in w.lower() for w in result.warnings)


def test_battery_reserve_ok_within_margin_no_warning():
    result = evaluate_rth_terrain_safety(
        lanes_geojson=_LANES_WITH_OFFPATH_PEAK,
        altitude_ft=3000,
        rth_altitude_ft=100000,
        terrain_service=_OffPathPeakTerrain(),
        total_distance_m=100,
        battery_range_m=3000,
        mission_buffer_pct=0.10,
    )
    assert not any("battery reserve" in w.lower() for w in result.warnings)


def test_battery_reserve_check_skipped_without_battery_data():
    result = evaluate_rth_terrain_safety(
        lanes_geojson=_LANES_WITH_OFFPATH_PEAK,
        altitude_ft=3000,
        rth_altitude_ft=100000,
        terrain_service=_OffPathPeakTerrain(),
        total_distance_m=None,
        battery_range_m=None,
    )
    assert not any("battery reserve" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# Home point defaulting / override
# ---------------------------------------------------------------------------


def test_default_home_point_is_first_waypoint():
    # With no explicit home_point, home is (35.0, -80.5) — the first vertex.
    # Farthest waypoint from that home is (35.0, -80.3) (flat), so no RTH
    # violation should be raised even with a low RTH altitude.
    result = evaluate_rth_terrain_safety(
        lanes_geojson=_LANES_WITH_OFFPATH_PEAK,
        altitude_ft=100,
        rth_altitude_ft=50,
        terrain_service=_OffPathPeakTerrain(),
    )
    assert result.valid is True
    assert result.violations == []


def test_explicit_home_point_overrides_default():
    # Force home to be the peak itself; then the "farthest" waypoint's return
    # path no longer touches the peak, but home's own elevation now equals the
    # peak, so the home-vs-terrain warning should not fire.
    result = evaluate_rth_terrain_safety(
        lanes_geojson=_LANES_WITH_OFFPATH_PEAK,
        altitude_ft=100,
        rth_altitude_ft=100000,
        home_point=(35.02, -80.48),
        terrain_service=_OffPathPeakTerrain(),
    )
    assert not any("Home point sits" in w for w in result.warnings)
