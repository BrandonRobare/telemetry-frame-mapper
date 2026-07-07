from __future__ import annotations

import json as _json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession

from backend.db.database import get_db
from backend.db.models import Reconstruction
from backend.services.job_queue import cancel_job, get_job
from backend.services.job_queue import list_jobs as list_queue_jobs

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
            "source_session_ids": (
                _json.loads(r.source_session_ids)
                if r.source_session_ids
                else None
            ),
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


@router.get("/queue")
def list_queue_entries(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: str | None = Query(None, min_length=1),
    job_type: str | None = Query(None, min_length=1),
):
    """List persistent job queue entries (survives API restarts)."""
    return list_queue_jobs(skip=skip, limit=limit, status=status, job_type=job_type)


@router.get("/queue/{job_id}")
def get_queue_entry(job_id: int):
    """Get a single job queue entry by id."""
    entry = get_job(job_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return entry


@router.post("/queue/{job_id}/cancel")
def cancel_queue_entry(job_id: int):
    """Cancel a pending or running job queue entry."""
    ok = cancel_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found or not cancellable")
    return {"ok": True}
