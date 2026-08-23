"""Integration tests for DJI log upload through the flight-log router.

These mock the ``djirecord`` CLI and verify that UploadFile containing
DJI binary log bytes is sniffed correctly and persisted as FlightLog +
FlightLogPoint rows with attitude/gimbal/battery fields.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime

from backend.db.models import FlightLog, FlightLogPoint
from backend.main import app
from backend.services import flight_log_sync

# ---------------------------------------------------------------------------
# Sample djirecord --json (v12 unencrypted)
# ---------------------------------------------------------------------------

_V12_JSON = {
    "logVersion": 12,
    "header": {
        "aircraftName": "Mavic 2 Pro",
        "aircraftSn": "ABC123",
        "batterySn": "BAT001",
        "cameraSn": "CAM001",
        "rcSn": "RC001",
        "productType": "MAVIC2",
        "startTime": "2024-06-15T10:30:00Z",
        "totalDistance": 2.5,
        "maxHeight": 120.0,
        "totalTime": 480.0,
    },
    "frames": [
        {
            "osd": {
                "timeMs": 0,
                "latitude": 35.0,
                "longitude": -80.0,
                "altitude": 100.0,
                "speed": 5.0,
                "heading": 90.0,
            },
            "attitude": {"roll": 0.5, "pitch": 1.2, "yaw": 89.0},
            "gimbal": {"pitch": -45.0, "roll": 0.0, "yaw": 90.0},
            "battery": {"voltage": 15.2, "chargeLevel": 95.0, "temperature": 32.0},
        },
        {
            "osd": {
                "timeMs": 100,
                "latitude": 35.001,
                "longitude": -80.001,
                "altitude": 110.0,
                "speed": 6.0,
                "heading": 95.0,
            },
            "attitude": {"roll": 0.8, "pitch": 1.5, "yaw": 94.0},
            "gimbal": {"pitch": -46.0, "roll": 0.1, "yaw": 95.0},
            "battery": {"voltage": 15.1, "chargeLevel": 94.0, "temperature": 33.0},
        },
    ],
}

# Minimal DJI binary prefix for sniffing: version byte at offset 10
_PRE_V12 = b"\x00" * 10 + b"\x0c" + b"\x00" * 5  # version 12
_PRE_V13 = b"\x00" * 10 + b"\x0d" + b"\x00" * 5  # version 13


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(client):
    from backend.db.models import Session as SM

    db = app.state.test_db_session
    s = SM(name="dji_test", folder_path="/tmp", photo_count=0, usable_count=0)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ---------------------------------------------------------------------------
# DJI binary upload tests
# ---------------------------------------------------------------------------


def test_upload_dji_binary_v12(client, monkeypatch):
    """Upload a v12 .txt log: sniffed as DJI binary, parsed via mock."""
    s = _make_session(client)

    def fake_run(argv, capture_output, text, timeout, env=None):  # noqa: ARG001
        return _FakeCompletedProcess(0, json.dumps(_V12_JSON), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "backend.services.dji_log_parser._BINARY", "/fake/djirecord"
    )

    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("flight.txt", _PRE_V12, "application/octet-stream")},
        data={"session_id": str(s.id)},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "dji_binary"
    assert data["point_count"] == 2
    assert data["log_version"] == 12
    assert data["aircraft_name"] == "Mavic 2 Pro"
    assert data["encrypted"] is False
    assert "id" in data

    # Verify DB rows
    db = app.state.test_db_session
    log = db.query(FlightLog).filter(FlightLog.id == data["id"]).one()
    assert log.format == "dji_binary"
    assert log.log_version == 12
    assert log.aircraft_name == "Mavic 2 Pro"
    assert log.aircraft_sn == "ABC123"

    points = (
        db.query(FlightLogPoint)
        .filter(FlightLogPoint.flight_log_id == log.id)
        .order_by(FlightLogPoint.id)
        .all()
    )
    assert len(points) == 2

    p0 = points[0]
    assert p0.latitude == 35.0
    assert p0.longitude == -80.0
    assert p0.altitude_m == 100.0
    assert p0.speed_ms == 5.0
    assert p0.heading == 90.0
    assert p0.roll == 0.5
    assert p0.pitch == 1.2
    assert p0.yaw == 89.0
    assert p0.gimbal_pitch == -45.0
    assert p0.gimbal_roll == 0.0
    assert p0.gimbal_yaw == 90.0
    assert p0.battery_voltage == 15.2
    assert p0.battery_charge_pct == 95.0
    assert p0.battery_temperature_c == 32.0


def test_upload_dji_binary_v13_no_key_rejected(client, monkeypatch):
    """v13+ without API key: server returns 422 with clear message."""
    s = _make_session(client)

    def fake_run(argv, capture_output, text, timeout, env=None):  # noqa: ARG001
        return _FakeCompletedProcess(
            1, "",
            "Error: Cannot decrypt version 13+ logs without an API key",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "backend.services.dji_log_parser._BINARY", "/fake/djirecord"
    )

    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("flight.txt", _PRE_V13, "application/octet-stream")},
        data={"session_id": str(s.id)},
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "API key" in detail.lower() or "decrypt" in detail.lower()


def test_upload_dji_binary_pydjirecord_missing(client, monkeypatch):
    """Without djirecord on PATH: 501 Not Implemented."""
    s = _make_session(client)
    monkeypatch.setattr(
        "backend.services.dji_log_parser._BINARY", None
    )

    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("flight.txt", _PRE_V12, "application/octet-stream")},
        data={"session_id": str(s.id)},
    )

    assert resp.status_code == 501


def test_upload_dji_binary_sniffed_from_content(client, monkeypatch):
    """Upload with a generic filename but DJI binary prefix: sniffed correctly."""
    s = _make_session(client)

    def fake_run(argv, capture_output, text, timeout, env=None):  # noqa: ARG001
        return _FakeCompletedProcess(0, json.dumps(_V12_JSON), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "backend.services.dji_log_parser._BINARY", "/fake/djirecord"
    )

    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("data.bin", _PRE_V12, "application/octet-stream")},
        data={"session_id": str(s.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["format"] == "dji_binary"


def test_upload_dji_csv_fallback(client):
    """Standard CSV upload still works when content is not DJI binary."""
    s = _make_session(client)

    csv_bytes = (
        b"time(millisecond),OSD.latitude,OSD.longitude,OSD.altitude[m]\n"
        b"1000,35.0,-80.0,100.0\n"
    )

    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("log.csv", csv_bytes, "text/csv")},
        data={"session_id": str(s.id)},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "csv"
    assert data["point_count"] == 1


def test_upload_dji_binary_missing_session(client, monkeypatch):
    """404 when session_id doesn't exist."""
    monkeypatch.setattr(
        "backend.services.dji_log_parser._BINARY", "/fake/djirecord"
    )
    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("flight.txt", _PRE_V12, "application/octet-stream")},
        data={"session_id": "999999"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Offset-preview bounds and sort hoisting (issue #635)
# ---------------------------------------------------------------------------


class _FakeImage:
    def __init__(self, image_id: int, timestamp: datetime):
        self.id = image_id
        self.filename = f"IMG_{image_id}.jpg"
        self.timestamp = timestamp


_LOG_POINTS = [
    {"timestamp_s": 0.0, "latitude": 35.0, "longitude": -80.0, "altitude_m": 100.0},
    {"timestamp_s": 1.0, "latitude": 35.001, "longitude": -80.001, "altitude_m": 101.0},
    {"timestamp_s": 2.0, "latitude": 35.002, "longitude": -80.002, "altitude_m": 102.0},
]

_IMAGES = [_FakeImage(1, datetime(1970, 1, 1, 0, 0, 1))]


def test_build_offset_preview_caps_step_count():
    """A tiny step_s must yield a bounded row count instead of running unbounded."""
    rows = flight_log_sync.build_offset_preview(
        _IMAGES, _LOG_POINTS, tolerance_s=2.0, window_s=10.0, step_s=0.001
    )
    # Uncapped this is int(20 / 0.001) + 1 == 20_001 rows.
    assert len(rows) == flight_log_sync._MAX_PREVIEW_STEPS + 1

    # Only reachable once the cap exists: uncapped this is 600_000_001 iterations.
    rows = flight_log_sync.build_offset_preview(
        _IMAGES, _LOG_POINTS, tolerance_s=2.0, window_s=300.0, step_s=0.000001
    )
    assert len(rows) == flight_log_sync._MAX_PREVIEW_STEPS + 1


def test_build_offset_preview_sorts_log_points_once(monkeypatch):
    """The flight log is sorted once per request, not once per image per offset."""
    calls = []
    real_sorted = sorted

    def counting_sorted(iterable, **kwargs):
        calls.append(1)
        return real_sorted(iterable, **kwargs)

    monkeypatch.setattr(flight_log_sync, "sorted", counting_sorted, raising=False)

    rows = flight_log_sync.build_offset_preview(
        _IMAGES, _LOG_POINTS, tolerance_s=2.0, window_s=2.0, step_s=1.0
    )

    assert len(rows) == 5  # 1 image x 5 offsets == 5 sorts before the hoist
    assert len(calls) == 1


def test_match_images_to_log_sorts_unsorted_points():
    """match_images_to_log owns the sort, so unsorted input still matches correctly.

    ``interpolate_log_point`` now requires sorted points by contract; this guards
    the one place that guarantees it.
    """
    shuffled = [_LOG_POINTS[2], _LOG_POINTS[0], _LOG_POINTS[1]]
    matches = flight_log_sync.match_images_to_log(_IMAGES, shuffled, tolerance_s=0.1)

    assert len(matches) == 1
    assert matches[0]["latitude"] == 35.001
    assert matches[0]["longitude"] == -80.001