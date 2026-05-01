from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import FlightLog, FlightLogPoint, Image, Session as SessionModel
from ..services.flight_log_sync import match_images_to_log, parse_dji_csv

router = APIRouter(prefix="/flight-logs", tags=["flight-logs"])


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

    log = FlightLog(
        session_id=session_id,
        filename=file.filename,
        point_count=len(points),
    )
    db.add(log)
    db.flush()  # get log.id before adding points

    for p in points:
        # Store timestamp_s as a DateTime using epoch + offset
        ts = datetime.fromtimestamp(p["timestamp_s"], tz=timezone.utc).replace(tzinfo=None)
        point = FlightLogPoint(
            flight_log_id=log.id,
            timestamp=ts,
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
def match_preview(
    session_id: int,
    db: DBSession = Depends(get_db),
):
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
            "timestamp_s": pt.timestamp.timestamp() if pt.timestamp else 0.0,
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

    results = match_images_to_log(images, log_points_dicts, tolerance_s=2.0)
    return results


@router.post("/apply")
def apply_sync(
    session_id: int,
    db: DBSession = Depends(get_db),
):
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
            "timestamp_s": pt.timestamp.timestamp() if pt.timestamp else 0.0,
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

    matches = match_images_to_log(images, log_points_dicts, tolerance_s=2.0)

    # Build a lookup from image_id -> match
    match_map = {m["image_id"]: m for m in matches}

    applied = 0
    for img in images:
        if img.id in match_map:
            m = match_map[img.id]
            img.latitude = m["latitude"]
            img.longitude = m["longitude"]
            img.altitude_m = m["altitude_m"]
            applied += 1

    db.commit()
    return {"applied": applied}
