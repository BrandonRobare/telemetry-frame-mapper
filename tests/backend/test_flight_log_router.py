from __future__ import annotations

import codecs
import json
from datetime import UTC, datetime, timedelta

import pytest

from backend.services.flight_log_sync import FlightLogCSVError, parse_autel_csv

# Flight logs carry absolute Unix times; image EXIF times are stored as naive UTC.
T0 = datetime(2024, 6, 15, 10, 30, 0)  # 1718447400 s
T0_PLUS_HALF = T0 + timedelta(milliseconds=500)
T0_PLUS_ONE = T0 + timedelta(seconds=1)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CSV_BYTES = (
    b"time(millisecond),OSD.latitude,OSD.longitude,OSD.altitude[m]\n"
    b"1718447401000,35.0,-80.0,100.0\n"
    b"1718447402000,35.001,-80.001,101.0\n"
)

# A clock counting from the start of the flight, as DJI and Autel exports do.
RELATIVE_CSV_BYTES = (
    b"time(millisecond),OSD.latitude,OSD.longitude,OSD.altitude[m]\n"
    b"0,35.0,-80.0,100.0\n"
    b"600000,35.01,-80.01,110.0\n"
)

# Receiver outages logged as (0, 0), plus a near-zero placeholder inside the
# shared no-fix threshold, between real fixes.
GAP_CSV_BYTES = (
    b"time(millisecond),OSD.latitude,OSD.longitude,OSD.altitude[m]\n"
    b"1718447400000,35.0,-80.0,100.0\n"
    b"1718447401000,0.0,0.0,0.0\n"
    b"1718447402000,35.002,-80.002,102.0\n"
    b"1718447403000,0.0004,-0.0003,0.0\n"
    b"1718447404000,35.004,-80.004,104.0\n"
)

VENDOR_CSVS = [
    (
        "autel.csv",
        b"Time(ms),Latitude,Longitude,Altitude(m)\n1710000000000,35.0,-80.0,100.0\n",
        "autel_csv",
    ),
    (
        "fdr-lite-5hz.csv",
        b"time,latitude,longitude,altitude\n1710000000,35.0,-80.0,101.0\n",
        "parrot_csv",
    ),
    (
        "POS.csv",
        b"timestamp,TimeUS,Lat,Lng,Alt\n1710000000.0,500000,35.0,-80.0,102.0\n",
        "ardupilot_csv",
    ),
]


def _make_session(client):
    from backend.db.models import Session as SM
    from backend.main import app

    db = app.state.test_db_session
    s = SM(name="fl_test", folder_path="/tmp", photo_count=0, usable_count=0)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _upload_log(client, session_id: int, content: bytes = CSV_BYTES) -> dict:
    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("log.csv", content, "text/csv")},
        data={"session_id": str(session_id)},
    )
    assert resp.status_code == 200
    return resp.json()


def _stored_timestamps(log_id: int) -> list[datetime]:
    from backend.db.models import FlightLogPoint
    from backend.main import app

    db = app.state.test_db_session
    return [
        p.timestamp
        for p in db.query(FlightLogPoint)
        .filter(FlightLogPoint.flight_log_id == log_id)
        .order_by(FlightLogPoint.timestamp)
    ]


def _utc(naive: datetime) -> datetime:
    return naive.replace(tzinfo=UTC)


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


@pytest.mark.parametrize(("filename", "content", "format_name"), VENDOR_CSVS)
def test_upload_vendor_flight_log_csv(client, filename, content, format_name):
    s = _make_session(client)

    resp = client.post(
        "/flight-logs/upload",
        files={"file": (filename, content, "text/csv")},
        data={"session_id": str(s.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["format"] == format_name
    assert resp.json()["point_count"] == 1


def test_upload_csv_rejects_unknown_headers_without_guessing_coordinates(client):
    s = _make_session(client)
    content = b"timestamp,latitude,longitude\n1710000000,35.0,-80.0\n"

    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("unknown.csv", content, "text/csv")},
        data={"session_id": str(s.id)},
    )

    assert resp.status_code == 422
    assert "Unsupported flight log CSV headers" in resp.json()["detail"]


def test_autel_csv_reports_missing_required_headers():
    with pytest.raises(FlightLogCSVError, match="missing required header"):
        parse_autel_csv(b"Time(ms),Latitude,Longitude\n1000,35.0,-80.0\n")


def test_upload_vendor_csv_rejects_invalid_coordinates(client):
    s = _make_session(client)
    content = b"time,latitude,longitude,altitude\n1710000000,95.0,-80.0,100.0\n"

    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("fdr-lite-5hz.csv", content, "text/csv")},
        data={"session_id": str(s.id)},
    )

    assert resp.status_code == 422
    assert "out-of-range coordinates" in resp.json()["detail"]


