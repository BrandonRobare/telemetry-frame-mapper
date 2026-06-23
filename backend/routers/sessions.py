from __future__ import annotations

import datetime
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config
from ..db.database import SessionLocal, get_db
from ..db.models import Image, Reconstruction
from ..db.models import Session as SessionModel
from ..services.artifact_cleanup import cleanup_session_artifacts
from ..services.ingest_orchestrator import get_progress, start_import
from ..services.reconstruction import cancel_reconstruction

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
    reconstructions = db.query(Reconstruction).filter(
        Reconstruction.session_id == session_id
    ).all()
    images = db.query(Image).filter(Image.session_id == session_id).all()
    for rec in reconstructions:
        cancel_reconstruction(rec.id)
    cleanup_session_artifacts(session_id, images, reconstructions, get_config())
    db.delete(s)
    db.commit()
    return {"ok": True}


class ImportRequest(BaseModel):
    folder_path: str
    name: str


@router.post("/import", response_model=SessionOut)
def import_session(req: ImportRequest, db: DBSession = Depends(get_db)):
    cfg = get_config()
    imports_root = Path(cfg.imports_dir).resolve()
    raw = req.folder_path.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Folder path must not be empty")
    user_path = PurePosixPath(raw.replace("\\", "/"))
    if user_path.is_absolute():
        raise HTTPException(status_code=400, detail="Folder path must be relative")
    if any(part in ("", ".", "..") for part in user_path.parts):
        raise HTTPException(status_code=400, detail="Folder path contains invalid segments")
    folder = imports_root.joinpath(*user_path.parts).resolve()
    if not folder.is_relative_to(imports_root):
        raise HTTPException(status_code=400, detail="Folder must be inside the imports directory")
    if not folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Folder not found: {raw}")
    s = SessionModel(
        name=req.name,
        folder_path=str(folder),
        imported_at=datetime.datetime.now(datetime.timezone.utc),
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
