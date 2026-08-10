from __future__ import annotations

import pytest

from backend.db.models import Reconstruction
from backend.db.models import Session as SessionModel


def _get_db(client):
    from backend.main import app
    return app.state.test_db_session


def _make_reconstruction(db) -> Reconstruction:
    s = SessionModel(name="Ann Test", folder_path="/tmp/ann", photo_count=1, usable_count=1)
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


_ANN_BODY = {
    "label": "Tower Base", "lat": 35.123, "lon": -80.456, "alt_m": 120.5, "color": "#ff6b35"
}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def test_create_annotation_happy_path(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)

    resp = client.post(f"/reconstruction/{rec.id}/annotations", json=_ANN_BODY)
    assert resp.status_code == 201
    data = resp.json()
    assert data["label"] == "Tower Base"
    assert data["lat"] == pytest.approx(35.123)
    assert data["lon"] == pytest.approx(-80.456)
    assert data["alt_m"] == pytest.approx(120.5)
    assert data["color"] == "#ff6b35"
    assert data["reconstruction_id"] == rec.id
    assert "id" in data
    assert "created_at" in data


def test_create_annotation_reconstruction_not_found(client):
    resp = client.post("/reconstruction/999999/annotations", json=_ANN_BODY)
    assert resp.status_code == 404


def test_create_annotation_default_color(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    body = {k: v for k, v in _ANN_BODY.items() if k != "color"}
    resp = client.post(f"/reconstruction/{rec.id}/annotations", json=body)
    assert resp.status_code == 201
    assert resp.json()["color"] == "#ff6b35"


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

def test_list_annotations_empty(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    resp = client.get(f"/reconstruction/{rec.id}/annotations")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_annotations_multiple(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    client.post(f"/reconstruction/{rec.id}/annotations", json={**_ANN_BODY, "label": "A"})
    client.post(f"/reconstruction/{rec.id}/annotations", json={**_ANN_BODY, "label": "B"})
    resp = client.get(f"/reconstruction/{rec.id}/annotations")
    assert resp.status_code == 200
    labels = [a["label"] for a in resp.json()]
    assert "A" in labels
    assert "B" in labels


def test_list_annotations_isolation(client):
    db = _get_db(client)
    rec1 = _make_reconstruction(db)
    rec2 = _make_reconstruction(db)
    client.post(f"/reconstruction/{rec1.id}/annotations", json=_ANN_BODY)
    resp = client.get(f"/reconstruction/{rec2.id}/annotations")
    assert resp.json() == []


def test_list_annotations_reconstruction_not_found(client):
    resp = client.get("/reconstruction/999999/annotations")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_annotation_happy_path(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    create_resp = client.post(f"/reconstruction/{rec.id}/annotations", json=_ANN_BODY)
    ann_id = create_resp.json()["id"]

    resp = client.delete(f"/reconstruction/{rec.id}/annotations/{ann_id}")
    assert resp.status_code == 200

    list_resp = client.get(f"/reconstruction/{rec.id}/annotations")
    ids = [a["id"] for a in list_resp.json()]
    assert ann_id not in ids


def test_delete_annotation_not_found(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    resp = client.delete(f"/reconstruction/{rec.id}/annotations/999999")
    assert resp.status_code == 404


def test_delete_annotation_wrong_reconstruction(client):
    db = _get_db(client)
    rec1 = _make_reconstruction(db)
    rec2 = _make_reconstruction(db)
    create_resp = client.post(f"/reconstruction/{rec1.id}/annotations", json=_ANN_BODY)
    ann_id = create_resp.json()["id"]

    resp = client.delete(f"/reconstruction/{rec2.id}/annotations/{ann_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GeoJSON export
# ---------------------------------------------------------------------------

def test_export_geojson_empty(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    resp = client.get(f"/reconstruction/{rec.id}/annotations.geojson")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert data["features"] == []


def test_export_geojson_with_annotations(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    client.post(f"/reconstruction/{rec.id}/annotations", json=_ANN_BODY)

    resp = client.get(f"/reconstruction/{rec.id}/annotations.geojson")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 1

    feat = data["features"][0]
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] == "Point"
    # GeoJSON order: [lon, lat, alt]
    coords = feat["geometry"]["coordinates"]
    assert coords[0] == pytest.approx(-80.456)
    assert coords[1] == pytest.approx(35.123)
    assert coords[2] == pytest.approx(120.5)
    assert feat["properties"]["label"] == "Tower Base"
    assert feat["properties"]["color"] == "#ff6b35"


def test_export_geojson_reconstruction_not_found(client):
    resp = client.get("/reconstruction/999999/annotations.geojson")
    assert resp.status_code == 404
