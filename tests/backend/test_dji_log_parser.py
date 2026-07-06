"""Tests for backend/services/dji_log_parser.py — subprocess wrapper and DB integration.

These tests mock the ``djirecord`` CLI so they run without a real DJI
binary log, API key, or network access.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from backend.services.dji_log_parser import (
    _build_result,
    detect_log_version,
    dji_parser_available,
    parse_dji_binary_bytes,
)

# ---------------------------------------------------------------------------
# Sample djirecord --json output (pre-v13, unencrypted)
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

_V13_HEADER_ONLY = {
    "logVersion": 13,
    "header": {
        "aircraftName": "Mavic 3",
        "aircraftSn": "M3XYZ",
        "productType": "MAVIC3",
        "startTime": "2025-01-10T14:00:00Z",
    },
    "frames": [],
}

_V13_DECRYPTED = {
    "logVersion": 13,
    "header": {
        "aircraftName": "Mavic 3",
        "aircraftSn": "M3XYZ",
        "batterySn": "BAT002",
        "productType": "MAVIC3",
        "startTime": "2025-01-10T14:00:00Z",
        "totalDistance": 3.1,
        "maxHeight": 150.0,
        "totalTime": 600.0,
    },
    "frames": [
        {
            "osd": {
                "timeMs": 0,
                "latitude": 40.0,
                "longitude": -75.0,
                "altitude": 200.0,
                "speed": 8.0,
                "heading": 180.0,
            },
            "attitude": {"roll": 0.0, "pitch": 0.0, "yaw": 180.0},
            "gimbal": {"pitch": -90.0, "roll": 0.0, "yaw": 180.0},
            "battery": {"voltage": 16.8, "chargeLevel": 100.0, "temperature": 25.0},
        },
    ],
}


# ---------------------------------------------------------------------------
# Unit tests — _build_result
# ---------------------------------------------------------------------------


class TestBuildResult:
    def test_v12_unencrypted(self):
        result = _build_result(_V12_JSON, decrypted=False)
        assert result.header.version == 12
        assert result.header.aircraft_name == "Mavic 2 Pro"
        assert result.header.aircraft_sn == "ABC123"
        assert result.frame_count == 2
        assert result.decrypted is False

        frame = result.frames[0]
        assert frame.latitude == 35.0
        assert frame.longitude == -80.0
        assert frame.altitude_m == 100.0
        assert frame.roll == 0.5
        assert frame.pitch == 1.2
        assert frame.yaw == 89.0
        assert frame.gimbal_pitch == -45.0
        assert frame.battery_voltage == 15.2
        assert frame.battery_charge_pct == 95.0
        assert frame.battery_temperature_c == 32.0

    def test_v13_header_only(self):
        result = _build_result(_V13_HEADER_ONLY, decrypted=False)
        assert result.header.version == 13
        assert result.header.aircraft_name == "Mavic 3"
        assert result.frame_count == 0
        assert result.frames == []

    def test_v13_decrypted(self):
        result = _build_result(_V13_DECRYPTED, decrypted=True)
        assert result.header.version == 13
        assert result.decrypted is True
        assert result.frame_count == 1
        frame = result.frames[0]
        assert frame.latitude == 40.0
        assert frame.battery_voltage == 16.8

    def test_missing_optional_fields(self):
        """Fields that are absent from source JSON should be None, not crash."""
        minimal = {
            "logVersion": 10,
            "header": {},
            "frames": [
                {
                    "osd": {
                        "timeMs": 500,
                        "latitude": 0.0,
                        "longitude": 0.0,
                        "altitude": 0.0,
                        "speed": 0.0,
                        "heading": 0.0,
                    }
                }
            ],
        }
        result = _build_result(minimal, decrypted=False)
        assert result.header.aircraft_name is None
        assert result.frames[0].roll is None
        assert result.frames[0].battery_voltage is None

    def test_alternate_field_names(self):
        """pydjirecord 1.3.0 uses 'details' and non-nested field names sometimes."""
        alt = {
            "version": 10,
            "details": {
                "aircraft_name": "Phantom 4",
                "aircraft_sn": "P4-001",
                "battery_sn": "B99",
                "camera_sn": "C99",
                "rc_sn": "RC99",
                "product_type": "P4",
                "start_time": "2023-01-01T00:00:00Z",
                "total_distance": 1.0,
                "max_height": 50.0,
                "total_time": 120.0,
            },
            "frames": [
                {
                    "osd": {
                        "timestamp_ms": 200,
                        "latitude": 50.0,
                        "longitude": 10.0,
                        "altitude_m": 60.0,
                        "speed_ms": 3.0,
                        "heading": 270.0,
                    }
                }
            ],
        }
        result = _build_result(alt, decrypted=False)
        assert result.header.aircraft_name == "Phantom 4"
        assert result.frames[0].timestamp_ms == 200
        assert result.frames[0].altitude_m == 60.0


# ---------------------------------------------------------------------------
# Capability detection
# ---------------------------------------------------------------------------


class TestCapabilityDetection:
    def test_dji_parser_available(self, monkeypatch):
        # Without djirecord on PATH, should report unavailable
        monkeypatch.setattr(
            "backend.services.dji_log_parser._BINARY", None
        )
        assert dji_parser_available() is False

    def test_dji_parser_available_true(self, monkeypatch):
        monkeypatch.setattr(
            "backend.services.dji_log_parser._BINARY", "/usr/local/bin/djirecord"
        )
        assert dji_parser_available() is True


# ---------------------------------------------------------------------------
# Subprocess integration (mocked)
# ---------------------------------------------------------------------------


class TestParseDjiBinaryBytes:
    def test_v12_parse_via_mock(self, monkeypatch):
        """Mock subprocess.run to return valid v12 JSON."""
        def fake_run(argv, capture_output, text, timeout, env):  # noqa: ARG001
            return _FakeCompletedProcess(0, json.dumps(_V12_JSON), "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(
            "backend.services.dji_log_parser._BINARY", "/fake/djirecord"
        )

        result = parse_dji_binary_bytes(b"fake dji log v12")
        assert result.header.version == 12
        assert result.frame_count == 2
        assert result.decrypted is False

    def test_v13_without_key_raises(self, monkeypatch):
        """v13+ without API key should raise RuntimeError."""
        def fake_run(argv, capture_output, text, timeout, env):  # noqa: ARG001
            return _FakeCompletedProcess(
                1, "",
                "Error: Cannot decrypt version 13+ logs without an API key",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(
            "backend.services.dji_log_parser._BINARY", "/fake/djirecord"
        )

        with pytest.raises(RuntimeError, match="API key"):
            parse_dji_binary_bytes(b"fake v13 log")

    def test_v13_with_key_succeeds(self, monkeypatch):
        """v13+ with API key should parse successfully."""
        def fake_run(argv, capture_output, text, timeout, env):  # noqa: ARG001
            return _FakeCompletedProcess(0, json.dumps(_V13_DECRYPTED), "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(
            "backend.services.dji_log_parser._BINARY", "/fake/djirecord"
        )

        result = parse_dji_binary_bytes(b"fake v13 log", api_key="test-key")
        assert result.header.version == 13
        assert result.decrypted is True
        assert result.frame_count == 1

    def test_djirecord_not_found_raises(self, monkeypatch):
        monkeypatch.setattr(
            "backend.services.dji_log_parser._BINARY", None
        )
        with pytest.raises(RuntimeError, match="djirecord not found"):
            parse_dji_binary_bytes(b"content")


class TestDetectLogVersion:
    def test_valid_log(self, monkeypatch, tmp_path):
        log_file = tmp_path / "fake.txt"
        log_file.write_text("dummy")

        def fake_run(argv, capture_output, text, timeout, env=None):  # noqa: ARG001
            return _FakeCompletedProcess(0, json.dumps(_V12_JSON), "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(
            "backend.services.dji_log_parser._BINARY", "/fake/djirecord"
        )

        assert detect_log_version(log_file) == 12

    def test_invalid_file(self, monkeypatch, tmp_path):
        log_file = tmp_path / "fake.txt"
        log_file.write_text("dummy")

        def fake_run(argv, capture_output, text, timeout, env=None):  # noqa: ARG001
            return _FakeCompletedProcess(1, "", "not a DJI log")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(
            "backend.services.dji_log_parser._BINARY", "/fake/djirecord"
        )

        assert detect_log_version(log_file) is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr