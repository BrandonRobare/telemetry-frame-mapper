from __future__ import annotations

import json
import math
from types import SimpleNamespace

import numpy as np
import pytest
from pyproj import Transformer

from backend.services.cesium_tiles import (
    build_tileset,
    enu_to_ecef_transform,
    geodetic_to_ecef,
)
from backend.services.reconstruction import _LOCAL_FRAME_GEO, NotGeoreferencedError

# 3D Tiles 1.1, "glTF transforms": glTF content is y-up, and the runtime rotates it
# to z-up, (x, y, z) -> (x, -z, y), before applying the tile transform. Row-major.
_Y_UP_TO_Z_UP = np.array(
    [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, -1.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
)

# Mesh vertices in the COLMAP frame; about 100 m across once scaled.
_COLMAP_POINTS = [
    (0.0, 0.0, 0.0),
    (12.0, -5.0, 3.0),
    (-20.0, 8.0, -4.0),
    (15.0, 15.0, 15.0),
    (-9.0, -18.0, 6.0),
]


def _img(lat, lon, alt):
    return SimpleNamespace(latitude=lat, longitude=lon, altitude_m=alt)


def _rotation(yaw_deg: float, tilt_deg: float) -> np.ndarray:
    a, b = math.radians(yaw_deg), math.radians(tilt_deg)
    rz = np.array([[math.cos(a), -math.sin(a), 0.0], [math.sin(a), math.cos(a), 0.0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0.0, math.cos(b), -math.sin(b)], [0.0, math.sin(b), math.cos(b)]])
    return rz @ rx


def _geo(zone: str = "33N", origin: tuple[float, float] = (650123.0, 4649776.0)) -> dict:
    """A solved COLMAP->UTM similarity with a yaw, a tilt, a scale and a translation."""
    return {
        "scale": 2.5,
        "rotation": _rotation(40.0, 15.0).tolist(),
        "translation": [3.0, -7.0, 12.0],
        "utm_zone": zone,
        "utm_origin": list(origin),
        "rmse_m": 0.4,
        "trimmed_point_count": 0,
    }


def _utm_epsg(zone: str) -> int:
    return (32600 if zone.endswith("N") else 32700) + int(zone[:-1])


def _expected_ecef(geo: dict, point) -> np.ndarray:
    """Place one COLMAP point on the globe without going through build_tileset."""
    local = geo["scale"] * (np.array(geo["rotation"]) @ np.array(point)) + geo["translation"]
    easting = local[0] + geo["utm_origin"][0]
    northing = local[1] + geo["utm_origin"][1]
    to_lonlat = Transformer.from_crs(_utm_epsg(geo["utm_zone"]), 4326, always_xy=True)
    lon, lat = to_lonlat.transform(easting, northing)
    return np.array(geodetic_to_ecef(math.radians(lat), math.radians(lon), float(local[2])))


def _images_near(geo: dict) -> list:
    to_lonlat = Transformer.from_crs(_utm_epsg(geo["utm_zone"]), 4326, always_xy=True)
    lon, lat = to_lonlat.transform(*geo["utm_origin"])
    return [_img(lat - 0.0005, lon - 0.0005, 60.0), _img(lat + 0.0005, lon + 0.0005, 80.0)]


def test_geodetic_to_ecef_equator_prime_meridian():
    x, y, z = geodetic_to_ecef(0.0, 0.0, 0.0)
    assert math.isclose(x, 6378137.0, abs_tol=1e-6)
    assert math.isclose(y, 0.0, abs_tol=1e-6)
    assert math.isclose(z, 0.0, abs_tol=1e-6)


def test_geodetic_to_ecef_north_pole():
    x, y, z = geodetic_to_ecef(math.pi / 2, 0.0, 0.0)
    assert abs(x) < 1.0
    assert abs(y) < 1.0
    assert abs(z - 6356752.3) < 1.0


def test_enu_to_ecef_transform_is_16_numbers_column_major_translation():
    lat0, lon0, h0 = math.radians(37.0), math.radians(-122.0), 50.0
    t = enu_to_ecef_transform(lat0, lon0, h0)
    assert len(t) == 16
    expected_translation = geodetic_to_ecef(lat0, lon0, h0)
    assert t[12:15] == list(expected_translation)
    assert t[15] == 1.0


@pytest.mark.parametrize(
    ("zone", "origin"),
    [
        ("33N", (650123.0, 4649776.0)),  # east of the zone's central meridian
        ("56S", (334567.0, 6251234.0)),  # southern hemisphere, west of it
    ],
)
def test_build_tileset_root_transform_is_the_georeferenced_ecef_placement(zone, origin):
    geo = _geo(zone, origin)
    tileset = build_tileset(_images_near(geo), "artifacts/mesh.glb", geo_transform=geo)

    # 3D Tiles stores the matrix column-major.
    root = np.array(tileset["root"]["transform"], dtype=np.float64).reshape(4, 4).T
    for point in _COLMAP_POINTS:
        placed = root @ _Y_UP_TO_Z_UP @ np.array([*point, 1.0])
        error_m = np.linalg.norm(placed[:3] - _expected_ecef(geo, point))
        assert error_m < 0.01, f"{point} lands {error_m:.3f} m from its georeferenced position"


def test_build_tileset_accepts_the_stored_json_column():
    geo = _geo()
    from_dict = build_tileset(_images_near(geo), None, geo_transform=geo)
    from_column = build_tileset(_images_near(geo), None, geo_transform=json.dumps(geo))
    assert from_column["root"]["transform"] == from_dict["root"]["transform"]


@pytest.mark.parametrize(
    "geo_transform",
    [None, "", "not json", _LOCAL_FRAME_GEO, {**_geo(), "utm_zone": "unknown"}],
    ids=["null", "empty", "malformed", "local-frame-identity", "no-utm-zone"],
)
def test_build_tileset_refuses_a_reconstruction_that_is_not_georeferenced(geo_transform):
    with pytest.raises(NotGeoreferencedError, match="georeferenced"):
        build_tileset([_img(10.0, 20.0, 100.0)], "artifacts/mesh.glb", geo_transform=geo_transform)


def test_build_tileset_region_order_and_radians():
    images = [_img(10.0, 20.0, 100.0), _img(11.0, 21.0, 150.0)]
    tileset = build_tileset(images, content_uri=None, geo_transform=_geo())
    west, south, east, north, min_h, max_h = tileset["root"]["boundingVolume"]["region"]
    assert west == math.radians(20.0)
    assert east == math.radians(21.0)
    assert south == math.radians(10.0)
    assert north == math.radians(11.0)
    assert min_h == 100.0
    assert max_h == 150.0


def test_build_tileset_geometric_error_positive():
    images = [_img(10.0, 20.0, 100.0), _img(11.0, 21.0, 150.0)]
    tileset = build_tileset(images, content_uri=None, geo_transform=_geo())
    assert tileset["geometricError"] > 0
    assert tileset["root"]["geometricError"] > 0


def test_build_tileset_no_content_when_uri_missing():
    images = [_img(10.0, 20.0, 100.0)]
    tileset = build_tileset(images, content_uri=None, geo_transform=_geo())
    assert "content" not in tileset["root"]
    # not the degenerate stub
    assert tileset["root"]["boundingVolume"]["region"] != [0, 0, 0, 0, 0, 0]


def test_build_tileset_content_uri_set_when_glb_bundled():
    images = [_img(10.0, 20.0, 100.0)]
    tileset = build_tileset(images, content_uri="artifacts/mesh.glb", geo_transform=_geo())
    assert tileset["root"]["content"]["uri"] == "artifacts/mesh.glb"


def test_build_tileset_asset_version_1_1():
    images = [_img(10.0, 20.0, 100.0)]
    tileset = build_tileset(images, content_uri=None, geo_transform=_geo())
    assert tileset["asset"]["version"] == "1.1"


def test_build_tileset_raises_without_gps():
    with pytest.raises(ValueError):
        build_tileset([], content_uri=None, geo_transform=_geo())
