from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

from shapely.geometry import shape

from .terrain import TerrainService, get_terrain_service

logger = logging.getLogger(__name__)

_MAX_LANES = 10_000


def _usable_elevations(results: list) -> list[float]:
    """Elevations that came from real terrain data (in-bounds, non-no-op)."""
    return [r.elevation_m for r in results if not r.out_of_bounds and r.source != "noop"]


def generate_lawnmower(
    target_geojson: str,
    altitude_ft: float,
    side_overlap: float,
    forward_overlap: float,
    fov_h_deg: float = 84.0,
    fov_v_deg: float = 64.0,
    terrain_follow: bool = False,
    terrain_service: TerrainService | None = None,
) -> dict:
    """Returns lanes_geojson, lane_count, total_distance_m, waypoint_spacing_m.

    When *terrain_follow* is True, waypoints embed per-point ground elevation
    sampled from *terrain_service* so that the requested AGL is maintained
    across varying terrain.  The lanes GeoJSON includes a 3rd coordinate
    (altitude in metres above sea level) set to ``requested_agl_m + ground_elevation_m``
    for each vertex.  OOB / missing DEM points fall back to the requested AGL
    (i.e. ground elevation = 0).  When *no* vertex got usable terrain data the
    returned ``terrain_degraded`` flag is True: the altitudes are plain AGL above
    the takeoff point and the plan is not really terrain-following.
    """
    if side_overlap >= 1.0:
        raise ValueError(f"side_overlap must be < 1.0, got {side_overlap}")
    if forward_overlap >= 1.0:
        raise ValueError(f"forward_overlap must be < 1.0, got {forward_overlap}")

    poly = shape(json.loads(target_geojson))
    bounds = poly.bounds  # minx, miny, maxx, maxy
    centroid = poly.centroid

    altitude_m = altitude_ft * 0.3048
    gw = 2 * altitude_m * math.tan(math.radians(fov_h_deg / 2))
    gh = 2 * altitude_m * math.tan(math.radians(fov_v_deg / 2))
    lane_spacing = gw * (1 - side_overlap)
    if lane_spacing <= 0:
        lane_spacing = gw * 0.3  # fallback for degenerate overlap values
    waypoint_spacing_m = gh * (1 - forward_overlap)
    if waypoint_spacing_m <= 0:
        waypoint_spacing_m = gh * 0.2  # fallback for degenerate overlap values

    # Convert lane_spacing from meters to degrees along the longitude axis.
    # meters-per-degree-longitude = 111_320 * cos(latitude), so the step in
    # degrees depends on the centroid latitude of the target polygon.
    lat_rad = math.radians(centroid.y)
    meters_per_deg_lon = 111_320 * math.cos(lat_rad)
    # Guard at the poles (tiny value would produce very large step).
    if meters_per_deg_lon < 1_000:
        meters_per_deg_lon = 1_000
    lane_spacing_deg = lane_spacing / meters_per_deg_lon
    if not math.isfinite(lane_spacing_deg) or lane_spacing_deg <= 0:
        raise ValueError("Altitude and overlap produce a non-positive lane spacing")

    minx, miny, maxx, maxy = bounds
    lanes = []
    x = minx + lane_spacing_deg / 2
    direction = 1
    while x <= maxx:
        if len(lanes) >= _MAX_LANES:
            raise ValueError(f"Plan would produce too many lanes (maximum {_MAX_LANES})")
        if direction == 1:
            lanes.append([[x, miny], [x, maxy]])
        else:
            lanes.append([[x, maxy], [x, miny]])
        x += lane_spacing_deg
        direction *= -1

    # Total distance: along-lane distances + inter-lane transit legs.
    meters_per_deg_lat = 111_320  # approximately constant per degree latitude
    along_lane_dist = 0.0
    for ln in lanes:
        dx = (ln[1][0] - ln[0][0]) * meters_per_deg_lon
        dy = (ln[1][1] - ln[0][1]) * meters_per_deg_lat
        along_lane_dist += math.hypot(dx, dy)
    # Transit legs between consecutive lanes
    transit_dist = 0.0
    for i in range(len(lanes) - 1):
        transit_dist += math.hypot(
            (lanes[i + 1][0][0] - lanes[i][1][0]) * meters_per_deg_lon,
            (lanes[i + 1][0][1] - lanes[i][1][1]) * meters_per_deg_lat,
        )
    total_dist = along_lane_dist + transit_dist

    # ---- terrain-following altitude enrichment ---------------------------
    terrain_degraded = False
    if terrain_follow:
        svc = terrain_service or get_terrain_service()
        # Build altitude-enriched lane coordinates
        enriched_lanes, terrain_degraded = _enrich_lanes_with_terrain(
            lanes, altitude_m, svc
        )
        if terrain_degraded:
            logger.warning(
                "Terrain following was requested but no usable terrain data was returned "
                "for this area; waypoint altitudes are plain AGL above the takeoff point."
            )
        lanes_geojson = json.dumps({
            "type": "GeometryCollection",
            "geometries": [{"type": "LineString", "coordinates": ln} for ln in enriched_lanes],
        })
    else:
        lanes_geojson = json.dumps({
            "type": "GeometryCollection",
            "geometries": [{"type": "LineString", "coordinates": ln} for ln in lanes],
        })

    return {
        "lanes_geojson": lanes_geojson,
        "lane_count": len(lanes),
        "total_distance_m": round(total_dist, 1),
        "waypoint_spacing_m": round(waypoint_spacing_m, 2),
        "terrain_degraded": terrain_degraded,
    }


