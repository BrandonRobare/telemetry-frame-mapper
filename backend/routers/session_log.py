from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import SessionLogEntry

router = APIRouter(prefix="/session-log", tags=["session-log"])


class LogEntryOut(BaseModel):
    id: int
    session_id: int | None
    event_type: str | None
    coverage_pct: float | None
    photo_count: int | None
    message: str | None
    timestamp: datetime.datetime | None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[LogEntryOut])
def list_session_log(session_id: int, db: DBSession = Depends(get_db)):
    return (
        db.query(SessionLogEntry)
        .filter(SessionLogEntry.session_id == session_id)
        .order_by(SessionLogEntry.timestamp.desc())
        .all()
    )
