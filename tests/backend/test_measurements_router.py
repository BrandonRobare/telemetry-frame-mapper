from __future__ import annotations

from backend.db.models import Reconstruction
from backend.db.models import Session as SessionModel


def _get_db(client):
    from backend.db.database import get_db
    from backend.main import app
    return next(app.dependency_overrides[get_db]())


def _make_reconstruction(db) -> Reconstruction:
    s = SessionModel(name="Meas Router Test", folder_path="/tmp/mr", photo_count=1, usable_count=1)
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

_AREA_BODY = {
    "kind": "area",
    "points": [
        {"x": 0.0, "y": 0.0, "z": 0.0, "lat": 35.0, "lon": -80.0, "alt": 100.0},
        {"x": 10.0, "y": 0.0, "z": 0.0, "lat": 35.0, "lon": -80.001, "alt": 100.0},
        {"x": 10.0, "y": 0.0, "z": 10.0, "lat": 35.001, "lon": -80.001, "alt": 100.0},
    ],
    "value": 250.5,
    "unit": "m2",
}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_measurement_happy_path(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)

    resp = client.post(f"/reconstruction/{rec.id}/measurements", json=_DIST_BODY)
    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "distance"
    assert data["value"] == 111.0
    assert data["unit"] == "m"
    assert data["label"] == "Roof span"
    assert data["reconstruction_id"] == rec.id
    assert len(data["points"]) == 2
    assert data["points"][0]["lat"] == 35.0
    assert "id" in data
    assert "created_at" in data


def test_create_measurement_reconstruction_not_found(client):
    resp = client.post("/reconstruction/999999/measurements", json=_DIST_BODY)
    assert resp.status_code == 404


def test_create_measurement_no_label(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    body = {k: v for k, v in _AREA_BODY.items() if k != "label"}
    resp = client.post(f"/reconstruction/{rec.id}/measurements", json=body)
    assert resp.status_code == 201
    assert resp.json()["label"] is None


def test_create_measurement_invalid_kind(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    body = {**_DIST_BODY, "kind": "volume"}
    resp = client.post(f"/reconstruction/{rec.id}/measurements", json=body)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_list_measurements_empty(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    resp = client.get(f"/reconstruction/{rec.id}/measurements")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_measurements_multiple(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    client.post(f"/reconstruction/{rec.id}/measurements", json=_DIST_BODY)
    client.post(f"/reconstruction/{rec.id}/measurements", json=_AREA_BODY)
    resp = client.get(f"/reconstruction/{rec.id}/measurements")
    assert resp.status_code == 200
    kinds = [m["kind"] for m in resp.json()]
    assert "distance" in kinds
    assert "area" in kinds


def test_list_measurements_isolation(client):
    db = _get_db(client)
    rec1 = _make_reconstruction(db)
    rec2 = _make_reconstruction(db)
    client.post(f"/reconstruction/{rec1.id}/measurements", json=_DIST_BODY)
    resp = client.get(f"/reconstruction/{rec2.id}/measurements")
    assert resp.json() == []


def test_list_measurements_reconstruction_not_found(client):
    resp = client.get("/reconstruction/999999/measurements")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_measurement_happy_path(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    create_resp = client.post(f"/reconstruction/{rec.id}/measurements", json=_DIST_BODY)
    m_id = create_resp.json()["id"]

    resp = client.delete(f"/reconstruction/{rec.id}/measurements/{m_id}")
    assert resp.status_code == 200

    list_resp = client.get(f"/reconstruction/{rec.id}/measurements")
    ids = [m["id"] for m in list_resp.json()]
    assert m_id not in ids


def test_delete_measurement_not_found(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    resp = client.delete(f"/reconstruction/{rec.id}/measurements/999999")
    assert resp.status_code == 404


def test_delete_measurement_wrong_reconstruction(client):
    db = _get_db(client)
    rec1 = _make_reconstruction(db)
    rec2 = _make_reconstruction(db)
    create_resp = client.post(f"/reconstruction/{rec1.id}/measurements", json=_DIST_BODY)
    m_id = create_resp.json()["id"]

    resp = client.delete(f"/reconstruction/{rec2.id}/measurements/{m_id}")
    assert resp.status_code == 404
