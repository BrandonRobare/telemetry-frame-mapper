from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import SessionComparison
from ..services.reconstruction import diff_to_geojson, start_session_comparison

router = APIRouter(prefix="/comparisons", tags=["comparisons"])


class ComparisonIn(BaseModel):
    session_a_id: int
    session_b_id: int
    reconstruction_a_id: int
    reconstruction_b_id: int
    voxel_size_m: float = Field(default=0.5, gt=0)


class ComparisonOut(BaseModel):
    id: int
    session_a_id: int
    session_b_id: int
    reconstruction_a_id: int
    reconstruction_b_id: int
    status: str
    diff_path: str | None = None
    error_msg: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


def _comparison_or_404(comparison_id: int, db: DBSession) -> SessionComparison:
    comparison = db.query(SessionComparison).filter(SessionComparison.id == comparison_id).first()
    if not comparison:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return comparison


def _load_complete_diff(comparison: SessionComparison) -> dict:
    if comparison.status != "complete":
        raise HTTPException(status_code=202, detail="Comparison still in progress")
    if not comparison.diff_path:
        raise HTTPException(status_code=404, detail="Comparison diff not available")
    path = Path(comparison.diff_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Comparison diff file not found on disk")
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("", response_model=ComparisonOut, status_code=201)
def create_comparison(body: ComparisonIn, db: DBSession = Depends(get_db)):
    try:
        return start_session_comparison(
            body.session_a_id,
            body.session_b_id,
            body.reconstruction_a_id,
            body.reconstruction_b_id,
            db,
            voxel_size_m=body.voxel_size_m,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc


@router.get("/{comparison_id}", response_model=ComparisonOut)
def get_comparison(comparison_id: int, db: DBSession = Depends(get_db)):
    return _comparison_or_404(comparison_id, db)


@router.get("/{comparison_id}/diff")
def get_diff(comparison_id: int, db: DBSession = Depends(get_db)):
    comparison = _comparison_or_404(comparison_id, db)
    return _load_complete_diff(comparison)


@router.get("/{comparison_id}/diff.geojson")
def get_diff_geojson(comparison_id: int, db: DBSession = Depends(get_db)):
    comparison = _comparison_or_404(comparison_id, db)
    geojson = diff_to_geojson(_load_complete_diff(comparison))
    return JSONResponse(
        geojson,
        media_type="application/geo+json",
        headers={
            "Content-Disposition": f'attachment; filename="comparison_{comparison_id}.geojson"'
        },
    )


def _diff_metrics(diff: dict) -> dict:
    new_cells = diff.get("new", []) or []
    removed_cells = diff.get("removed", []) or []

    def volume(cells):
        return sum(float(c.get("size", 0) or 0) ** 3 for c in cells)

    def area(cells):
        return sum(float(c.get("size", 0) or 0) ** 2 for c in cells)

    return {
        "new_count": len(new_cells),
        "removed_count": len(removed_cells),
        "new_volume_m3": volume(new_cells),
        "removed_volume_m3": volume(removed_cells),
        "net_volume_m3": volume(new_cells) - volume(removed_cells),
        "changed_area_m2": area(new_cells) + area(removed_cells),
        "alignment": diff.get("alignment") or {"method": "none", "status": "not_applied"},
    }


@router.get("/{comparison_id}/metrics")
def get_comparison_metrics(comparison_id: int, db: DBSession = Depends(get_db)):
    comparison = _comparison_or_404(comparison_id, db)
    return _diff_metrics(_load_complete_diff(comparison))
