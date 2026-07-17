from __future__ import annotations

import csv
import io

from backend.db.models import Reconstruction
from backend.db.models import Session as SessionModel


def _get_db(client):
    from backend.db.database import get_db
    from backend.main import app
    return next(app.dependency_overrides[get_db]())


def _make_reconstruction(db) -> Reconstruction:
    s = SessionModel(name="Meas Export Test", folder_path="/tmp/me", photo_count=1, usable_count=1)
    db.add(s)
    db.commit()
    db.refresh(s)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete", progress_pct=100.0, frames_used=1
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


_DIST_BODY = {
    "kind": "distance",
    "points": [
        {"x": 0.0, "y": 0.0, "z": 0.0, "lat": 35.0, "lon": -80.0, "alt": 100.0},
        {"x": 10.0, "y": 0.0, "z": 0.0, "lat": 35.001, "lon": -80.0, "alt": 100.0},
    ],
    "value": 111.0,
    "unit": "m",
    "label": "Roof span",
}

_POINT_BODY_NO_GPS = {
    "kind": "point",
    "points": [{"x": 5.0, "y": 1.0, "z": 5.0}],
}


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def test_export_measurements_csv_empty(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    resp = client.get(f"/export/reconstructions/{rec.id}/measurements.csv")
    assert resp.status_code == 200
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert rows[0] == ["id", "kind", "label", "value", "unit", "created_at", "points"]
    assert len(rows) == 1


def test_export_measurements_csv_with_rows(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    client.post(f"/reconstruction/{rec.id}/measurements", json=_DIST_BODY)

    resp = client.get(f"/export/reconstructions/{rec.id}/measurements.csv")
    assert resp.status_code == 200
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert len(rows) == 2
    header, row = rows
    assert row[header.index("kind")] == "distance"
    assert row[header.index("label")] == "Roof span"
    assert row[header.index("value")] == "111.0"
    assert row[header.index("unit")] == "m"


def test_export_measurements_csv_reconstruction_not_found(client):
    resp = client.get("/export/reconstructions/999999/measurements.csv")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GeoJSON export
# ---------------------------------------------------------------------------


def test_export_measurements_geojson_empty(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    resp = client.get(f"/export/reconstructions/{rec.id}/measurements.geojson")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert data["features"] == []


def test_export_measurements_geojson_distance_is_linestring(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    client.post(f"/reconstruction/{rec.id}/measurements", json=_DIST_BODY)

    resp = client.get(f"/export/reconstructions/{rec.id}/measurements.geojson")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["features"]) == 1
    feat = data["features"][0]
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] == "LineString"
    assert feat["geometry"]["coordinates"][0] == [-80.0, 35.0, 100.0]
    assert feat["properties"]["label"] == "Roof span"
    assert feat["properties"]["value"] == 111.0
    assert feat["properties"]["unit"] == "m"


def test_export_measurements_geojson_skips_points_without_gps(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    client.post(f"/reconstruction/{rec.id}/measurements", json=_POINT_BODY_NO_GPS)

    resp = client.get(f"/export/reconstructions/{rec.id}/measurements.geojson")
    assert resp.status_code == 200
    assert resp.json()["features"] == []


def test_export_measurements_geojson_reconstruction_not_found(client):
    resp = client.get("/export/reconstructions/999999/measurements.geojson")
    assert resp.status_code == 404
