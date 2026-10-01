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


# 3D Tiles 1.1 ("glTF transforms"): glTF content is y-up and the runtime rotates it
# to z-up, (x, y, z) -> (x, -z, y), before applying the tile transform. Row-major.
_GLTF_Y_UP_TO_Z_UP = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 0.0, -1.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)


def georeferenced_root_transform(geo_transform: dict) -> list[float]:
    """Column-major 4x4 placing COLMAP-frame glTF content at its solved ECEF position.

    The mesh keeps COLMAP's coordinates (the frame mesh_georef.json describes), so the
    matrix is, applied right to left: undo the runtime's glTF y-up -> z-up rotation;
    COLMAP -> UTM through reconstruction._world_points_to_utm; UTM -> a local
    East-North-Up frame at the transform's UTM origin (grid convergence and scale
    factor, linearised there); ENU -> ECEF. Heights keep the transform's vertical
    frame, taken as ellipsoidal height. One affine matrix cannot follow the Earth's
    curvature, so a point d metres from the origin sits about d**2 / 2R too high: under
    1 cm within 350 m, 3 cm at 600 m.
    """
    import numpy as np
    from pyproj import Transformer

    from backend.services.reconstruction import _utm_epsg, _world_points_to_utm

    origin_e, origin_n = (float(v) for v in geo_transform["utm_origin"])
    to_lonlat = Transformer.from_crs(
        _utm_epsg(str(geo_transform["utm_zone"])), 4326, always_xy=True
    )
    lon0, lat0 = to_lonlat.transform(origin_e, origin_n)
    lat0_rad, lon0_rad = math.radians(lat0), math.radians(lon0)
    enu_to_ecef = np.array(enu_to_ecef_transform(lat0_rad, lon0_rad, 0.0)).reshape(4, 4).T
    anchor = np.array(geodetic_to_ecef(lat0_rad, lon0_rad, 0.0))

    # COLMAP -> UTM, read off the shared helper as an affine map relative to the origin.
    corners = _world_points_to_utm(np.vstack([np.zeros(3), np.eye(3)]), geo_transform)
    corners = corners - np.array([origin_e, origin_n, 0.0])
    colmap_to_utm = np.eye(4)
    colmap_to_utm[:3, :3] = (corners[1:] - corners[0]).T
    colmap_to_utm[:3, 3] = corners[0]

    # UTM easting/northing offsets -> local east/north metres, by central differences.
    def _east_north(de: float, dn: float) -> np.ndarray:
        lon, lat = to_lonlat.transform(origin_e + de, origin_n + dn)
        offset = np.array(geodetic_to_ecef(math.radians(lat), math.radians(lon), 0.0)) - anchor
        return enu_to_ecef[:3, :2].T @ offset

    utm_to_enu = np.eye(4)
    utm_to_enu[:2, 0] = (_east_north(1.0, 0.0) - _east_north(-1.0, 0.0)) / 2.0
    utm_to_enu[:2, 1] = (_east_north(0.0, 1.0) - _east_north(0.0, -1.0)) / 2.0

    gltf_to_colmap = np.linalg.inv(np.array(_GLTF_Y_UP_TO_Z_UP))
    matrix = enu_to_ecef @ utm_to_enu @ colmap_to_utm @ gltf_to_colmap
    return [float(v) for v in matrix.T.reshape(-1)]


def build_tileset(
    images: Iterable,
    content_uri: str | None,
    *,
    geo_transform: str | dict | None,
) -> dict:
    """Build a geo-referenced 3D Tiles 1.1 tileset for a reconstruction.

    ``root.transform`` places the content with the reconstruction's solved
    COLMAP->UTM ``geo_transform`` (the stored JSON column or its dict); the image
    GPS bounds only size ``boundingVolume.region``. A NULL ``geo_transform`` means
    the reconstruction is not georeferenced, so this raises
    ``reconstruction.NotGeoreferencedError`` (a ValueError) instead of guessing.
    """
    from backend.services.reconstruction import _require_geo_transform

    geo = _require_geo_transform(geo_transform, "3D Tiles placement")
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
        "transform": georeferenced_root_transform(geo),
    }
    if content_uri:
        root["content"] = {"uri": content_uri}

    return {
        "asset": {"version": "1.1"},
        "geometricError": geometric_error,
        "root": root,
    }
