from __future__ import annotations

import math
from collections.abc import Iterable

# WGS84 ellipsoid constants.
_A = 6378137.0
_F = 1 / 298.257223563
_E2 = _F * (2 - _F)

_METERS_PER_DEGREE_LAT = 111_320.0  # good enough for a geometricError hint, not for geodesy


def geodetic_to_ecef(lat_rad: float, lon_rad: float, h: float) -> tuple[float, float, float]:
    """WGS84 geodetic (radians, meters) -> ECEF (meters)."""
    sin_lat = math.sin(lat_rad)
    n = _A / math.sqrt(1 - _E2 * sin_lat * sin_lat)
    x = (n + h) * math.cos(lat_rad) * math.cos(lon_rad)
    y = (n + h) * math.cos(lat_rad) * math.sin(lon_rad)
    z = (n * (1 - _E2) + h) * sin_lat
    return x, y, z


def enu_to_ecef_transform(lat0_rad: float, lon0_rad: float, h0: float) -> list[float]:
    """Column-major 4x4 Cesium transform placing a local East-North-Up frame at (lat0, lon0, h0)."""
    sin_lat, cos_lat = math.sin(lat0_rad), math.cos(lat0_rad)
    sin_lon, cos_lon = math.sin(lon0_rad), math.cos(lon0_rad)
    east = (-sin_lon, cos_lon, 0.0)
    north = (-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat)
    up = (cos_lat * cos_lon, cos_lat * sin_lon, sin_lat)
    cx, cy, cz = geodetic_to_ecef(lat0_rad, lon0_rad, h0)
    return [
        east[0], east[1], east[2], 0.0,
        north[0], north[1], north[2], 0.0,
        up[0], up[1], up[2], 0.0,
        cx, cy, cz, 1.0,
    ]


def build_tileset(images: Iterable, content_uri: str | None) -> dict:
    """Build a real, geo-referenced 3D Tiles 1.1 tileset from an image GPS bounds.

    ponytail: assumes the bundled GLB sits in a local ENU-meters frame centered
    on the image GPS centroid (COLMAP's arbitrary-scale reconstruction frame is
    the known ceiling here) — a future similarity-transform fit (e.g. against
    GCPs) would refine root.transform instead of this centroid approximation.
    """
    points = [
        (img.latitude, img.longitude, img.altitude_m or 0.0)
        for img in images
        if img.latitude is not None and img.longitude is not None
    ]
    if not points:
        raise ValueError("no GPS-tagged images available to compute a geo-referenced tileset")

    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    alts = [p[2] for p in points]
    west, east = min(lons), max(lons)
    south, north = min(lats), max(lats)
    min_h, max_h = min(alts), max(alts)
    lat0 = sum(lats) / len(lats)
    lon0 = sum(lons) / len(lons)
    h0 = sum(alts) / len(alts)

    lat_span_m = (north - south) * _METERS_PER_DEGREE_LAT
    lon_span_m = (east - west) * _METERS_PER_DEGREE_LAT * math.cos(math.radians(lat0))
    geometric_error = max(math.hypot(lat_span_m, lon_span_m), 1.0)

    region = [
        math.radians(west), math.radians(south),
        math.radians(east), math.radians(north),
        min_h, max_h,
    ]
    root: dict = {
        "boundingVolume": {"region": region},
        "geometricError": geometric_error,
        "refine": "ADD",
        "transform": enu_to_ecef_transform(math.radians(lat0), math.radians(lon0), h0),
    }
    if content_uri:
        root["content"] = {"uri": content_uri}

    return {
        "asset": {"version": "1.1"},
        "geometricError": geometric_error,
        "root": root,
    }
