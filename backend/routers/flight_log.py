from __future__ import annotations

import calendar
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_dji_api_key, get_upload_limits_config
from ..db.database import get_db
from ..db.models import FlightLog, FlightLogPoint, Image
from ..db.models import Session as SessionModel
from ..services.flight_log_sync import build_offset_preview, match_images_to_log, parse_dji_csv

router = APIRouter(prefix="/flight-logs", tags=["flight-logs"])

_FLIGHT_LOG_CHUNK_SIZE = 1024 * 1024

# Allowed extensions for DJI binary logs.
_DJI_EXTENSIONS = {".txt"}


async def _read_upload_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = await file.read(_FLIGHT_LOG_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Flight log upload exceeds {max_bytes} byte limit",
            )
        chunks.append(chunk)

    return b"".join(chunks)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utc_timestamp_to_naive(ts: float) -> datetime:
    """Convert a Unix epoch float to a naive UTC datetime for DB storage."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


def _naive_utc_to_timestamp(dt: datetime) -> float:
    """Convert a naive UTC datetime back to a Unix epoch float.

    Uses ``calendar.timegm`` which always interprets the input as UTC,
    avoiding the platform-dependent behaviour of ``datetime.timestamp()``
    on naive datetimes (which assumes local time).
    """
    return float(calendar.timegm(dt.timetuple())) + dt.microsecond / 1_000_000


def _get_log_points_and_images(
    session_id: int,
    db: DBSession,
) -> tuple[FlightLog, list[dict], list[Image]]:
    """Shared loader for match-preview and apply-sync.

    Returns ``(log, log_points_dicts, images_with_timestamp)`` or raises 404.
    """
    log = (
        db.query(FlightLog)
        .filter(FlightLog.session_id == session_id)
        .order_by(FlightLog.uploaded_at.desc())
        .first()
    )
    if not log:
        raise HTTPException(status_code=404, detail="No flight log found for this session")

    log_points_dicts = [
        {
            "timestamp_s": _naive_utc_to_timestamp(pt.timestamp) if pt.timestamp else 0.0,
            "latitude": pt.latitude,
            "longitude": pt.longitude,
            "altitude_m": pt.altitude_m,
        }
        for pt in log.points
    ]

    images = (
        db.query(Image).filter(Image.session_id == session_id, Image.timestamp.isnot(None)).all()
    )
    return log, log_points_dicts, images


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_flight_log(
    file: UploadFile = File(...),
    session_id: int = Form(...),
    db: DBSession = Depends(get_db),
):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    limits = get_upload_limits_config()
    content = await _read_upload_with_limit(file, limits["flight_log_max_bytes"])

    # --- sniff: DJI binary (.txt) or CSV? -----------------------------------
    ext = os.path.splitext(file.filename or "")[1].lower()
    first_bytes = content[:64].strip()

    if ext in _DJI_EXTENSIONS or (first_bytes and is_dji_binary_header(first_bytes)):
        return await _upload_dji_binary(session_id, file.filename or "", content, db)

    # Fallback: existing CSV path
    points = parse_dji_csv(content)

    if not points:
        raise HTTPException(
            status_code=422,
            detail="No valid data rows found in flight log CSV",
        )

    log = FlightLog(
        session_id=session_id,
        filename=file.filename,
        format="csv",
        point_count=len(points),
    )
    db.add(log)
    db.flush()

    for p in points:
        point = FlightLogPoint(
            flight_log_id=log.id,
            timestamp=_utc_timestamp_to_naive(p["timestamp_s"]),
            latitude=p["latitude"],
            longitude=p["longitude"],
            altitude_m=p["altitude_m"],
        )
        db.add(point)

    db.commit()
    db.refresh(log)

    return {
        "id": log.id,
        "session_id": log.session_id,
        "filename": log.filename,
        "format": log.format,
        "point_count": log.point_count,
        "log_version": None,
        "aircraft_name": None,
        "encrypted": False,
    }


async def _upload_dji_binary(
    session_id: int,
    filename: str,
    content: bytes,
    db: DBSession,
) -> dict:
    """Parse a DJI .txt binary log and persist FlightLog + FlightLogPoint rows."""
    from ..services.dji_log_parser import (
        dji_parser_available,
        parse_dji_binary_bytes,
    )

    if not dji_parser_available():
        raise HTTPException(
            status_code=501,
            detail="DJI log parsing requires pydjirecord; install with: pip install pydjirecord",
        )

    api_key = get_dji_api_key()

    try:
        result = parse_dji_binary_bytes(content, api_key=api_key)
    except RuntimeError as exc:
        msg = str(exc)
        if "API key" in msg.lower() or "decrypt" in msg.lower():
            raise HTTPException(status_code=422, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc

    return _persist_dji_result(session_id, filename, content, result, db)


def _persist_dji_result(
    session_id: int,
    filename: str,
    _content: bytes,
    result,
    db: DBSession,
) -> dict:
    log = FlightLog(
        session_id=session_id,
        filename=filename,
        format="dji_binary",
        point_count=result.frame_count,
        log_version=result.header.version,
        aircraft_name=result.header.aircraft_name,
        aircraft_sn=result.header.aircraft_sn,
        encrypted=not result.decrypted and result.header.version >= 13,
    )
    db.add(log)
    db.flush()

    for frame in result.frames:
        point = FlightLogPoint(
            flight_log_id=log.id,
            timestamp=_utc_timestamp_to_naive(frame.timestamp_ms / 1000.0),
            latitude=frame.latitude,
            longitude=frame.longitude,
            altitude_m=frame.altitude_m,
            speed_ms=frame.speed_ms,
            heading=frame.heading,
            roll=frame.roll,
            pitch=frame.pitch,
            yaw=frame.yaw,
            gimbal_pitch=frame.gimbal_pitch,
            gimbal_roll=frame.gimbal_roll,
            gimbal_yaw=frame.gimbal_yaw,
            battery_voltage=frame.battery_voltage,
            battery_charge_pct=frame.battery_charge_pct,
            battery_temperature_c=frame.battery_temperature_c,
        )
        db.add(point)

    db.commit()
    db.refresh(log)

    return {
        "id": log.id,
        "session_id": log.session_id,
        "filename": log.filename,
        "format": log.format,
        "point_count": log.point_count,
        "log_version": log.log_version,
        "aircraft_name": log.aircraft_name,
        "encrypted": log.encrypted,
    }


def is_dji_binary_header(data: bytes) -> bool:
    """Heuristic: DJI binary logs have a version byte (1-14 or >=128) at offset 10.

    The DJI prefix layout (100 bytes, little-endian)::

        detail_offset : u64   (bytes 0-7)
        detail_length : u16   (bytes 8-9)
        version       : u8    (byte 10)
        ...
    """
    if len(data) < 16:
        return False

    try:
        version_byte = data[10]
    except IndexError:
        return False

    # Log versions 1-14 are unencrypted; 128+ are encrypted
    return 1 <= version_byte <= 14 or version_byte >= 128


@router.get("/match-preview")
def match_preview(
    session_id: int,
    offset_s: float = 0.0,
    tolerance_s: float = Query(2.0, ge=0.0),
    db: DBSession = Depends(get_db),
):
    _, log_points_dicts, images = _get_log_points_and_images(session_id, db)
    return match_images_to_log(
        images,
        log_points_dicts,
        tolerance_s=tolerance_s,
        offset_s=offset_s,
    )


@router.get("/offset-preview")
def offset_preview(
    session_id: int,
    offset_s: float = 0.0,
    tolerance_s: float = Query(2.0, ge=0.0),
    window_s: float = Query(10.0, ge=0.0, le=300.0),
    step_s: float = Query(1.0, gt=0.0, le=60.0),
    db: DBSession = Depends(get_db),
):
    _, log_points_dicts, images = _get_log_points_and_images(session_id, db)
    return build_offset_preview(
        images,
        log_points_dicts,
        tolerance_s=tolerance_s,
        center_offset_s=offset_s,
        window_s=window_s,
        step_s=step_s,
    )


@router.post("/apply")
def apply_sync(
    session_id: int,
    offset_s: float = 0.0,
    tolerance_s: float = Query(2.0, ge=0.0),
    db: DBSession = Depends(get_db),
):
    _, log_points_dicts, images = _get_log_points_and_images(session_id, db)
    matches = match_images_to_log(
        images,
        log_points_dicts,
        tolerance_s=tolerance_s,
        offset_s=offset_s,
    )

    match_map = {m["image_id"]: m for m in matches}
    applied = 0
    for img in images:
        if img.id in match_map:
            m = match_map[img.id]
            if img.original_latitude is None and img.latitude is not None:
                img.original_latitude = img.latitude
            if img.original_longitude is None and img.longitude is not None:
                img.original_longitude = img.longitude
            if img.original_altitude_m is None and img.altitude_m is not None:
                img.original_altitude_m = img.altitude_m
            img.synced_latitude = m["latitude"]
            img.synced_longitude = m["longitude"]
            img.synced_altitude_m = m["altitude_m"]
            img.latitude = m["latitude"]
            img.longitude = m["longitude"]
            img.altitude_m = m["altitude_m"]
            img.gps_source = "flight_log"
            applied += 1

    db.commit()
    return {"applied": applied}