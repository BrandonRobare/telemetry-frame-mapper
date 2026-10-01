"""Integration tests for DJI log upload through the flight-log router.

These mock the ``djirecord`` CLI and verify that UploadFile containing
DJI binary log bytes is sniffed correctly and persisted as FlightLog +
FlightLogPoint rows with attitude/gimbal/battery fields.
"""

from __future__ import annotations

import codecs
import json
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

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
        b"1718447401000,35.0,-80.0,100.0\n"
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
# parse_dji_csv drift from its sibling parsers (issue #683)
# ---------------------------------------------------------------------------


def test_parse_dji_csv_skips_truncated_row():
    """A row missing trailing columns yields None -> float(None) is a TypeError.

    The sibling parsers (Autel/Parrot/ArduPilot) catch TypeError too; a
    truncated DJI row should be skipped rather than crashing the parse.
    """
    csv_bytes = (
        b"time(millisecond),OSD.latitude,OSD.longitude,OSD.altitude[m]\n"
        b"1000,35.0,-80.0,100.0\n"
        b"2000,35.1\n"  # missing longitude and altitude columns -> None
    )

    points = flight_log_sync.parse_dji_csv(csv_bytes)

    assert len(points) == 1
    assert points[0]["latitude"] == 35.0


def test_parse_dji_csv_rejects_out_of_range_coordinate():
    """Out-of-range lat/lon should be rejected like the other three parsers."""
    csv_bytes = (
        b"time(millisecond),OSD.latitude,OSD.longitude,OSD.altitude[m]\n"
        b"1000,35.0,-80.0,100.0\n"
        b"2000,95.0,-80.0,100.0\n"  # latitude out of [-90, 90] range
        b"3000,35.0,-200.0,100.0\n"  # longitude out of [-180, 180] range
    )

    points = flight_log_sync.parse_dji_csv(csv_bytes)

    assert len(points) == 1
    assert points[0]["latitude"] == 35.0
    assert points[0]["longitude"] == -80.0


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
    # The bound re-spaces the sweep; it never cuts the requested window short.
    assert rows[0]["offset_s"] == -10.0
    assert rows[-1]["offset_s"] == 10.0

    # Only reachable once the cap exists: uncapped this is 600_000_001 iterations.
    rows = flight_log_sync.build_offset_preview(
        _IMAGES, _LOG_POINTS, tolerance_s=2.0, window_s=300.0, step_s=0.000001
    )
    assert len(rows) == flight_log_sync._MAX_PREVIEW_STEPS + 1
    assert rows[0]["offset_s"] == -300.0
    assert rows[-1]["offset_s"] == 300.0


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


# ---------------------------------------------------------------------------
# BOM, relative clocks and null-island fixes (issue #947)
# ---------------------------------------------------------------------------

_T0 = datetime(2024, 6, 15, 10, 30, tzinfo=UTC)
_T0_S = _T0.timestamp()  # 1718447400.0

_DJI_CSV = (
    b"time(millisecond),OSD.latitude,OSD.longitude,OSD.altitude[m]\n"
    b"1718447401000,35.0,-80.0,100.0\n"
    b"1718447402000,35.001,-80.001,101.0\n"
)


def test_parse_dji_csv_bom_prefixed_matches_bomless():
    """A UTF-8 BOM (Excel, many exporters) must not zero every DJI timestamp."""
    bomless = flight_log_sync.parse_dji_csv(_DJI_CSV)
    bom = flight_log_sync.parse_dji_csv(codecs.BOM_UTF8 + _DJI_CSV)

    assert [p["timestamp_s"] for p in bomless] == [1718447401.0, 1718447402.0]
    assert bom == bomless
    # The upload entry point detects the format and parses through the same path.
    assert flight_log_sync.parse_flight_log_csv(codecs.BOM_UTF8 + _DJI_CSV) == ("csv", bomless)


def test_relative_clock_log_is_anchored_to_its_start_time():
    """A log with 0..600000 ms offsets lands at its start time, not in 1970."""
    content = "time(millisecond),OSD.latitude,OSD.longitude,OSD.altitude[m]\n" + "".join(
        f"{ms},35.0,-80.0,100.0\n" for ms in range(0, 600_001, 60_000)
    )
    _, points = flight_log_sync.parse_flight_log_csv(content.encode())
    offsets_s = [p["timestamp_s"] for p in points]
    assert offsets_s[0] == 0.0 and offsets_s[-1] == 600.0

    anchored = flight_log_sync.anchor_log_timestamps(offsets_s, _T0)

    assert anchored[0] == _T0_S
    assert anchored[-1] == _T0_S + 600.0
    assert [t - _T0_S for t in anchored] == offsets_s


def test_anchor_log_timestamps_reads_naive_start_time_as_utc():
    assert flight_log_sync.anchor_log_timestamps([0.0, 1.5], _T0.replace(tzinfo=None)) == [
        _T0_S,
        _T0_S + 1.5,
    ]


def test_relative_clock_without_start_time_is_rejected():
    """With no known start time the log cannot be placed in time; refuse, don't guess."""
    with pytest.raises(flight_log_sync.FlightLogClockError, match="relative"):
        flight_log_sync.anchor_log_timestamps([0.0, 1.0, 600.0], None)


def test_absolute_clock_log_is_left_alone():
    times = [_T0_S, _T0_S + 1.0]
    assert flight_log_sync.anchor_log_timestamps(times, None) == times
    # A supplied start time never shifts a log that already carries absolute times.
    later = datetime(2030, 1, 1, tzinfo=UTC)
    assert flight_log_sync.anchor_log_timestamps(times, later) == times


