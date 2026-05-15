from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import Reconstruction, TargetArea
from ..services.reconstruction import cancel_reconstruction, start_reconstruction

router = APIRouter(prefix="/reconstruction", tags=["reconstruction"])

VALID_PRESETS = {"quick", "full"}


class StartIn(BaseModel):
    session_id: int
    preset: str = "quick"
    target_area_id: int | None = None

    @field_validator("preset")
    @classmethod
    def validate_preset(cls, v: str) -> str:
        if v not in VALID_PRESETS:
            raise ValueError(f"preset must be one of {VALID_PRESETS}")
        return v


class ReconstructionOut(BaseModel):
    id: int
    session_id: int
    status: str
    preset: str
    progress_pct: float
    step: str
    frames_used: int
    frames_registered: int | None
    gaussian_count: int | None
    psnr: float | None
    ssim: float | None
    error_msg: str | None
    geo_transform: str | None
    splat_path: str | None

    model_config = {"from_attributes": True}


@router.post("/start", response_model=ReconstructionOut, status_code=201)
def start(body: StartIn, db: DBSession = Depends(get_db)):
    target_area_geojson: str | None = None
    if body.target_area_id is not None:
        ta = db.query(TargetArea).filter(TargetArea.id == body.target_area_id).first()
        if not ta:
            raise HTTPException(status_code=404, detail="Target area not found")
        if not ta.geom_geojson:
            raise HTTPException(status_code=422, detail="Target area has no geometry defined")
        target_area_geojson = ta.geom_geojson
    try:
        rec = start_reconstruction(
            body.session_id, body.preset, db,
            target_area_geojson=target_area_geojson,
        )
    except ValueError as exc:
        msg = str(exc)
        if "already in progress" in msg:
            raise HTTPException(status_code=409, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
    return rec


@router.get("/{reconstruction_id}/status", response_model=ReconstructionOut)
def get_status(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    return rec


@router.delete("/{reconstruction_id}")
def cancel(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    cancel_reconstruction(reconstruction_id)
    return {"ok": True}
