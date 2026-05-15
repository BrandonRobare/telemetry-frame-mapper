from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import Reconstruction

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/")
def list_jobs(db: DBSession = Depends(get_db)):
    reconstructions = (
        db.query(Reconstruction)
        .order_by(Reconstruction.started_at.desc())
        .limit(50)
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