def _enrich_lanes_with_terrain(
    lanes: list,
    requested_agl_m: float,
    svc: TerrainService,
) -> tuple[list, bool]:
    """Insert per-vertex ground-elevation-based MSL altitudes into lane coords.

    Each lane vertex gets a 3rd coordinate: ``requested_agl_m + ground_elevation_m``.
    OOB / missing DEM points default to ``requested_agl_m`` (ground elevation = 0).

    Returns ``(enriched_lanes, terrain_degraded)`` where *terrain_degraded* is True
    when no vertex got usable terrain data — an unreadable DEM, no DEM at all, or
    the whole area outside DEM coverage — so the caller can tell that the plan is
    not actually terrain-following.  Usability is decided by the same predicate the
    RTH terrain check uses, so the two never disagree about the same DEM.
    """
    point_set: dict[tuple[float, float], int] = {}
    all_points: list[tuple[float, float]] = []
    for ln in lanes:
        for pt in ln:
            key = (pt[1], pt[0])  # (lat, lon)
            if key not in point_set:
                point_set[key] = len(all_points)
                all_points.append(key)

    elev_results = svc.elevation_batch(all_points)

    altitude_map: dict[tuple[float, float], float] = {}
    for (lat, lon), result in zip(all_points, elev_results, strict=True):
        ground = result.elevation_m if not result.out_of_bounds else 0.0
        altitude_map[(lat, lon)] = requested_agl_m + ground

    enriched: list = []
    for ln in lanes:
        enriched_ln = []
        for pt in ln:
            msl = altitude_map.get((pt[1], pt[0]), requested_agl_m)
            enriched_ln.append([pt[0], pt[1], round(msl, 2)])
        enriched.append(enriched_ln)
    return enriched, not _usable_elevations(elev_results)


def write_kml(plan_id: int, lanes_geojson: str, exports_dir: Path, suffix: str = "") -> Path:
    """Write KML file for the given plan. Returns the file path."""
    exports_dir.mkdir(parents=True, exist_ok=True)
    kml_path = exports_dir / f"plan_{plan_id}{suffix}.kml"
    geo = json.loads(lanes_geojson)
    placemarks = ""
    for geom in geo.get("geometries", []):
        coords = " ".join(f"{c[0]},{c[1]},0" for c in geom["coordinates"])
        inner = f"<coordinates>{coords}</coordinates>"
        placemarks += f"<Placemark><LineString>{inner}</LineString></Placemark>\n"
    kml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>{placemarks}</Document>
