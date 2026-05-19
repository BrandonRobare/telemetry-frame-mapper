from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config
from ..db.database import get_db
from ..db.models import Reconstruction, SessionFrameSelection, TargetArea
from ..services.reconstruction import (
    _compute_coverage_gaps,
    cancel_reconstruction,
    get_rec_log,
    start_reconstruction,
)

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
    training_metrics: list[dict] | None = None
    error_msg: str | None
    geo_transform: str | None
    splat_path: str | None

    model_config = {"from_attributes": True}

    @field_validator("training_metrics", mode="before")
    @classmethod
    def parse_training_metrics(cls, v: object) -> list[dict] | None:
        if isinstance(v, str):
            return json.loads(v)
        return v  # type: ignore[return-value]


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


class FrameSelectionIn(BaseModel):
    session_id: int
    image_ids: list[int]


@router.post("/frame-selection", status_code=204)
def set_frame_selection(body: FrameSelectionIn, db: DBSession = Depends(get_db)):
    try:
        db.query(SessionFrameSelection).filter(
            SessionFrameSelection.session_id == body.session_id
        ).delete()
        for image_id in body.image_ids:
            db.add(SessionFrameSelection(session_id=body.session_id, image_id=image_id))
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"Invalid frame selection: {exc}") from exc


@router.delete("/frame-selection/{session_id}", status_code=204)
def clear_frame_selection(session_id: int, db: DBSession = Depends(get_db)):
    try:
        db.query(SessionFrameSelection).filter(
            SessionFrameSelection.session_id == session_id
        ).delete()
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=422, detail=f"Failed to clear frame selection: {exc}"
        ) from exc


@router.get("/frame-selection/{session_id}")
def get_frame_selection(session_id: int, db: DBSession = Depends(get_db)):
    rows = db.query(SessionFrameSelection).filter(
        SessionFrameSelection.session_id == session_id
    ).all()
    return {"image_ids": [r.image_id for r in rows]}


@router.get("/{reconstruction_id}/splat")
def download_splat(
    reconstruction_id: int,
    lod: str = Query("full", pattern="^(full|medium|preview)$"),
    db: DBSession = Depends(get_db),
):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(status_code=202, detail="Reconstruction still in progress")

    path_map = {
        "full": rec.splat_path,
        "medium": rec.splat_medium_path,
        "preview": rec.splat_preview_path,
    }
    splat_path = path_map[lod]
    if not splat_path or not Path(splat_path).exists():
        raise HTTPException(status_code=404, detail=f"Splat file ({lod}) not found on disk")

    return FileResponse(
        splat_path,
        media_type="application/octet-stream",
        filename=f"splat_{reconstruction_id}_{lod}.ply",
    )


@router.get("/{reconstruction_id}/geo-transform")
def get_geo_transform(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if not rec.geo_transform:
        raise HTTPException(status_code=404, detail="Geo-transform not yet available")
    try:
        return json.loads(rec.geo_transform)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500, detail="Stored geo-transform data is malformed"
        ) from exc


@router.get("/{reconstruction_id}/log")
def get_log(
    reconstruction_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: DBSession = Depends(get_db),
):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    lines = get_rec_log(reconstruction_id)
    return {"lines": lines[-limit:]}


@router.get("/{reconstruction_id}/coverage-gaps")
def get_coverage_gaps(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(status_code=404, detail="Reconstruction not complete")
    if not rec.splat_path:
        raise HTTPException(status_code=404, detail="No splat available")

    splat_path = Path(rec.splat_path)

    if rec.coverage_gaps_path and Path(rec.coverage_gaps_path).exists():
        return json.loads(Path(rec.coverage_gaps_path).read_text())

    cfg = get_config()
    output_path = Path(cfg.exports_dir) / str(reconstruction_id) / "coverage_gaps.json"
    try:
        cells = _compute_coverage_gaps(splat_path, output_path)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Failed to compute coverage gaps: {exc}"
        ) from exc

    rec.coverage_gaps_path = str(output_path)
    db.commit()
    return cells
