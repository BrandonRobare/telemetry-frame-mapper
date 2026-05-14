from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import MissionPlan, TargetArea
from ..services.mission_planner import generate_lawnmower, write_gpx, write_kml

router = APIRouter(prefix="/plans", tags=["plans"])

# Anchor exports dir to the package root so it resolves correctly regardless
# of the working directory at runtime.
EXPORTS_DIR = Path(__file__).parent.parent / "exports"


class PlanIn(BaseModel):
    target_area_id: int
    altitude_ft: float
    side_overlap_pct: float
    forward_overlap_pct: float


class PlanOut(BaseModel):
    id: int
    target_area_id: int
    altitude_ft: float | None
    side_overlap_pct: float | None
    forward_overlap_pct: float | None
    lane_count: int | None
    total_distance_m: float | None
    lanes_geojson: str | None
    kml_path: str | None
    gpx_path: str | None

    model_config = {"from_attributes": True}


@router.post("/generate", response_model=PlanOut)
def generate_plan(body: PlanIn, db: DBSession = Depends(get_db)):
    if body.side_overlap_pct >= 1.0:
        raise HTTPException(status_code=422, detail="side_overlap_pct must be < 1.0")
    if body.forward_overlap_pct >= 1.0:
        raise HTTPException(status_code=422, detail="forward_overlap_pct must be < 1.0")

    area = db.query(TargetArea).filter(TargetArea.id == body.target_area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Target area not found")

    result = generate_lawnmower(
        target_geojson=area.geom_geojson,
        altitude_ft=body.altitude_ft,
        side_overlap=body.side_overlap_pct,
        forward_overlap=body.forward_overlap_pct,
    )

    plan = MissionPlan(
        target_area_id=body.target_area_id,
        altitude_ft=body.altitude_ft,
        side_overlap_pct=body.side_overlap_pct,
        forward_overlap_pct=body.forward_overlap_pct,
        lane_count=result["lane_count"],
        total_distance_m=result["total_distance_m"],
        lanes_geojson=result["lanes_geojson"],
        lane_spacing_ft=None,
        batteries_estimated=None,
        coverage_run_id=None,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    kml_path = write_kml(plan.id, result["lanes_geojson"], EXPORTS_DIR)
    gpx_path = write_gpx(plan.id, result["lanes_geojson"], EXPORTS_DIR)

    plan.kml_path = str(kml_path)
    plan.gpx_path = str(gpx_path)
    db.commit()
    db.refresh(plan)

    return plan


@router.get("/{plan_id}/kml")
def download_kml(plan_id: int, db: DBSession = Depends(get_db)):
    plan = db.query(MissionPlan).filter(MissionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if not plan.kml_path:
        raise HTTPException(status_code=404, detail="KML file not available")
    kml_file = Path(plan.kml_path).resolve()
    if not kml_file.exists():
        raise HTTPException(status_code=404, detail="KML file not found on disk")
    return FileResponse(
        str(kml_file),
        media_type="application/vnd.google-earth.kml+xml",
        filename=f"plan_{plan_id}.kml",
    )


@router.get("/{plan_id}/gpx")
def download_gpx(plan_id: int, db: DBSession = Depends(get_db)):
    plan = db.query(MissionPlan).filter(MissionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if not plan.gpx_path:
        raise HTTPException(status_code=404, detail="GPX file not available")
    gpx_file = Path(plan.gpx_path).resolve()
    if not gpx_file.exists():
        raise HTTPException(status_code=404, detail="GPX file not found on disk")
    return FileResponse(
        str(gpx_file),
        media_type="application/gpx+xml",
        filename=f"plan_{plan_id}.gpx",
    )