</kml>"""
    kml_path.write_text(kml_content)
    return kml_path


def write_gpx(plan_id: int, lanes_geojson: str, exports_dir: Path, suffix: str = "") -> Path:
    """Write GPX file for the given plan. Returns the file path."""
    exports_dir.mkdir(parents=True, exist_ok=True)
    gpx_path = exports_dir / f"plan_{plan_id}{suffix}.gpx"
    geo = json.loads(lanes_geojson)
    trkseg_points = ""
    for geom in geo.get("geometries", []):
        for c in geom["coordinates"]:
            trkseg_points += f'<trkpt lat="{c[1]}" lon="{c[0]}"></trkpt>\n'
    gpx_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
<trk><trkseg>{trkseg_points}</trkseg></trk>
</gpx>"""
    gpx_path.write_text(gpx_content)
    return gpx_path


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    valid: bool = True
    warnings: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def validate_plan(
    lanes_geojson: str,
    altitude_ft: float,
    side_overlap: float,
    forward_overlap: float,
    fov_h_deg: float = 84.0,
    fov_v_deg: float = 64.0,
    battery_range_m: float = 3000,
) -> ValidationResult:
    """Simulate lane path and flag spacing/turn/flight-time violations."""
    result = ValidationResult()

    # Lane spacing check
    altitude_m = altitude_ft * 0.3048
    gw = 2 * altitude_m * math.tan(math.radians(fov_h_deg / 2))
    lane_spacing_m = gw * (1 - side_overlap)
    if lane_spacing_m <= 0:
        result.valid = False
        result.violations.append("Lane spacing is non-positive; check overlap values")
        return result

    geo = json.loads(lanes_geojson)
    lane_count = len(geo.get("geometries", []))

    if lane_count == 0:
        result.valid = False
        result.violations.append("No lanes in plan geometry")
        return result

    if lane_count < 2:
        result.warnings.append("Single-lane plan; no adjacent-lane overlap checks possible")

    # Compute total distance using the same logic as generate_lawnmower
    lat_rad = math.radians(float(geo["geometries"][0]["coordinates"][0][1]))
    meters_per_deg_lon = max(111_320 * math.cos(lat_rad), 1_000)
    meters_per_deg_lat = 111_320

    along_lane_dist = 0.0
    for geom in geo["geometries"]:
        coords = geom["coordinates"]
        dx = (coords[1][0] - coords[0][0]) * meters_per_deg_lon
        dy = (coords[1][1] - coords[0][1]) * meters_per_deg_lat
        along_lane_dist += math.hypot(dx, dy)

    transit_dist = 0.0
    for i in range(lane_count - 1):
        c0 = geo["geometries"][i]["coordinates"]
        c1 = geo["geometries"][i + 1]["coordinates"]
        transit_dist += math.hypot(
            (c1[0][0] - c0[1][0]) * meters_per_deg_lon,
            (c1[0][1] - c0[1][1]) * meters_per_deg_lat,
        )

    total_dist_m = along_lane_dist + transit_dist

    if total_dist_m > battery_range_m:
        remaining = total_dist_m - battery_range_m
        result.warnings.append(
            f"Total distance ({total_dist_m:.0f} m) exceeds battery range "
            f"({battery_range_m:.0f} m) by {remaining:.0f} m; consider multi-battery segmentation"
        )

    # Turn angle check: all turns are roughly 180 deg in a lawnmower so flag tight turns.
    if lane_spacing_m < 2:
        result.warnings.append(
            f"Lane spacing ({lane_spacing_m:.2f} m) may be too tight for smooth turns"
        )

    # Forward overlap waypoint density check
    gh = 2 * altitude_m * math.tan(math.radians(fov_v_deg / 2))
    waypoint_spacing_m = gh * (1 - forward_overlap)
    if waypoint_spacing_m <= 0:
        result.valid = False
        result.violations.append("Forward overlap produces zero or negative waypoint spacing")
    elif waypoint_spacing_m > 50:
        result.warnings.append(
            f"Waypoint spacing ({waypoint_spacing_m:.1f} m) is large; "
            "overlap may be too low for reliable reconstruction"
        )

    return result


