from __future__ import annotations

import math
from types import SimpleNamespace

from backend.services.cesium_tiles import (
    build_tileset,
    enu_to_ecef_transform,
    geodetic_to_ecef,
)


def _img(lat, lon, alt):
    return SimpleNamespace(latitude=lat, longitude=lon, altitude_m=alt)


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


def test_build_tileset_region_order_and_radians():
    images = [_img(10.0, 20.0, 100.0), _img(11.0, 21.0, 150.0)]
    tileset = build_tileset(images, content_uri=None)
    west, south, east, north, min_h, max_h = tileset["root"]["boundingVolume"]["region"]
    assert west == math.radians(20.0)
    assert east == math.radians(21.0)
    assert south == math.radians(10.0)
    assert north == math.radians(11.0)
    assert min_h == 100.0
    assert max_h == 150.0


def test_build_tileset_geometric_error_positive():
    images = [_img(10.0, 20.0, 100.0), _img(11.0, 21.0, 150.0)]
    tileset = build_tileset(images, content_uri=None)
    assert tileset["geometricError"] > 0
    assert tileset["root"]["geometricError"] > 0


def test_build_tileset_no_content_when_uri_missing():
    images = [_img(10.0, 20.0, 100.0)]
    tileset = build_tileset(images, content_uri=None)
    assert "content" not in tileset["root"]
    # not the degenerate stub
    assert tileset["root"]["boundingVolume"]["region"] != [0, 0, 0, 0, 0, 0]


def test_build_tileset_content_uri_set_when_glb_bundled():
    images = [_img(10.0, 20.0, 100.0)]
    tileset = build_tileset(images, content_uri="artifacts/mesh.glb")
    assert tileset["root"]["content"]["uri"] == "artifacts/mesh.glb"


def test_build_tileset_asset_version_1_1():
    images = [_img(10.0, 20.0, 100.0)]
    tileset = build_tileset(images, content_uri=None)
    assert tileset["asset"]["version"] == "1.1"


def test_build_tileset_raises_without_gps():
    import pytest

    with pytest.raises(ValueError):
        build_tileset([], content_uri=None)
