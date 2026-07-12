from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.db.models import FlightLog, FlightLogPoint
from backend.db.models import Session as SessionModel


def _get_db(client):
    from backend.db.database import get_db
    from backend.main import app
    return next(app.dependency_overrides[get_db]())


def _make_session(db, name: str = "Battery Test") -> SessionModel:
    s = SessionModel(name=name, folder_path="/tmp/batt", photo_count=1, usable_count=1)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


_ENTRY_BODY = {
    "battery_id": "B-03",
    "start_pct": 98.0,
    "end_pct": 34.0,
    "duration_s": 1080.0,
    "notes": "Windy, hover-heavy lawnmower pass",
}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def test_create_flight_entry_happy_path(client):
    db = _get_db(client)
    s = _make_session(db)

    resp = client.post(f"/sessions/{s.id}/flight-entries", json=_ENTRY_BODY)
    assert resp.status_code == 201
    data = resp.json()
    assert data["battery_id"] == "B-03"
    assert data["start_pct"] == pytest.approx(98.0)
    assert data["end_pct"] == pytest.approx(34.0)
    assert data["duration_s"] == pytest.approx(1080.0)
    assert data["notes"] == "Windy, hover-heavy lawnmower pass"
    assert data["session_id"] == s.id
    assert "id" in data
    assert "created_at" in data


def test_create_flight_entry_session_not_found(client):
    resp = client.post("/sessions/999999/flight-entries", json=_ENTRY_BODY)
    assert resp.status_code == 404


def test_create_flight_entry_minimal_body(client):
    db = _get_db(client)
    s = _make_session(db)
    resp = client.post(f"/sessions/{s.id}/flight-entries", json={"battery_id": "B-01"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["battery_id"] == "B-01"
    assert data["start_pct"] is None
    assert data["end_pct"] is None
    assert data["notes"] is None


def test_create_flight_entry_rejects_out_of_range_pct(client):
    db = _get_db(client)
    s = _make_session(db)
    resp = client.post(
        f"/sessions/{s.id}/flight-entries",
        json={"battery_id": "B-01", "start_pct": 120.0},
    )
    assert resp.status_code == 422
    resp = client.post(
        f"/sessions/{s.id}/flight-entries",
        json={"battery_id": "B-01", "end_pct": -5.0},
    )
    assert resp.status_code == 422


def test_create_flight_entry_rejects_negative_duration(client):
    db = _get_db(client)
    s = _make_session(db)
    resp = client.post(
        f"/sessions/{s.id}/flight-entries",
        json={"battery_id": "B-01", "duration_s": -1.0},
    )
    assert resp.status_code == 422


def test_create_flight_entry_derives_duration_from_flight_log(client):
    """When duration_s is omitted, derive it from the session's flight log span."""
    db = _get_db(client)
    s = _make_session(db)
    log = FlightLog(session_id=s.id, filename="FlightRecord.csv", format="dji_csv")
    db.add(log)
    db.commit()
    db.refresh(log)
    t0 = datetime(2026, 7, 1, 14, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 7, 1, 14, 12, 30, tzinfo=timezone.utc)
    db.add_all([
        FlightLogPoint(flight_log_id=log.id, timestamp=t0, latitude=35.0, longitude=-80.0),
        FlightLogPoint(flight_log_id=log.id, timestamp=t1, latitude=35.001, longitude=-80.001),
    ])
    db.commit()

    resp = client.post(f"/sessions/{s.id}/flight-entries", json={"battery_id": "B-02"})
    assert resp.status_code == 201
    assert resp.json()["duration_s"] == pytest.approx(750.0)


def test_create_flight_entry_no_flight_log_leaves_duration_null(client):
    db = _get_db(client)
    s = _make_session(db)
    resp = client.post(f"/sessions/{s.id}/flight-entries", json={"battery_id": "B-02"})
    assert resp.status_code == 201
    assert resp.json()["duration_s"] is None


def test_create_flight_entry_explicit_duration_wins_over_derived(client):
    db = _get_db(client)
    s = _make_session(db)
    log = FlightLog(session_id=s.id, filename="FlightRecord.csv", format="dji_csv")
    db.add(log)
    db.commit()
    db.refresh(log)
    t0 = datetime(2026, 7, 1, 14, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 7, 1, 14, 10, 0, tzinfo=timezone.utc)
    db.add_all([
        FlightLogPoint(flight_log_id=log.id, timestamp=t0, latitude=35.0, longitude=-80.0),
        FlightLogPoint(flight_log_id=log.id, timestamp=t1, latitude=35.001, longitude=-80.001),
    ])
    db.commit()

    resp = client.post(
        f"/sessions/{s.id}/flight-entries",
        json={"battery_id": "B-02", "duration_s": 42.0},
    )
    assert resp.status_code == 201
    assert resp.json()["duration_s"] == pytest.approx(42.0)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

def test_list_flight_entries_empty(client):
    db = _get_db(client)
    s = _make_session(db)
    resp = client.get(f"/sessions/{s.id}/flight-entries")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_flight_entries_multiple(client):
    db = _get_db(client)
    s = _make_session(db)
    client.post(f"/sessions/{s.id}/flight-entries", json={**_ENTRY_BODY, "battery_id": "B-01"})
    client.post(f"/sessions/{s.id}/flight-entries", json={**_ENTRY_BODY, "battery_id": "B-02"})
    resp = client.get(f"/sessions/{s.id}/flight-entries")
    assert resp.status_code == 200
    ids = [e["battery_id"] for e in resp.json()]
    assert "B-01" in ids
    assert "B-02" in ids


def test_list_flight_entries_isolation(client):
    db = _get_db(client)
    s1 = _make_session(db, "A")
    s2 = _make_session(db, "B")
    client.post(f"/sessions/{s1.id}/flight-entries", json=_ENTRY_BODY)
    resp = client.get(f"/sessions/{s2.id}/flight-entries")
    assert resp.json() == []


def test_list_flight_entries_session_not_found(client):
    resp = client.get("/sessions/999999/flight-entries")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_flight_entry_happy_path(client):
    db = _get_db(client)
    s = _make_session(db)
    create_resp = client.post(f"/sessions/{s.id}/flight-entries", json=_ENTRY_BODY)
    entry_id = create_resp.json()["id"]

    resp = client.delete(f"/sessions/{s.id}/flight-entries/{entry_id}")
    assert resp.status_code == 200

    list_resp = client.get(f"/sessions/{s.id}/flight-entries")
    assert entry_id not in [e["id"] for e in list_resp.json()]


def test_delete_flight_entry_not_found(client):
    db = _get_db(client)
    s = _make_session(db)
    resp = client.delete(f"/sessions/{s.id}/flight-entries/999999")
    assert resp.status_code == 404


def test_delete_flight_entry_wrong_session(client):
    db = _get_db(client)
    s1 = _make_session(db, "A")
    s2 = _make_session(db, "B")
    create_resp = client.post(f"/sessions/{s1.id}/flight-entries", json=_ENTRY_BODY)
    entry_id = create_resp.json()["id"]

    resp = client.delete(f"/sessions/{s2.id}/flight-entries/{entry_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Model cascade
# ---------------------------------------------------------------------------

def test_flight_entry_cascade_delete_with_session(client):
    from backend.db.models import FlightEntry

    db = _get_db(client)
    s = _make_session(db)
    entry = FlightEntry(session_id=s.id, battery_id="B-09")
    db.add(entry)
    db.commit()
    entry_id = entry.id

    db.delete(s)
    db.commit()

    assert db.query(FlightEntry).filter(FlightEntry.id == entry_id).first() is None
