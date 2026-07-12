from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import Defect, DefectImage, Image
from ..db.models import Session as SessionModel

router = APIRouter(prefix="/sessions", tags=["defects"])

# Fixed vocabulary for defect categories/severity — kept small and field-oriented rather than
# open-ended free text so the list view and any future reporting can group reliably.
DefectCategory = Literal[
    "crack", "corrosion", "vegetation", "water_damage", "missing_material", "other"
]
DefectSeverity = Literal["low", "medium", "high"]


class DefectImageOut(BaseModel):
    id: int
    filename: str
    latitude: float | None
    longitude: float | None
    thumb_path: str | None

    model_config = {"from_attributes": True}


class DefectIn(BaseModel):
    category: DefectCategory
    severity: DefectSeverity | None = None
    note: str | None = None
    image_ids: list[int] = Field(min_length=1)


class DefectPatch(BaseModel):
    category: DefectCategory | None = None
    severity: DefectSeverity | None = None
    note: str | None = None
    image_ids: list[int] | None = Field(default=None, min_length=1)


class DefectOut(BaseModel):
    id: int
    session_id: int
    category: str
    severity: str | None
    note: str | None
    created_at: datetime
    image_ids: list[int]
    images: list[DefectImageOut]

    model_config = {"from_attributes": True}


def _get_session_or_404(session_id: int, db: DBSession) -> SessionModel:
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _get_defect_or_404(session_id: int, defect_id: int, db: DBSession) -> Defect:
    defect = (
        db.query(Defect)
        .filter(Defect.id == defect_id, Defect.session_id == session_id)
        .first()
    )
    if defect is None:
        raise HTTPException(status_code=404, detail="Defect not found")
    return defect


def _validate_image_ids(session_id: int, image_ids: list[int], db: DBSession) -> None:
    found = (
        db.query(Image.id)
        .filter(Image.id.in_(image_ids), Image.session_id == session_id)
        .all()
    )
    found_ids = {row[0] for row in found}
    missing = set(image_ids) - found_ids
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"image_ids not found in session {session_id}: {sorted(missing)}",
        )


def _serialize_defect(defect: Defect) -> DefectOut:
    images = [link.image for link in defect.image_links]
    return DefectOut(
        id=defect.id,
        session_id=defect.session_id,
        category=defect.category,
        severity=defect.severity,
        note=defect.note,
        created_at=defect.created_at,
        image_ids=[img.id for img in images],
        images=[DefectImageOut.model_validate(img) for img in images],
    )


@router.post("/{session_id}/defects", response_model=DefectOut, status_code=201)
def create_defect(session_id: int, body: DefectIn, db: DBSession = Depends(get_db)):
    _get_session_or_404(session_id, db)
    image_ids = list(dict.fromkeys(body.image_ids))  # de-dupe, preserve order
    _validate_image_ids(session_id, image_ids, db)

    defect = Defect(
        session_id=session_id,
        category=body.category,
        severity=body.severity,
        note=body.note,
    )
    db.add(defect)
    db.commit()
    db.refresh(defect)

    for image_id in image_ids:
        db.add(DefectImage(defect_id=defect.id, image_id=image_id))
    db.commit()
    db.refresh(defect)
    return _serialize_defect(defect)


@router.get("/{session_id}/defects", response_model=list[DefectOut])
def list_defects(
    session_id: int,
    category: DefectCategory | None = None,
    db: DBSession = Depends(get_db),
):
    _get_session_or_404(session_id, db)
    q = db.query(Defect).filter(Defect.session_id == session_id)
    if category is not None:
        q = q.filter(Defect.category == category)
    defects = q.order_by(Defect.created_at).all()
    return [_serialize_defect(d) for d in defects]


@router.get("/{session_id}/defects/{defect_id}", response_model=DefectOut)
def get_defect(session_id: int, defect_id: int, db: DBSession = Depends(get_db)):
    defect = _get_defect_or_404(session_id, defect_id, db)
    return _serialize_defect(defect)


@router.patch("/{session_id}/defects/{defect_id}", response_model=DefectOut)
def patch_defect(
    session_id: int,
    defect_id: int,
    body: DefectPatch,
    db: DBSession = Depends(get_db),
):
    defect = _get_defect_or_404(session_id, defect_id, db)
    if body.category is not None:
        defect.category = body.category
    if body.severity is not None:
        defect.severity = body.severity
    if body.note is not None:
        defect.note = body.note
    if body.image_ids is not None:
        image_ids = list(dict.fromkeys(body.image_ids))
        _validate_image_ids(session_id, image_ids, db)
        defect.image_links.clear()
        db.flush()
        for image_id in image_ids:
            db.add(DefectImage(defect_id=defect.id, image_id=image_id))
    db.commit()
    db.refresh(defect)
    return _serialize_defect(defect)


@router.delete("/{session_id}/defects/{defect_id}")
def delete_defect(session_id: int, defect_id: int, db: DBSession = Depends(get_db)):
    defect = _get_defect_or_404(session_id, defect_id, db)
    db.delete(defect)
    db.commit()
    return {"ok": True}
