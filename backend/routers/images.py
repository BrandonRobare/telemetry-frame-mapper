from __future__ import annotations

import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config
from ..db.database import get_db
from ..db.models import Footprint, Image, Reconstruction, ReconstructionFrame

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
    colmap_error_px: float | None = None
    flag: str | None
    usable: bool | None
    notes: str | None

    model_config = {"from_attributes": True}


class ImagePatch(BaseModel):
    flag: str | None = None
    usable: bool | None = None


class ImageBulkPatch(BaseModel):
    image_ids: list[int]
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
    images = q.all()

    # Build reproj error map from most recent completed reconstruction
    reproj_map: dict[int, float] = {}
    latest = (
        db.query(Reconstruction.id)
        .filter(Reconstruction.session_id == session_id, Reconstruction.status == "complete")
        .order_by(Reconstruction.id.desc())
        .first()
    )
    if latest:
        frames = db.query(ReconstructionFrame).filter(
            ReconstructionFrame.reconstruction_id == latest.id
        ).all()
        reproj_map = {f.image_id: f.colmap_error_px for f in frames}

    return [
        ImageOut.model_validate(img).model_copy(update={"colmap_error_px": reproj_map.get(img.id)})
        for img in images
    ]


@router.patch("/bulk")
def bulk_patch_images(body: ImageBulkPatch, db: DBSession = Depends(get_db)) -> dict:
    """Apply a flag and/or usable change to many images in one request.

    Defined before ``/{image_id}`` so the literal ``bulk`` path is not parsed as
    an id. Returns the number of rows updated.
    """
    if not body.image_ids:
        return {"updated": 0}
    if body.flag is None and body.usable is None:
        raise HTTPException(status_code=400, detail="Provide flag and/or usable")
    values: dict = {}
    if body.flag is not None:
        values["flag"] = body.flag
    if body.usable is not None:
        values["usable"] = body.usable
    updated = (
        db.query(Image)
        .filter(Image.id.in_(body.image_ids))
        .update(values, synchronize_session=False)
    )
    db.commit()
    return {"updated": updated}


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
    thumb_path = Path(img.thumb_path)
    if thumb_path.is_absolute():
        processed_dir = Path(get_config().processed_dir).resolve()
        try:
            thumb_path = Path("processed") / thumb_path.resolve().relative_to(processed_dir)
        except ValueError:
            thumb_path = Path("processed") / thumb_path.name
    return RedirectResponse(f"/{thumb_path.as_posix()}")