def test_mixed_relative_and_absolute_clock_is_rejected():
    with pytest.raises(flight_log_sync.FlightLogClockError, match="mixes"):
        flight_log_sync.anchor_log_timestamps([0.0, _T0_S], _T0)


def _dji_json(offsets_ms: list[int], start_time: str | None) -> dict:
    data = json.loads(json.dumps(_V12_JSON))
    frame = data["frames"][0]
    data["frames"] = [{**frame, "osd": {**frame["osd"], "timeMs": ms}} for ms in offsets_ms]
    if start_time is None:
        del data["header"]["startTime"]
    else:
        data["header"]["startTime"] = start_time
    return data


def _fake_djirecord(monkeypatch, payload: dict) -> None:
    def fake_run(argv, capture_output, text, timeout, env=None):  # noqa: ARG001
        return _FakeCompletedProcess(0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("backend.services.dji_log_parser._BINARY", "/fake/djirecord")


def _stored_timestamps(log_id: int) -> list[datetime]:
    db = app.state.test_db_session
    return [
        p.timestamp
        for p in db.query(FlightLogPoint)
        .filter(FlightLogPoint.flight_log_id == log_id)
        .order_by(FlightLogPoint.timestamp)
    ]


def test_upload_dji_binary_anchors_relative_clock_to_header_start_time(client, monkeypatch):
    """DJI OSD timeMs counts from the flight start recorded in the log header."""
    s = _make_session(client)
    _fake_djirecord(
        monkeypatch, _dji_json(list(range(0, 600_001, 60_000)), "2024-06-15T10:30:00Z")
    )

    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("flight.txt", _PRE_V12, "application/octet-stream")},
        data={"session_id": str(s.id)},
    )

    assert resp.status_code == 200
    stamps = _stored_timestamps(resp.json()["id"])
    assert len(stamps) == 11
    assert stamps[0] == _T0
    assert stamps[-1] == _T0 + timedelta(minutes=10)


def test_upload_dji_binary_relative_clock_without_start_time_is_rejected(client, monkeypatch):
    s = _make_session(client)
    _fake_djirecord(monkeypatch, _dji_json([0, 100], None))

    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("flight.txt", _PRE_V12, "application/octet-stream")},
        data={"session_id": str(s.id)},
    )

    assert resp.status_code == 422
    assert "relative" in resp.json()["detail"]
    db = app.state.test_db_session
    assert db.query(FlightLog).filter(FlightLog.session_id == s.id).count() == 0


def test_upload_dji_binary_relative_clock_uses_supplied_start_time(client, monkeypatch):
    s = _make_session(client)
    _fake_djirecord(monkeypatch, _dji_json([0, 1000], None))

    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("flight.txt", _PRE_V12, "application/octet-stream")},
        data={"session_id": str(s.id), "start_time": "2024-06-15T10:30:00Z"},
    )

    assert resp.status_code == 200
    assert _stored_timestamps(resp.json()["id"]) == [_T0, _T0 + timedelta(seconds=1)]


# Receiver outages recorded as (0, 0), plus a near-zero placeholder inside the
# shared no-fix threshold. Neither may pull an interpolated position.
_GAP_LOG = [
    {"timestamp_s": 0.0, "latitude": 35.0, "longitude": -80.0, "altitude_m": 100.0},
    {"timestamp_s": 1.0, "latitude": 0.0, "longitude": 0.0, "altitude_m": 0.0},
    {"timestamp_s": 2.0, "latitude": 35.002, "longitude": -80.002, "altitude_m": 102.0},
    {"timestamp_s": 3.0, "latitude": 0.0004, "longitude": -0.0003, "altitude_m": 0.0},
    {"timestamp_s": 4.0, "latitude": 35.004, "longitude": -80.004, "altitude_m": 104.0},
]


def _image_at(image_id: int, seconds: float) -> _FakeImage:
    return _FakeImage(image_id, datetime(1970, 1, 1) + timedelta(seconds=seconds))


def test_null_island_points_never_feed_interpolation():
    images = [_image_at(1, 1.0), _image_at(2, 2.5), _image_at(3, 3.0)]

    matches = {
        m["image_id"]: m
        for m in flight_log_sync.match_images_to_log(images, _GAP_LOG, tolerance_s=0.1)
    }

    assert set(matches) == {1, 2, 3}

    def position(m):
        return (m["latitude"], m["longitude"], m["altitude_m"])

    assert position(matches[1]) == pytest.approx((35.001, -80.001, 101.0))
    assert position(matches[2]) == pytest.approx((35.0025, -80.0025, 102.5))
    assert position(matches[3]) == pytest.approx((35.003, -80.003, 103.0))


def test_log_with_only_null_island_points_matches_nothing():
    no_fix = [
        {"timestamp_s": t, "latitude": 0.0, "longitude": 0.0, "altitude_m": 0.0}
        for t in (0.0, 1.0, 2.0)
    ]

    assert flight_log_sync.match_images_to_log(_IMAGES, no_fix, tolerance_s=2.0) == []
    rows = flight_log_sync.build_offset_preview(
        _IMAGES, no_fix, tolerance_s=2.0, window_s=1.0, step_s=1.0
    )
    assert [row["matched"] for row in rows] == [0, 0, 0]