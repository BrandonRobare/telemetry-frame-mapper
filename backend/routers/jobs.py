from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import Reconstruction

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/")
def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: str | None = Query(None, min_length=1),
    db: DBSession = Depends(get_db),
):
    query = db.query(Reconstruction)
    if status is not None:
        query = query.filter(Reconstruction.status == status)

    reconstructions = (
        query.order_by(Reconstruction.started_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "type": "reconstruction",
            "session_id": r.session_id,
            "status": r.status,
            "preset": r.preset,
            "progress_pct": r.progress_pct,
            "step": r.step,
            "frames_used": r.frames_used,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "error_msg": r.error_msg,
        }
        for r in reconstructions
    ]
