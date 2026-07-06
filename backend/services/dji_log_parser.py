"""DJI binary flight-log parser via pydjirecord subprocess wrapper.

Pre-v13 logs (.txt binary format) are parsed offline with no external
dependencies beyond ``pydjirecord``.  v13+ logs are encrypted with
AES-256-CBC; decryption requires a DJI Developer API key, passed via
``--api-key`` / ``DJI_API_KEY`` env var.  Without a key, v13+ logs
produce header-only output (no frames) and the parser raises a clear error.

Capability detection (``djirecord`` on PATH) is exposed so callers can
guard imports at runtime.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Capability detection
# ---------------------------------------------------------------------------

_BINARY = shutil.which("djirecord")


def dji_parser_available() -> bool:
    """Return *True* when the ``djirecord`` CLI (pydjirecord) is on PATH."""
    return _BINARY is not None


def _check_available() -> str:
    if _BINARY is None:
        raise RuntimeError(
            "djirecord not found on PATH; install pydjirecord (pip install pydjirecord)"
        )
    return _BINARY


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class DJILogFrame:
    timestamp_ms: float
    latitude: float
    longitude: float
    altitude_m: float
    speed_ms: float
    heading: float

    # Attitude
    roll: float | None = None
    pitch: float | None = None
    yaw: float | None = None

    # Gimbal
    gimbal_pitch: float | None = None
    gimbal_roll: float | None = None
    gimbal_yaw: float | None = None

    # Battery
    battery_voltage: float | None = None
    battery_charge_pct: float | None = None
    battery_temperature_c: float | None = None


@dataclass
class DJILogHeader:
    version: int
    aircraft_name: str | None = None
    aircraft_sn: str | None = None
    battery_sn: str | None = None
    camera_sn: str | None = None
    rc_sn: str | None = None
    product_type: str | None = None
    start_time: str | None = None  # ISO 8601
    total_distance_km: float | None = None
    max_height_m: float | None = None
    total_time_s: float | None = None


@dataclass
class DJILogResult:
    header: DJILogHeader
    frames: list[DJILogFrame] = field(default_factory=list)
    frame_count: int = 0
    decrypted: bool = False


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_dji_binary(
    filepath: str | Path,
    *,
    api_key: str | None = None,
    timeout_s: int = 120,
) -> DJILogResult:
    """Parse a DJI .txt binary flight log via ``djirecord`` CLI.

    *Pre-v13 logs* are parsed offline.  *v13+ encrypted logs* require
    ``api_key`` (or the ``DJI_API_KEY`` env var); without either this
    function raises ``RuntimeError`` with the decryption error from the
    subprocess.

    Parameters
    ----------
    filepath : str | Path
        Path to the DJI .txt flight log.
    api_key : str | None
        DJI Developer API key for v13+ decryption.  Falls back to
        ``DJI_API_KEY`` env var.
    timeout_s : int
        Subprocess timeout in seconds (default 120).

    Returns
    -------
    DJILogResult
        Parsed header and telemetry frames.

    Raises
    ------
    RuntimeError
        If ``djirecord`` is not installed, the log cannot be decrypted
        (v13+ without key), or parsing fails.
    """
    binary = _check_available()
    fp = Path(filepath)

    if not fp.exists():
        raise FileNotFoundError(f"DJI flight log not found: {fp}")

    # Build argv
    argv: list[str] = [binary, str(fp), "--json"]

    env = os.environ.copy()
    effective_key = api_key or os.environ.get("DJI_API_KEY", "")

    if effective_key:
        argv.extend(["--api-key", effective_key])

    # --- shell out -----------------------------------------------------------
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        env=env,
    )

    if proc.returncode != 0:
        _raise_parse_error(proc)

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"djirecord produced invalid JSON for {fp.name}"
        ) from None

    return _build_result(data, bool(effective_key))


def parse_dji_binary_bytes(
    content: bytes,
    *,
    api_key: str | None = None,
    timeout_s: int = 120,
) -> DJILogResult:
    """Like ``parse_dji_binary`` but accepts raw bytes via a temp file."""
    suffix = ".txt"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tf.write(content)
        tmp_path = tf.name

    try:
        return parse_dji_binary(tmp_path, api_key=api_key, timeout_s=timeout_s)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def detect_log_version(filepath: str | Path, *, timeout_s: int = 30) -> int | None:
    """Return the DJI log version without parsing frames.

    Returns *None* if the file is not a recognised DJI log.
    """
    binary = _check_available()
    fp = Path(filepath)
    if not fp.exists():
        return None

    proc = subprocess.run(
        [binary, str(fp), "--json"],
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )

    if proc.returncode != 0:
        return None

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None

    return data.get("logVersion") or data.get("version")


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _raise_parse_error(proc: subprocess.CompletedProcess) -> None:
    stderr = proc.stderr.strip() if proc.stderr else ""
    stdout = proc.stdout.strip() if proc.stdout else ""

    combined = stderr or stdout or "unknown error"

    if "API key" in combined.lower() or "decrypt" in combined.lower():
        raise RuntimeError(
            "DJI log decryption failed: this v13+ encrypted log requires a DJI "
            "Developer API key.  Set DJI_API_KEY in the environment or provide "
            "an apiKey path in telemetry-frame-mapper config.yaml.\n\n"
            "To obtain a key: https://developer.dji.com/user → CREATE APP → "
            "Open API → copy the SDK key.\n\n"
            f"Subprocess output: {combined}"
        )

    raise RuntimeError(
        f"djirecord exited with code {proc.returncode}: {combined}"
    )


def _build_result(data: dict, decrypted: bool) -> DJILogResult:
    header_info = data.get("header", data.get("details", data))

    header = DJILogHeader(
        version=int(data.get("logVersion", data.get("version", 0))),
        aircraft_name=header_info.get("aircraftName") or header_info.get("aircraft_name"),
        aircraft_sn=header_info.get("aircraftSn") or header_info.get("aircraft_sn"),
        battery_sn=header_info.get("batterySn") or header_info.get("battery_sn"),
        camera_sn=header_info.get("cameraSn") or header_info.get("camera_sn"),
        rc_sn=header_info.get("rcSn") or header_info.get("rc_sn"),
        product_type=header_info.get("productType") or header_info.get("product_type"),
        start_time=header_info.get("startTime") or header_info.get("start_time"),
        total_distance_km=header_info.get("totalDistance") or header_info.get("total_distance"),
        max_height_m=header_info.get("maxHeight") or header_info.get("max_height"),
        total_time_s=header_info.get("totalTime") or header_info.get("total_time"),
    )

    raw_frames: list[dict] = data.get("frames", [])
    frames: list[DJILogFrame] = []
    for f in raw_frames:
        osd = f.get("osd", f)
        attitude = f.get("attitude", {})
        gimbal = f.get("gimbal", {})
        battery = f.get("battery", {})

        frames.append(
            DJILogFrame(
                timestamp_ms=float(osd.get("timeMs", osd.get("timestamp_ms", 0))),
                latitude=float(osd.get("latitude", 0)),
                longitude=float(osd.get("longitude", 0)),
                altitude_m=float(osd.get("altitude", osd.get("altitude_m", 0))),
                speed_ms=float(osd.get("speed", osd.get("speed_ms", 0))),
                heading=float(osd.get("heading", 0)),
                roll=_opt_float(attitude.get("roll")),
                pitch=_opt_float(attitude.get("pitch")),
                yaw=_opt_float(attitude.get("yaw")),
                gimbal_pitch=_opt_float(gimbal.get("pitch")),
                gimbal_roll=_opt_float(gimbal.get("roll")),
                gimbal_yaw=_opt_float(gimbal.get("yaw")),
                battery_voltage=_opt_float(battery.get("voltage")),
                battery_charge_pct=_opt_float(
                    battery.get("chargeLevel", battery.get("charge_pct"))
                ),
                battery_temperature_c=_opt_float(
                    battery.get("temperature", battery.get("temperature_c"))
                ),
            )
        )

    return DJILogResult(
        header=header,
        frames=frames,
        frame_count=len(frames),
        decrypted=decrypted,
    )


def _opt_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