def test_upload_bom_prefixed_dji_csv_keeps_its_timestamps(client):
    s = _make_session(client)

    data = _upload_log(client, s.id, codecs.BOM_UTF8 + CSV_BYTES)

    assert _stored_timestamps(data["id"]) == [_utc(T0_PLUS_ONE), _utc(T0 + timedelta(seconds=2))]


def test_upload_relative_clock_csv_without_start_time_is_rejected(client):
    from backend.db.models import FlightLog
    from backend.main import app

    s = _make_session(client)

    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("log.csv", RELATIVE_CSV_BYTES, "text/csv")},
        data={"session_id": str(s.id)},
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "relative" in detail
    assert "start_time" in detail
    db = app.state.test_db_session
    assert db.query(FlightLog).filter(FlightLog.session_id == s.id).count() == 0


def test_upload_relative_clock_csv_is_anchored_to_start_time(client):
    s = _make_session(client)

    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("log.csv", RELATIVE_CSV_BYTES, "text/csv")},
        data={"session_id": str(s.id), "start_time": "2024-06-15T10:30:00Z"},
    )

    assert resp.status_code == 200
    assert _stored_timestamps(resp.json()["id"]) == [
        _utc(T0),
        _utc(T0 + timedelta(minutes=10)),
    ]


def test_upload_rejects_malformed_start_time(client):
    s = _make_session(client)

    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("log.csv", RELATIVE_CSV_BYTES, "text/csv")},
        data={"session_id": str(s.id), "start_time": "yesterday"},
    )

    assert resp.status_code == 422
    assert "start_time" in resp.json()["detail"]


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
    from backend.db.models import Image
    from backend.main import app

    s = _make_session(client)
    db = app.state.test_db_session
    img = Image(
        session_id=s.id,
        filename="frame.jpg",
        filepath="/tmp/frame.jpg",
        timestamp=T0_PLUS_HALF,
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


def test_offset_preview_bounds_tiny_step_s(client):
    """A tiny step_s passes the router's ``gt=0`` bound; the row count stays bounded."""
    from backend.services.flight_log_sync import _MAX_PREVIEW_STEPS

    s = _make_session(client)
    _upload_log(client, s.id)

    # Uncapped this is int(600 / 0.05) + 1 == 12_001 rows.
    resp = client.get(
        f"/flight-logs/offset-preview?session_id={s.id}&window_s=300&step_s=0.05"
    )
    assert resp.status_code == 200
    assert len(resp.json()) == _MAX_PREVIEW_STEPS + 1

    # Only reachable once the cap exists: uncapped this is 600_000_001 iterations.
    resp = client.get(
        f"/flight-logs/offset-preview?session_id={s.id}&window_s=300&step_s=0.000001"
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == _MAX_PREVIEW_STEPS + 1
    # Bounded by re-spacing, so the operator still sees the window they asked for.
    assert (rows[0]["offset_s"], rows[-1]["offset_s"]) == (-300.0, 300.0)


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


def _pre_sync_footprint(image_id: int):
    from backend.db.models import Footprint

    return Footprint(
        image_id=image_id,
        geom_wkt="PRE-SYNC",
        geom_geojson='{"type":"Polygon","coordinates":[]}',
        ground_width_m=1.0,
        ground_height_m=1.0,
    )


def _assert_footprint_follows_position(footprint, img) -> None:
    """The footprint is centred on the image's synced position, built as ingest builds it."""
    from shapely.geometry import shape

    from backend.core.config import load_config
    from backend.services.ingest_orchestrator import build_footprint

    centroid = shape(json.loads(footprint.geom_geojson)).centroid
    assert (centroid.y, centroid.x) == pytest.approx((img.latitude, img.longitude), abs=1e-6)
    expected = build_footprint(img, load_config())
    assert footprint.geom_wkt == expected.geom_wkt
    assert footprint.ground_width_m == expected.ground_width_m


def test_apply_sync_recomputes_stale_footprint(client):
    from backend.db.models import Footprint, Image
    from backend.main import app

    s = _make_session(client)
    db = app.state.test_db_session
    img = Image(
        session_id=s.id,
        filename="frame.jpg",
        filepath="/tmp/frame.jpg",
        timestamp=T0_PLUS_ONE,
        latitude=10.0,
        longitude=20.0,
        altitude_m=50.0,
        yaw=15.0,
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    db.add(_pre_sync_footprint(img.id))
    db.commit()

    _upload_log(client, s.id)
    resp = client.post(f"/flight-logs/apply?session_id={s.id}")

    assert resp.status_code == 200
    db.expire_all()
    refreshed = db.query(Image).filter(Image.id == img.id).one()
    assert refreshed.original_latitude == 10.0
    assert refreshed.original_longitude == 20.0
    assert refreshed.original_altitude_m == 50.0
    assert refreshed.synced_latitude == 35.0
    assert refreshed.synced_longitude == -80.0
    assert refreshed.synced_altitude_m == 100.0
    assert refreshed.gps_source == "flight_log"
    footprints = db.query(Footprint).filter(Footprint.image_id == img.id).all()
    assert len(footprints) == 1
    assert footprints[0].geom_wkt != "PRE-SYNC"
    _assert_footprint_follows_position(footprints[0], refreshed)


def test_apply_sync_creates_footprint_for_newly_positioned_image(client):
    from backend.db.models import Footprint, Image
    from backend.main import app

    s = _make_session(client)
    db = app.state.test_db_session
    img = Image(
        session_id=s.id,
        filename="frame.jpg",
        filepath="/tmp/frame.jpg",
        timestamp=T0_PLUS_ONE,
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
    refreshed = db.query(Image).filter(Image.id == img.id).one()
    footprint = db.query(Footprint).filter(Footprint.image_id == img.id).one()
    _assert_footprint_follows_position(footprint, refreshed)


def test_apply_sync_ignores_null_island_rows_and_recomputes_footprints(client):
    """(0, 0) rows never influence synced positions; footprints follow the sync."""
    from backend.db.models import Footprint, Image
    from backend.main import app

    s = _make_session(client)
    db = app.state.test_db_session
    at_outage = Image(
        session_id=s.id,
        filename="outage.jpg",
        filepath="/tmp/outage.jpg",
        timestamp=T0_PLUS_ONE,
        latitude=35.1,
        longitude=-80.1,
        altitude_m=50.0,
        yaw=15.0,
    )
    near_placeholder = Image(
        session_id=s.id,
        filename="placeholder.jpg",
        filepath="/tmp/placeholder.jpg",
        timestamp=T0 + timedelta(milliseconds=2500),
    )
    outside_log = Image(
        session_id=s.id,
        filename="outside.jpg",
        filepath="/tmp/outside.jpg",
        timestamp=T0 + timedelta(hours=1),
        latitude=36.0,
        longitude=-81.0,
        altitude_m=60.0,
    )
    db.add_all([at_outage, near_placeholder, outside_log])
    db.commit()
    for img in (at_outage, near_placeholder, outside_log):
        db.refresh(img)
    db.add_all([_pre_sync_footprint(at_outage.id), _pre_sync_footprint(outside_log.id)])
    db.commit()

    _upload_log(client, s.id, GAP_CSV_BYTES)
    resp = client.post(f"/flight-logs/apply?session_id={s.id}")

    assert resp.status_code == 200
    assert resp.json()["applied"] == 2
    db.expire_all()
    synced = {img.filename: img for img in db.query(Image).filter(Image.session_id == s.id)}

    outage = synced["outage.jpg"]
    placeholder = synced["placeholder.jpg"]
    assert (outage.latitude, outage.longitude, outage.altitude_m) == pytest.approx(
        (35.001, -80.001, 101.0)
    )
    assert (placeholder.latitude, placeholder.longitude, placeholder.altitude_m) == pytest.approx(
        (35.0025, -80.0025, 102.5)
    )

    footprints = {
        fp.image_id: fp
        for fp in db.query(Footprint).filter(
            Footprint.image_id.in_([img.id for img in synced.values()])
        )
    }
    _assert_footprint_follows_position(footprints[outage.id], outage)
    _assert_footprint_follows_position(footprints[placeholder.id], placeholder)
    # An image the sync did not reposition keeps its position and footprint.
    outside = synced["outside.jpg"]
    assert (outside.latitude, outside.longitude, outside.gps_source) == (36.0, -81.0, "none")
    assert footprints[outside.id].geom_wkt == "PRE-SYNC"
