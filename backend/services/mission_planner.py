from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from shapely.geometry import shape


def generate_lawnmower(
    target_geojson: str,
    altitude_ft: float,
    side_overlap: float,
    forward_overlap: float,
    fov_h_deg: float = 84.0,
    fov_v_deg: float = 64.0,
) -> dict:
    """Returns lanes_geojson, lane_count, total_distance_m, waypoint_spacing_m."""
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

    minx, miny, maxx, maxy = bounds
    lanes = []
    x = minx + lane_spacing_deg / 2
    direction = 1
    while x <= maxx:
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

    return {
        "lanes_geojson": json.dumps({
            "type": "GeometryCollection",
            "geometries": [{"type": "LineString", "coordinates": ln} for ln in lanes],
        }),
        "lane_count": len(lanes),
        "total_distance_m": round(total_dist, 1),
        "waypoint_spacing_m": round(waypoint_spacing_m, 2),
    }


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