from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config
from ..db.database import get_db
from ..db.models import CoverageRun, MissionPlan, TargetArea
from ..services.mission_planner import (
    estimate_batteries,
    generate_lawnmower,
    generate_lawnmower_from_gaps,
    segment_plan,
    validate_plan,
    write_gpx,
    write_kml,
)

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
    batteries_estimated: float | None
    lanes_geojson: str | None
    kml_path: str | None
    gpx_path: str | None

    model_config = {"from_attributes": True}


class PlanGenerateFromGapsIn(BaseModel):
    coverage_run_id: int
    altitude_ft: float
    side_overlap_pct: float
    forward_overlap_pct: float


class ValidationOut(BaseModel):
    plan_id: int
    valid: bool
    warnings: list[str]
    violations: list[str]


class SegmentOut(BaseModel):
    index: int
    from_lane: int
    to_lane: int
    distance_m: float
    landing_wpt: list[float] | None = None
    resume_wpt: list[float] | None = None
    lanes_geojson: str | None = None
    kml_path: str | None = None
    gpx_path: str | None = None


# ---------------------------------------------------------------------------
# Generate plan from target area
# ---------------------------------------------------------------------------


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

    batteries = estimate_batteries(total_distance_m=result["total_distance_m"])

    plan = MissionPlan(
        target_area_id=body.target_area_id,
        altitude_ft=body.altitude_ft,
        side_overlap_pct=body.side_overlap_pct,
        forward_overlap_pct=body.forward_overlap_pct,
        lane_count=result["lane_count"],
        total_distance_m=result["total_distance_m"],
        batteries_estimated=batteries,
        lanes_geojson=result["lanes_geojson"],
        lane_spacing_ft=None,
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


# ---------------------------------------------------------------------------
# Validate plan
# ---------------------------------------------------------------------------


@router.post("/{plan_id}/validate", response_model=ValidationOut)
def validate_mission_plan(plan_id: int, db: DBSession = Depends(get_db)):
    plan = db.query(MissionPlan).filter(MissionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if not plan.lanes_geojson:
        raise HTTPException(status_code=422, detail="Plan has no lane geometry")

    config = get_config()

    result = validate_plan(
        lanes_geojson=plan.lanes_geojson,
        altitude_ft=plan.altitude_ft or 200,
        side_overlap=plan.side_overlap_pct or 0.7,
        forward_overlap=plan.forward_overlap_pct or 0.8,
        battery_range_m=config.battery_range_m,
    )

    return ValidationOut(
        plan_id=plan_id,
        valid=result.valid,
        warnings=result.warnings,
        violations=result.violations,
    )


# ---------------------------------------------------------------------------
# Multi-battery segmentation
# ---------------------------------------------------------------------------


@router.get("/{plan_id}/segments", response_model=list[SegmentOut])
def get_plan_segments(plan_id: int, db: DBSession = Depends(get_db)):
    plan = db.query(MissionPlan).filter(MissionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if not plan.lanes_geojson:
        raise HTTPException(status_code=404, detail="Plan has no lane geometry")

    config = get_config()

    segments = segment_plan(
        lanes_geojson=plan.lanes_geojson,
        total_distance_m=plan.total_distance_m or 0,
        battery_range_m=config.battery_range_m,
    )

    out: list[SegmentOut] = []
    for seg in segments:
        kml_path = write_kml(
            plan.id, seg.lanes_geojson, EXPORTS_DIR, suffix=f"_seg_{seg.index}"
        )
        gpx_path = write_gpx(
            plan.id, seg.lanes_geojson, EXPORTS_DIR, suffix=f"_seg_{seg.index}"
        )
        out.append(
            SegmentOut(
                index=seg.index,
                from_lane=seg.from_lane,
                to_lane=seg.to_lane,
                distance_m=seg.distance_m,
                landing_wpt=list(seg.landing_wpt) if seg.landing_wpt else None,
                resume_wpt=list(seg.resume_wpt) if seg.resume_wpt else None,
                lanes_geojson=seg.lanes_geojson,
                kml_path=str(kml_path),
                gpx_path=str(gpx_path),
            )
        )

    return out


# ---------------------------------------------------------------------------
# Gap-based re-fly plan
# ---------------------------------------------------------------------------


@router.post("/generate-from-gaps", response_model=PlanOut)
def generate_plan_from_gaps(body: PlanGenerateFromGapsIn, db: DBSession = Depends(get_db)):
    cov_run = db.query(CoverageRun).filter(CoverageRun.id == body.coverage_run_id).first()
    if not cov_run:
        raise HTTPException(status_code=404, detail="Coverage run not found")
    if not cov_run.gap_geojson:
        raise HTTPException(status_code=422, detail="Coverage run has no gap geometry")

    result = generate_lawnmower_from_gaps(
        gap_geojson=cov_run.gap_geojson,
        altitude_ft=body.altitude_ft,
        side_overlap=body.side_overlap_pct,
        forward_overlap=body.forward_overlap_pct,
    )

    if result is None:
        raise HTTPException(status_code=422, detail="Could not generate plan from gap geometry")

    batteries = estimate_batteries(total_distance_m=result["total_distance_m"])

    plan = MissionPlan(
        target_area_id=cov_run.target_area_id,
        altitude_ft=body.altitude_ft,
        side_overlap_pct=body.side_overlap_pct,
        forward_overlap_pct=body.forward_overlap_pct,
        lane_count=result["lane_count"],
        total_distance_m=result["total_distance_m"],
        batteries_estimated=batteries,
        lanes_geojson=result["lanes_geojson"],
        lane_spacing_ft=None,
        coverage_run_id=cov_run.id,
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


# ---------------------------------------------------------------------------
# KML / GPX downloads
# ---------------------------------------------------------------------------


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