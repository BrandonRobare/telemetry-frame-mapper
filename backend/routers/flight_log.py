from __future__ import annotations

import calendar
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session as DBSession

from ..core.config import load_config
from ..db.database import get_db
from ..db.models import FlightLog, FlightLogPoint, Footprint, Image
from ..db.models import Session as SessionModel
from ..services.flight_log_sync import match_images_to_log, parse_dji_csv
from ..services.geometry import compute_footprint

router = APIRouter(prefix="/flight-logs", tags=["flight-logs"])


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
        db.query(Image)
        .filter(Image.session_id == session_id, Image.timestamp.isnot(None))
        .all()
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

    content = await file.read()
    points = parse_dji_csv(content)

    if not points:
        raise HTTPException(
            status_code=422,
            detail="No valid data rows found in flight log CSV",
        )

    log = FlightLog(
        session_id=session_id,
        filename=file.filename,
        point_count=len(points),
    )
    db.add(log)
    db.flush()  # get log.id before adding points

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
        "point_count": log.point_count,
    }


@router.get("/match-preview")
def match_preview(session_id: int, db: DBSession = Depends(get_db)):
    _, log_points_dicts, images = _get_log_points_and_images(session_id, db)
    return match_images_to_log(images, log_points_dicts, tolerance_s=2.0)


@router.post("/apply")
def apply_sync(session_id: int, db: DBSession = Depends(get_db)):
    _, log_points_dicts, images = _get_log_points_and_images(session_id, db)
    matches = match_images_to_log(images, log_points_dicts, tolerance_s=2.0)

    match_map = {m["image_id"]: m for m in matches}
    cfg = load_config()
    applied = 0
    for img in images:
        if img.id in match_map:
            m = match_map[img.id]
            img.latitude = m["latitude"]
            img.longitude = m["longitude"]
            img.altitude_m = m["altitude_m"]

            if img.footprint is not None:
                db.delete(img.footprint)
                db.flush()

            if (
                img.latitude is not None
                and img.longitude is not None
                and img.altitude_m is not None
            ):
                fp = compute_footprint(
                    lat=img.latitude,
                    lon=img.longitude,
                    altitude_m=img.altitude_m,
                    fov_horizontal_deg=cfg.fov_horizontal_deg,
                    fov_vertical_deg=cfg.fov_vertical_deg,
                    yaw_deg=img.yaw,
                    target_crs=cfg.target_crs,
                )
                if fp:
                    db.add(Footprint(
                        image_id=img.id,
                        geom_wkt=fp.get("geom_wkt"),
                        geom_geojson=fp.get("geom_geojson"),
                        ground_width_m=fp.get("ground_width_m"),
                        ground_height_m=fp.get("ground_height_m"),
                        heading_estimated=fp.get("heading_estimated", True),
                    ))
            applied += 1

    db.commit()
    return {"applied": applied}