# ---------------------------------------------------------------------------
# RTH / obstacle sanity check
# ---------------------------------------------------------------------------

_RTH_PATH_SAMPLES = 9
_RTH_CLEARANCE_MARGIN_M = 5.0


def _flatten_lane_points(geo: dict) -> list[tuple[float, float]]:
    """Return unique (lat, lon) points from a lanes GeometryCollection, in order."""
    seen: set[tuple[float, float]] = set()
    points: list[tuple[float, float]] = []
    for geom in geo.get("geometries", []):
        for coord in geom.get("coordinates", []):
            key = (coord[1], coord[0])
            if key not in seen:
                seen.add(key)
                points.append(key)
    return points


def _planar_distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Approximate flat-earth distance in meters between two (lat, lon) points."""
    lat_rad = math.radians((a[0] + b[0]) / 2)
    meters_per_deg_lon = max(111_320 * math.cos(lat_rad), 1_000)
    dx = (b[1] - a[1]) * meters_per_deg_lon
    dy = (b[0] - a[0]) * 111_320
    return math.hypot(dx, dy)


def _interpolate_path(
    a: tuple[float, float], b: tuple[float, float], n: int
) -> list[tuple[float, float]]:
    """Return *n* evenly spaced (lat, lon) points from *a* to *b*, inclusive."""
    if n < 2:
        return [a, b]
    return [
        (a[0] + (b[0] - a[0]) * i / (n - 1), a[1] + (b[1] - a[1]) * i / (n - 1))
        for i in range(n)
    ]


def evaluate_rth_terrain_safety(
    lanes_geojson: str,
    altitude_ft: float,
    rth_altitude_ft: float,
    home_point: tuple[float, float] | None = None,
    terrain_service: TerrainService | None = None,
    total_distance_m: float | None = None,
    battery_range_m: float | None = None,
    mission_buffer_pct: float = 0.0,
    clearance_margin_m: float = _RTH_CLEARANCE_MARGIN_M,
) -> ValidationResult:
    """Evaluate RTH-altitude-vs-terrain and home-elevation sanity checks for a plan.

    Uses the configured terrain service (DEM) to check:

      1. Whether the configured RTH altitude clears the highest terrain sampled
         along the direct return path from the farthest waypoint back to the
         home point.
      2. Whether the home point sits below the highest terrain in the survey
         area such that the planned cruise altitude would fly below that
         terrain elsewhere in the survey.
      3. (Only when *battery_range_m* and *total_distance_m* are supplied)
         whether the plan distance plus the RTH leg back to home leaves an
         adequate battery reserve, using *mission_buffer_pct* as the safety
         margin. Skipped entirely when either datum is missing.

    *home_point* defaults to the first vertex of the plan's lanes when not
    supplied — a reasonable stand-in for "launch near the survey area" when no
    explicit home point is tracked.

    When the terrain service has no usable data for the area (no DEM
    configured, or the area falls outside DEM coverage), checks 1 and 2 are
    skipped and an informational message is added to ``result.info`` instead
    of raising a warning or violation.
    """
    result = ValidationResult()

    geo = json.loads(lanes_geojson)
    points = _flatten_lane_points(geo)
    if not points:
        result.valid = False
        result.violations.append("No lanes in plan geometry")
        return result

    home = home_point or points[0]

    # ---- Check 3: battery/RTH-reserve (independent of terrain data) --------
    if battery_range_m is not None and total_distance_m is not None:
        rth_leg_m = _planar_distance_m(points[-1], home)
        required_m = total_distance_m + rth_leg_m
        reserved_range_m = battery_range_m * (1 - mission_buffer_pct)
        if required_m > reserved_range_m:
            result.warnings.append(
                f"Plan distance plus RTH leg back to home ({required_m:.0f} m) exceeds "
                f"the battery-safe range with reserve ({reserved_range_m:.0f} m, "
                f"{mission_buffer_pct * 100:.0f}% margin); battery reserve for RTH is doubtful"
            )

    # ---- Checks 1 & 2: terrain-based -----------------------------------------
    svc = terrain_service or get_terrain_service()

    farthest = max(points, key=lambda p: _planar_distance_m(home, p))
    path_points = _interpolate_path(farthest, home, _RTH_PATH_SAMPLES)

    query_points = [home, *path_points, *points]
    elevations = svc.elevation_batch(query_points)

    home_result = elevations[0]
    path_results = elevations[1 : 1 + len(path_points)]
    survey_results = elevations[1 + len(path_points) :]

    home_usable = home_result.source != "noop" and not home_result.out_of_bounds
    path_usable = _usable_elevations(path_results)
    survey_usable = _usable_elevations(survey_results)

    if not home_usable or not path_usable or not survey_usable:
        result.info.append(
            "Terrain data unavailable for this area; RTH/terrain elevation checks were skipped."
        )
        return result

    home_elev_m = home_result.elevation_m
    max_path_terrain_m = max(path_usable)
    max_survey_terrain_m = max(survey_usable)

    # Check 1: RTH altitude vs. terrain relief on the direct return path.
    rth_msl_m = home_elev_m + rth_altitude_ft * 0.3048
    clearance_m = rth_msl_m - max_path_terrain_m
    if clearance_m < 0:
        result.valid = False
        result.violations.append(
            f"RTH altitude ({rth_altitude_ft:.0f} ft AGL from home) would be "
            f"{abs(clearance_m):.1f} m below the highest terrain on the return path "
            f"from the farthest waypoint; raise the RTH height to avoid a collision"
        )
    elif clearance_m < clearance_margin_m:
        result.warnings.append(
            f"RTH altitude clears the highest terrain on the return path by only "
            f"{clearance_m:.1f} m (recommended margin {clearance_margin_m:.0f} m); "
            f"consider raising the RTH height"
        )

    # Check 2: home-point elevation vs. highest terrain in the survey area.
    relief_m = max_survey_terrain_m - home_elev_m
    if relief_m > 0:
        cruise_msl_m = home_elev_m + altitude_ft * 0.3048
        cruise_clearance_m = cruise_msl_m - max_survey_terrain_m
        if cruise_clearance_m < 0:
            result.warnings.append(
                f"Home point sits {relief_m:.1f} m below the highest terrain in the "
                f"survey area; at the planned cruise altitude ({altitude_ft:.0f} ft AGL) "
                f"the aircraft would fly below that terrain elsewhere in the survey area"
            )

    return result


# ---------------------------------------------------------------------------
# Battery estimation
# ---------------------------------------------------------------------------


def estimate_batteries(
    total_distance_m: float,
    flight_speed_ms: float = 10.0,
    battery_flight_time_s: float = 1200,
) -> float:
    """Deterministic battery estimate from total distance and flight budget.

    Defaults assume ~10 m/s cruise speed and 20-minute battery budget.
    """
    if total_distance_m <= 0:
        return 0.0
    time_needed_s = total_distance_m / flight_speed_ms
    batteries = time_needed_s / battery_flight_time_s
    return round(batteries, 2)


# ---------------------------------------------------------------------------
# Multi-battery segmentation
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    index: int
    lanes_geojson: str
    from_lane: int
    to_lane: int
    distance_m: float
    landing_wpt: tuple[float, float] | None = None
    resume_wpt: tuple[float, float] | None = None


def segment_plan(
    lanes_geojson: str,
    total_distance_m: float,
    battery_range_m: float = 3000,
    fov_h_deg: float = 84.0,
) -> list[Segment]:
    """Split lawnmower lanes into sequential battery-sized sub-missions.

    Uses a simple deterministic approach: divide lanes evenly by count
    so each segment's distance stays within battery_range_m.
    """
    geo = json.loads(lanes_geojson)
    geometries = geo.get("geometries", [])
    lane_count = len(geometries)

    if lane_count == 0:
        return []

    avg_dist_per_lane = total_distance_m / lane_count if lane_count else 0
    if avg_dist_per_lane <= 0 or total_distance_m <= battery_range_m:
        # Fits in one battery
        return [
            Segment(
                index=0,
                lanes_geojson=lanes_geojson,
                from_lane=0,
                to_lane=lane_count - 1,
                distance_m=total_distance_m,
            )
        ]

    lanes_per_segment = max(1, int(lane_count * battery_range_m / total_distance_m))
    segments: list[Segment] = []

    for seg_idx in range(0, lane_count, lanes_per_segment):
        seg_lanes = geometries[seg_idx : seg_idx + lanes_per_segment]
        if not seg_lanes:
            break
        from_idx = seg_idx
        to_idx = seg_idx + len(seg_lanes) - 1

        seg_geojson = json.dumps({
            "type": "GeometryCollection",
            "geometries": seg_lanes,
        })

        seg_distance = len(seg_lanes) * avg_dist_per_lane

        landing_wpt = None
        resume_wpt = None
        if to_idx < lane_count - 1:
            last_coords = seg_lanes[-1]["coordinates"]
            landing_wpt = (last_coords[-1][0], last_coords[-1][1])
            next_start = geometries[to_idx + 1]["coordinates"][0]
            resume_wpt = (next_start[0], next_start[1])

        segments.append(Segment(
            index=len(segments),
            lanes_geojson=seg_geojson,
            from_lane=from_idx,
            to_lane=to_idx,
            distance_m=round(seg_distance, 1),
            landing_wpt=landing_wpt,
            resume_wpt=resume_wpt,
        ))

    return segments


# ---------------------------------------------------------------------------
# Gap-based re-fly plan generation
# ---------------------------------------------------------------------------


def generate_lawnmower_from_gaps(
    gap_geojson: str,
    altitude_ft: float,
    side_overlap: float,
    forward_overlap: float,
    fov_h_deg: float = 84.0,
    fov_v_deg: float = 64.0,
) -> dict | None:
    """Generate a lawnmower plan covering only gap polygons.

    Reuses generate_lawnmower against gap geometry instead of the full
    TargetArea. Returns None if gap_geojson is empty/null.
    """
    if not gap_geojson or gap_geojson.strip() in ("", "null", "{}"):
        return None

    gap = json.loads(gap_geojson)

    # gap_geojson may be a FeatureCollection of gap polygons, a single
    # Polygon/MultiPolygon, or a GeometryCollection. Try to extract the
    # union bounding box or the first usable polygon.
    features = []
    if gap.get("type") == "FeatureCollection":
        features = gap.get("features", [])
    elif gap.get("type") == "GeometryCollection":
        features = gap.get("geometries", [])
    elif gap.get("type") in ("Polygon", "MultiPolygon"):
        features = [gap]

    if not features:
        return None

    # Use the first feature/geometry as the target
    first = features[0]
    if isinstance(first, dict) and "geometry" in first:
        feat_geom = first["geometry"]
    else:
        feat_geom = first

    if feat_geom.get("type") not in ("Polygon", "MultiPolygon"):
        return None

    target_geojson = json.dumps(feat_geom)

    result = generate_lawnmower(
        target_geojson=target_geojson,
        altitude_ft=altitude_ft,
        side_overlap=side_overlap,
        forward_overlap=forward_overlap,
        fov_h_deg=fov_h_deg,
        fov_v_deg=fov_v_deg,
    )

    result["source"] = "gap_re_fly"
    return result