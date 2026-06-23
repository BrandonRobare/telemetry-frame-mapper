from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from shapely.geometry import mapping
from shapely.wkt import loads as wkt_loads
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import CoverageRun, Footprint, Image, TargetArea
from ..db.models import Session as SessionModel
from ..services.coverage import run_coverage
from ..services.geometry_exports import (
    feature_collection,
    geojson_to_kml,
    geometry_feature,
    kml_to_kmz,
    parse_geojson_geometry,
)

router = APIRouter(prefix="/coverage", tags=["coverage"])


class CoverageRunOut(BaseModel):
    id: int
    target_area_id: int
    session_ids: str | None
    covered_area_m2: float | None
    coverage_pct: float | None
    gap_geojson: str | None
    overlap_geojson: str | None

    model_config = {"from_attributes": True}


@router.post("/run", response_model=CoverageRunOut)
def run_coverage_analysis(
    session_id: int,
    target_area_id: int,
    db: DBSession = Depends(get_db),
):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    target = db.query(TargetArea).filter(TargetArea.id == target_area_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target area not found")

    # Gather footprint GeoJSONs for the session
    footprint_rows = (
        db.query(Footprint)
        .join(Image, Footprint.image_id == Image.id)
        .filter(Image.session_id == session_id)
        .all()
    )

    footprint_geojsons: list[str] = []
    for fp in footprint_rows:
        if fp.geom_geojson:
            footprint_geojsons.append(fp.geom_geojson)
        elif fp.geom_wkt:
            geom = wkt_loads(fp.geom_wkt)
            footprint_geojsons.append(json.dumps(mapping(geom)))

    result = run_coverage(footprint_geojsons, target.geom_geojson)

    # session_ids stores a single session_id as string; multi-session not yet supported
    cov_run = CoverageRun(
        target_area_id=target_area_id,
        session_ids=str(session_id),
        covered_area_m2=result["covered_area_m2"],
        total_area_m2=None,
        coverage_pct=result["coverage_pct"],
        gap_geojson=result["gap_geojson"],
        overlap_geojson=result["overlap_geojson"],
    )
    db.add(cov_run)
    db.commit()
    db.refresh(cov_run)
    return cov_run


@router.get("/results", response_model=CoverageRunOut | None)
def get_coverage_results(session_id: int, db: DBSession = Depends(get_db)):
    # Find the most recent CoverageRun that includes this session_id
    run = (
        db.query(CoverageRun)
        .filter(CoverageRun.session_ids == str(session_id))
        .order_by(CoverageRun.run_at.desc())
        .first()
    )
    if run is None:
        return None
    return {
        "id": run.id,
        "target_area_id": run.target_area_id,
        "session_ids": run.session_ids,
        "covered_area_m2": run.covered_area_m2,
        "coverage_pct": run.coverage_pct,
        "gap_geojson": run.gap_geojson,
        "overlap_geojson": run.overlap_geojson,
    }


@router.get("/results/export")
def export_latest_coverage_results(
    session_id: int,
    format: str = Query("geojson", pattern="^(geojson|kml|kmz)$"),
    db: DBSession = Depends(get_db),
):
    run = (
        db.query(CoverageRun)
        .filter(CoverageRun.session_ids == str(session_id))
        .order_by(CoverageRun.run_at.desc())
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Coverage run not found")
    return _coverage_export_response(run, format)


@router.get("/{run_id}/export")
def export_coverage_run(
    run_id: int,
    format: str = Query("geojson", pattern="^(geojson|kml|kmz)$"),
    db: DBSession = Depends(get_db),
):
    run = db.query(CoverageRun).filter(CoverageRun.id == run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Coverage run not found")
    return _coverage_export_response(run, format)


def _coverage_export_response(run: CoverageRun, format: str):
    features = []
    for name, raw_geojson in (
        ("coverage_gap", run.gap_geojson),
        ("coverage_overlap", run.overlap_geojson),
    ):
        feature = geometry_feature(
            parse_geojson_geometry(raw_geojson),
            name=name,
            properties={
                "coverage_run_id": run.id,
                "target_area_id": run.target_area_id,
                "session_ids": run.session_ids,
                "covered_area_m2": run.covered_area_m2,
                "coverage_pct": run.coverage_pct,
                "kind": name,
            },
        )
        if feature:
            features.append(feature)

    if not features:
        raise HTTPException(status_code=404, detail="No coverage geometry found for run")

    collection = feature_collection(features)
    filename = f"coverage_run_{run.id}"
    if format == "geojson":
        return JSONResponse(
            collection,
            media_type="application/geo+json",
            headers={"Content-Disposition": f'attachment; filename="{filename}.geojson"'},
        )

    kml = geojson_to_kml(collection, f"Coverage run {run.id}")
    if format == "kml":
        return Response(
            kml,
            media_type="application/vnd.google-earth.kml+xml",
            headers={"Content-Disposition": f'attachment; filename="{filename}.kml"'},
        )
    return Response(
        kml_to_kmz(kml, f"{filename}.kml"),
        media_type="application/vnd.google-earth.kmz",
        headers={"Content-Disposition": f'attachment; filename="{filename}.kmz"'},
    )
