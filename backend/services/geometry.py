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
) -> dict:
    """Compute ground footprint polygon for a nadir photo.

    Returns dict with geom_wkt (UTM), geom_geojson (WGS84), ground dimensions,
    and heading_estimated flag.
    """
    ground_width_m = 2 * altitude_m * math.tan(math.radians(fov_horizontal_deg / 2))
    ground_height_m = 2 * altitude_m * math.tan(math.radians(fov_vertical_deg / 2))

    to_utm = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    to_wgs = Transformer.from_crs(target_crs, "EPSG:4326", always_xy=True)

    cx, cy = to_utm.transform(lon, lat)

    hw = ground_width_m / 2
    hh = ground_height_m / 2
    poly_utm = Polygon([
        (cx - hw, cy - hh),
        (cx + hw, cy - hh),
        (cx + hw, cy + hh),
        (cx - hw, cy + hh),
        (cx - hw, cy - hh),
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
        "ground_width_m": ground_width_m,
        "ground_height_m": ground_height_m,
        "heading_estimated": heading_estimated,
    }
