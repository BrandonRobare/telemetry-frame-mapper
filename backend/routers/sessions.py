from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel
import datetime

from ..db.database import get_db
from ..db.models import Session as SessionModel

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
