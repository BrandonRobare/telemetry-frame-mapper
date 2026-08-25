from __future__ import annotations

_POLYGON = '{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'
_MULTIPOLYGON = (
    '{"type":"MultiPolygon","coordinates":['
    '[[[0,0],[1,0],[1,1],[0,1],[0,0]]],'
    '[[[2,2],[3,2],[3,3],[2,3],[2,2]]]'
    "]}"
)
_POINT = '{"type":"Point","coordinates":[0,0]}'
_EMPTY_RING_POLYGON = '{"type":"Polygon","coordinates":[]}'


def test_create_rejects_malformed_json(client):
    resp = client.post("/target-areas/", json={"name": "x", "geom_geojson": "not json"})
    assert resp.status_code == 422


def test_create_rejects_point_geometry(client):
    resp = client.post("/target-areas/", json={"name": "x", "geom_geojson": _POINT})
    assert resp.status_code == 422


def test_create_rejects_empty_ring_polygon(client):
    resp = client.post("/target-areas/", json={"name": "x", "geom_geojson": _EMPTY_RING_POLYGON})
    assert resp.status_code == 422


def test_create_accepts_polygon(client):
    resp = client.post("/target-areas/", json={"name": "field", "geom_geojson": _POLYGON})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "field"
    assert body["geom_geojson"] == _POLYGON


def test_create_accepts_multipolygon(client):
    resp = client.post("/target-areas/", json={"name": "field2", "geom_geojson": _MULTIPOLYGON})
    assert resp.status_code == 200
