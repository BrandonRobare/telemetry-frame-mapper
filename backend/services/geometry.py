from __future__ import annotations

import json
import logging
import math

import pyproj
from pyproj import Transformer
from shapely.affinity import rotate
from shapely.geometry import Polygon, mapping

logger = logging.getLogger(__name__)


def utm_crs_for(lon: float, lat: float) -> pyproj.CRS:
    """UTM CRS covering a WGS84 point.  Shared by footprints and coverage."""
    zone = int((lon + 180) / 6) + 1
    return pyproj.CRS.from_dict({"proj": "utm", "zone": zone, "south": lat < 0.0})


def _resolve_crs(lon: float, lat: float, target_crs: str | None) -> pyproj.CRS:
    """Projected CRS to build a footprint in at (lon, lat).

    An explicitly configured *target_crs* wins, but only where it actually
    applies: projecting a flight into a distant UTM zone inflates the polygon
    (~5% at 24° off the central meridian) while ground_width_m — computed from
    altitude and FOV — stays correct, so the two silently disagree (#640).
    """
    if target_crs is None:
        return utm_crs_for(lon, lat)
    crs = pyproj.CRS.from_user_input(target_crs)
    area = crs.area_of_use
    if area is not None:
        west, south, east, north = area.bounds
        lon_ok = (west <= lon <= east) if west <= east else (lon >= west or lon <= east)
        if not (lon_ok and south <= lat <= north):
            logger.warning(
                "target_crs %s does not cover (%.5f, %.5f); using the local UTM zone "
                "for this footprint instead",
                target_crs, lat, lon,
            )
            return utm_crs_for(lon, lat)
    return crs


def compute_footprint(
    lat: float,
    lon: float,
    altitude_m: float,
    fov_horizontal_deg: float,
    fov_vertical_deg: float,
    yaw_deg: float | None,
    target_crs: str | None = None,
    gimbal_pitch: float | None = None,
    ground_elevation_m: float = 0.0,
) -> dict:
    """Compute ground footprint polygon for an aerial photo.

    When gimbal_pitch is -90° (straight-down) or None, the footprint is
    a nadir rectangle centred under the drone.  For oblique captures the
    frustum is offset along the yaw vector so the footprint centre shifts
    forward, and both dimensions stretch proportionally to the slant range,
    producing an approximate trapezoid.

    *target_crs* is an optional override; by default (and whenever the given
    CRS does not cover the point) the local UTM zone is derived from lat/lon.

    Returns dict with geom_wkt (UTM), geom_geojson (WGS84), ground dimensions,
    heading_estimated flag, and a boolean `pitch_oblique` (True when the
    computed footprint assumes a non-nadir, approximate projection).

    *ground_elevation_m* is the terrain elevation at (lat, lon) in metres
    above sea level (MSL).  When provided, the effective altitude used for
    footprint math is ``altitude_m - ground_elevation_m`` (above ground level).
    If the result is ≤ 0 (rare — e.g. negative MSL valley or bad sensor data),
    the footprint dimension blows up; we clamp to 1 m AGL in that case and
    flag the result.
    """

    # ---- helpers -----------------------------------------------------------
    crs = _resolve_crs(lon, lat, target_crs)
    to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    cx, cy = to_utm.transform(lon, lat)

    # Effective AGL altitude for footprint dimensions
    agl_m = altitude_m - ground_elevation_m
    if agl_m <= 0.0:
        agl_m = 1.0  # clamp to avoid degenerate footprint

    # Pitch: -90 => straight down.  We treat abs(pitch + 90) <= 2 as nadir.
    is_oblique = (
        gimbal_pitch is not None
        and abs(gimbal_pitch + 90) > 2
    )
    if is_oblique:
        # Convert to radians from vertical: 0 = nadir, positive = forward tilt
        tilt_rad = math.radians(90 + gimbal_pitch)
        slant = agl_m / max(math.cos(tilt_rad), 0.001)
        ground_offset = agl_m * math.tan(tilt_rad)

        # Angular FOV spread at the slant range is wider
        ground_width_m = 2 * slant * math.tan(math.radians(fov_horizontal_deg / 2))
        ground_height_m = 2 * slant * math.tan(math.radians(fov_vertical_deg / 2))

        # Direction of the offset: along the yaw vector (0 = north, CW)
        yaw_rad = math.radians(yaw_deg) if yaw_deg else 0.0
        dx = ground_offset * math.sin(yaw_rad)
        dy = ground_offset * math.cos(yaw_rad)
    else:
        ground_width_m = 2 * agl_m * math.tan(math.radians(fov_horizontal_deg / 2))
        ground_height_m = 2 * agl_m * math.tan(math.radians(fov_vertical_deg / 2))
        dx = dy = 0.0

    hw = ground_width_m / 2
    hh = ground_height_m / 2
    poly_utm = Polygon([
        (cx + dx - hw, cy + dy - hh),
        (cx + dx + hw, cy + dy - hh),
        (cx + dx + hw, cy + dy + hh),
        (cx + dx - hw, cy + dy + hh),
        (cx + dx - hw, cy + dy - hh),
    ])

    heading_estimated = True
    if yaw_deg is not None:
        poly_utm = rotate(poly_utm, -yaw_deg, origin="centroid", use_radians=False)
        heading_estimated = False

    coords_wgs = []
    for x, y in poly_utm.exterior.coords:
        lon_out, lat_out = to_wgs.transform(x, y)
        coords_wgs.append([lon_out, lat_out])

    poly_wgs = Polygon(coords_wgs)

    return {
        "geom_wkt": poly_utm.wkt,
        "geom_geojson": json.dumps(mapping(poly_wgs)),
        "ground_width_m": round(ground_width_m, 2),
        "ground_height_m": round(ground_height_m, 2),
        "heading_estimated": heading_estimated,
        "pitch_oblique": is_oblique,
    }