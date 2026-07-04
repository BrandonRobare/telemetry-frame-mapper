from __future__ import annotations

import json
import math

from pyproj import Transformer
from shapely.affinity import rotate
from shapely.geometry import Polygon, mapping


def compute_footprint(
    lat: float,
    lon: float,
    altitude_m: float,
    fov_horizontal_deg: float,
    fov_vertical_deg: float,
    yaw_deg: float | None,
    target_crs: str,
    gimbal_pitch: float | None = None,
) -> dict:
    """Compute ground footprint polygon for an aerial photo.

    When gimbal_pitch is -90° (straight-down) or None, the footprint is
    a nadir rectangle centred under the drone.  For oblique captures the
    frustum is offset along the yaw vector so the footprint centre shifts
    forward, and both dimensions stretch proportionally to the slant range,
    producing an approximate trapezoid.

    Returns dict with geom_wkt (UTM), geom_geojson (WGS84), ground dimensions,
    heading_estimated flag, and a boolean `pitch_oblique` (True when the
    computed footprint assumes a non-nadir, approximate projection).
    """

    # ---- helpers -----------------------------------------------------------
    to_utm = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    to_wgs = Transformer.from_crs(target_crs, "EPSG:4326", always_xy=True)

    cx, cy = to_utm.transform(lon, lat)

    # Pitch: -90 => straight down.  We treat abs(pitch + 90) <= 2 as nadir.
    is_oblique = (
        gimbal_pitch is not None
        and abs(gimbal_pitch + 90) > 2
    )
    if is_oblique:
        # Convert to radians from vertical: 0 = nadir, positive = forward tilt
        tilt_rad = math.radians(90 + gimbal_pitch)
        slant = altitude_m / max(math.cos(tilt_rad), 0.001)
        ground_offset = altitude_m * math.tan(tilt_rad)

        # Angular FOV spread at the slant range is wider
        ground_width_m = 2 * slant * math.tan(math.radians(fov_horizontal_deg / 2))
        ground_height_m = 2 * slant * math.tan(math.radians(fov_vertical_deg / 2))

        # Direction of the offset: along the yaw vector (0 = north, CW)
        yaw_rad = math.radians(yaw_deg) if yaw_deg else 0.0
        dx = ground_offset * math.sin(yaw_rad)
        dy = ground_offset * math.cos(yaw_rad)
    else:
        ground_width_m = 2 * altitude_m * math.tan(math.radians(fov_horizontal_deg / 2))
        ground_height_m = 2 * altitude_m * math.tan(math.radians(fov_vertical_deg / 2))
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