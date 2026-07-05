from __future__ import annotations

from datetime import datetime

UTC_EPOCH_PLUS_HALF = datetime(1970, 1, 1, 0, 0, 0, 500000)
UTC_EPOCH_PLUS_ONE = datetime(1970, 1, 1, 0, 0, 1)

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


def test_upload_flight_log_rejects_oversized_file(client, monkeypatch):
    import backend.routers.flight_log as flight_log_mod

    s = _make_session(client)
    monkeypatch.setattr(
        flight_log_mod,
        "get_upload_limits_config",
        lambda: {"flight_log_max_bytes": len(CSV_BYTES) - 1},
    )

    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("log.csv", CSV_BYTES, "text/csv")},
        data={"session_id": str(s.id)},
    )

    assert resp.status_code == 413
    assert "Flight log upload exceeds" in resp.json()["detail"]


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


def test_match_preview_uses_offset_and_interpolation(client):
    from backend.db.database import get_db
    from backend.db.models import Image
    from backend.main import app

    s = _make_session(client)
    db = next(app.dependency_overrides[get_db]())
    img = Image(
        session_id=s.id,
        filename="frame.jpg",
        filepath="/tmp/frame.jpg",
        timestamp=UTC_EPOCH_PLUS_HALF,
    )
    db.add(img)
    db.commit()

    _upload_log(client, s.id)
    resp = client.get(
        f"/flight-logs/match-preview?session_id={s.id}&offset_s=1.0&tolerance_s=0.1"
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["interpolated"] is True
    assert data[0]["latitude"] == 35.0005
    assert data[0]["longitude"] == -80.0005
    assert data[0]["altitude_m"] == 100.5


def test_offset_preview_returns_graph_rows(client):
    s = _make_session(client)
    _upload_log(client, s.id)
    resp = client.get(
        f"/flight-logs/offset-preview?session_id={s.id}&offset_s=0&tolerance_s=2&window_s=2&step_s=1"
    )

    assert resp.status_code == 200
    data = resp.json()
    assert [row["offset_s"] for row in data] == [-2.0, -1.0, 0.0, 1.0, 2.0]
    assert all({"matched", "total", "mean_abs_delta_s"} <= set(row) for row in data)


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


def test_apply_sync_preserves_stale_footprint(client):
    from backend.db.database import get_db
    from backend.db.models import Footprint, Image
    from backend.main import app

    s = _make_session(client)
    db = next(app.dependency_overrides[get_db]())
    img = Image(
        session_id=s.id,
        filename="frame.jpg",
        filepath="/tmp/frame.jpg",
        timestamp=UTC_EPOCH_PLUS_ONE,
        latitude=10.0,
        longitude=20.0,
        altitude_m=50.0,
        yaw=15.0,
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    db.add(
        Footprint(
            image_id=img.id,
            geom_wkt="STALE",
            geom_geojson='{"type":"Polygon","coordinates":[]}',
            ground_width_m=1.0,
            ground_height_m=1.0,
        )
    )
    db.commit()

    _upload_log(client, s.id)
    resp = client.post(f"/flight-logs/apply?session_id={s.id}")

    assert resp.status_code == 200
    db.expire_all()
    footprints = db.query(Footprint).filter(Footprint.image_id == img.id).all()
    assert len(footprints) == 1
    assert footprints[0].geom_wkt == "STALE"
    refreshed = db.query(Image).filter(Image.id == img.id).one()
    assert refreshed.original_latitude == 10.0
    assert refreshed.original_longitude == 20.0
    assert refreshed.original_altitude_m == 50.0
    assert refreshed.synced_latitude == 35.0
    assert refreshed.synced_longitude == -80.0
    assert refreshed.synced_altitude_m == 100.0
    assert refreshed.gps_source == "flight_log"


def test_apply_sync_does_not_create_missing_footprint(client):
    from backend.db.database import get_db
    from backend.db.models import Footprint, Image
    from backend.main import app

    s = _make_session(client)
    db = next(app.dependency_overrides[get_db]())
    img = Image(
        session_id=s.id,
        filename="frame.jpg",
        filepath="/tmp/frame.jpg",
        timestamp=UTC_EPOCH_PLUS_ONE,
        latitude=None,
        longitude=None,
        altitude_m=None,
    )
    db.add(img)
    db.commit()
    db.refresh(img)

    _upload_log(client, s.id)
    resp = client.post(f"/flight-logs/apply?session_id={s.id}")

    assert resp.status_code == 200
    db.expire_all()
    footprint = db.query(Footprint).filter(Footprint.image_id == img.id).one_or_none()
    assert footprint is None
