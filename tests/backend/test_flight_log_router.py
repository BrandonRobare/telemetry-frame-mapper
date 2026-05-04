from __future__ import annotations

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CSV_BYTES = (
    b"time(millisecond),OSD.latitude,OSD.longitude,OSD.altitude[m]\n"
    b"1000,35.0,-80.0,100.0\n"
    b"2000,35.001,-80.001,101.0\n"
)


def _make_session(client):
    from backend.db.database import get_db
    from backend.db.models import Session as SM
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    s = SM(name="fl_test", folder_path="/tmp", photo_count=0, usable_count=0)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _upload_log(client, session_id: int) -> dict:
    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("log.csv", CSV_BYTES, "text/csv")},
        data={"session_id": str(session_id)},
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------


def test_upload_flight_log_missing_session(client):
    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("log.csv", CSV_BYTES, "text/csv")},
        data={"session_id": "999999"},
    )
    assert resp.status_code == 404


def test_upload_flight_log_success(client):
    s = _make_session(client)
    data = _upload_log(client, s.id)
    assert data["session_id"] == s.id
    assert data["filename"] == "log.csv"
    assert data["point_count"] == 2
    assert "id" in data


# ---------------------------------------------------------------------------
# Match-preview tests
# ---------------------------------------------------------------------------


def test_match_preview_no_log(client):
    s = _make_session(client)
    resp = client.get(f"/flight-logs/match-preview?session_id={s.id}")
    assert resp.status_code == 404


def test_match_preview_returns_list(client):
    s = _make_session(client)
    _upload_log(client, s.id)
    resp = client.get(f"/flight-logs/match-preview?session_id={s.id}")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Apply-sync tests
# ---------------------------------------------------------------------------


def test_apply_sync_no_log(client):
    s = _make_session(client)
    resp = client.post(f"/flight-logs/apply?session_id={s.id}")
    assert resp.status_code == 404


def test_apply_sync_returns_applied_count(client):
    s = _make_session(client)
    _upload_log(client, s.id)
    resp = client.post(f"/flight-logs/apply?session_id={s.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "applied" in data
    assert isinstance(data["applied"], int)
