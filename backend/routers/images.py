from __future__ import annotations

import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import Footprint, Image

router = APIRouter(prefix="/images", tags=["images"])


class ImageOut(BaseModel):
    id: int
    session_id: int
    filename: str
    filepath: str
    thumb_path: str | None
    timestamp: datetime.datetime | None
    latitude: float | None
    longitude: float | None
    altitude_m: float | None
    gps_source: str | None
    yaw: float | None
    gimbal_pitch: float | None
    width: int | None
    height: int | None
    focal_length_mm: float | None
    sharpness_score: float | None
    brightness_score: float | None
    flag: str | None
    usable: bool | None
    notes: str | None

    model_config = {"from_attributes": True}


class ImagePatch(BaseModel):
    flag: str | None = None
    usable: bool | None = None


@router.get("", response_model=list[ImageOut])
def list_images(
    session_id: int,
    flag: str | None = None,
    has_footprint: bool | None = None,
    db: DBSession = Depends(get_db),
):
    q = db.query(Image).filter(Image.session_id == session_id)
    if flag is not None:
        q = q.filter(Image.flag == flag)
    if has_footprint is True:
        # Must have a matching Footprint row
        q = q.join(Footprint, Footprint.image_id == Image.id)
    elif has_footprint is False:
        # Must NOT have a matching Footprint row
        q = q.outerjoin(Footprint, Footprint.image_id == Image.id).filter(
            Footprint.id.is_(None)
        )
    return q.all()


@router.patch("/{image_id}", response_model=ImageOut)
def patch_image(image_id: int, body: ImagePatch, db: DBSession = Depends(get_db)):
    img = db.query(Image).filter(Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    if body.flag is not None:
        img.flag = body.flag
    if body.usable is not None:
        img.usable = body.usable
    db.commit()
    db.refresh(img)
    return img


@router.get("/{image_id}/thumb")
def get_thumb(image_id: int, db: DBSession = Depends(get_db)):
    img = db.query(Image).filter(Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    if not img.thumb_path:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return RedirectResponse(f"/{Path(img.thumb_path).as_posix()}")
