from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import FlightEntry, FlightLog, FlightLogPoint
from ..db.models import Session as SessionModel

router = APIRouter(prefix="/sessions", tags=["flight-entries"])


class FlightEntryIn(BaseModel):
    battery_id: str | None = None
    start_pct: float | None = Field(default=None, ge=0, le=100)
    end_pct: float | None = Field(default=None, ge=0, le=100)
    duration_s: float | None = Field(default=None, ge=0)
    notes: str | None = None


class FlightEntryOut(BaseModel):
    id: int
    session_id: int
    battery_id: str | None
    start_pct: float | None
    end_pct: float | None
    duration_s: float | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


def _get_session_or_404(session_id: int, db: DBSession) -> SessionModel:
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _derive_duration_s(session_id: int, db: DBSession) -> float | None:
    """Derive flight duration from the session's flight-log telemetry span, if any."""
    first, last = (
        db.query(func.min(FlightLogPoint.timestamp), func.max(FlightLogPoint.timestamp))
        .join(FlightLog, FlightLogPoint.flight_log_id == FlightLog.id)
        .filter(FlightLog.session_id == session_id)
        .one()
    )
    if first is None or last is None:
        return None
    return (last - first).total_seconds()


@router.post(
    "/{session_id}/flight-entries",
    response_model=FlightEntryOut,
    status_code=201,
)
def create_flight_entry(
    session_id: int,
    body: FlightEntryIn,
    db: DBSession = Depends(get_db),
):
    _get_session_or_404(session_id, db)
    duration_s = body.duration_s
    if duration_s is None:
        duration_s = _derive_duration_s(session_id, db)
    entry = FlightEntry(
        session_id=session_id,
        battery_id=body.battery_id,
        start_pct=body.start_pct,
        end_pct=body.end_pct,
        duration_s=duration_s,
        notes=body.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get(
    "/{session_id}/flight-entries",
    response_model=list[FlightEntryOut],
)
def list_flight_entries(session_id: int, db: DBSession = Depends(get_db)):
    _get_session_or_404(session_id, db)
    return (
        db.query(FlightEntry)
        .filter(FlightEntry.session_id == session_id)
        .order_by(FlightEntry.created_at)
        .all()
    )


@router.delete("/{session_id}/flight-entries/{entry_id}")
def delete_flight_entry(
    session_id: int,
    entry_id: int,
    db: DBSession = Depends(get_db),
):
    entry = (
        db.query(FlightEntry)
        .filter(FlightEntry.id == entry_id, FlightEntry.session_id == session_id)
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Flight entry not found")
    db.delete(entry)
    db.commit()
    return {"ok": True}
