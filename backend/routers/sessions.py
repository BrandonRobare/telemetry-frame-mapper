from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel
import datetime

from ..db.database import get_db, SessionLocal
from ..db.models import Session as SessionModel
from ..services.ingest_orchestrator import get_progress, start_import

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionOut(BaseModel):
    id: int
    name: str
    folder_path: str
    imported_at: datetime.datetime | None
    photo_count: int
    usable_count: int

    model_config = {"from_attributes": True}


class DeleteOut(BaseModel):
    ok: bool


@router.get("/", response_model=list[SessionOut])
def list_sessions(db: DBSession = Depends(get_db)):
    return db.query(SessionModel).order_by(SessionModel.imported_at.desc()).all()


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: DBSession = Depends(get_db)):
    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s


@router.delete("/{session_id}", response_model=DeleteOut)
def delete_session(session_id: int, db: DBSession = Depends(get_db)):
    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


class ImportRequest(BaseModel):
    folder_path: str
    name: str


@router.post("/import", response_model=SessionOut)
def import_session(req: ImportRequest, db: DBSession = Depends(get_db)):
    folder = Path(req.folder_path)
    if not folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Folder not found: {req.folder_path}")
    s = SessionModel(
        name=req.name,
        folder_path=req.folder_path,
        imported_at=datetime.datetime.utcnow(),
        photo_count=0,
        usable_count=0,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    start_import(s.id, folder, SessionLocal)
    return s


@router.get("/{session_id}/progress")
def session_progress(session_id: int):
    return get_progress(session_id)
