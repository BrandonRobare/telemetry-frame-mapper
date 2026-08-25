from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import Image, Reconstruction
from ..db.models import Session as SessionModel
from ..services.georeferencing_workflows import (
    ControlPoint,
    GcpPoint,
    detect_precision_workflow,
    parse_control_point_csv,
    render_control_point_csv,
    render_gcp_list,
)
from ..services.quality_report import (
    compute_gcp_accuracy,
    parse_surveyed_points_3d,
)

router = APIRouter(prefix="/georeferencing", tags=["georeferencing"])
logger = logging.getLogger(__name__)


class GcpPointIn(BaseModel):
    image_filename: str
    pixel_x: float = Field(ge=0)
    pixel_y: float = Field(ge=0)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    altitude_m: float | None = None
    label: str | None = None

    @field_validator("image_filename", "label")
    @classmethod
    def reject_whitespace(cls, v: str | None) -> str | None:
        # gcp_list.txt rows are whitespace-delimited, so a space here would
        # shift every following column (#629).
        if v is not None and v.split() != [v]:
            raise ValueError("must be non-empty and contain no whitespace")
        return v


class ControlPointIn(BaseModel):
    label: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude_m: float


class ControlPointCsvIn(BaseModel):
    format: str
    contents: str


class ControlPointExportIn(BaseModel):
    format: str
    points: list[ControlPointIn]


# ---- Accuracy report models ----


class SurveyedGcpIn(BaseModel):
    """A paired surveyed/reconstructed GCP in local reconstruction coordinates."""

    label: str | None = None
    x: float
    y: float
    z: float
    reconstructed_x: float
    reconstructed_y: float
    reconstructed_z: float


class GcpAccuracyRequest(BaseModel):
    points: list[SurveyedGcpIn]

    @field_validator("points")
    @classmethod
    def at_least_one(cls, v: list[SurveyedGcpIn]) -> list[SurveyedGcpIn]:
        if len(v) == 0:
            raise ValueError("At least one GCP is required")
        return v


# ---- Existing endpoints ----


@router.get("/sessions/{session_id}/precision")
def get_precision_workflow(session_id: int, db: DBSession = Depends(get_db)):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    images = db.query(Image).filter(Image.session_id == session_id).all()
    return detect_precision_workflow(images)


@router.post("/gcp-list")
def build_gcp_list(points: list[GcpPointIn]):
    gcp_points = [GcpPoint(**point.model_dump()) for point in points]
    return {
        "format": "webodm_gcp_list",
        "point_count": len(points),
        "contents": render_gcp_list(gcp_points),
    }


@router.post("/control-points/import")
def import_control_points(body: ControlPointCsvIn):
    """Parse the documented no-header Pix4D or DroneDeploy WGS84 CSV format."""
    try:
        points = parse_control_point_csv(body.contents, body.format)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "format": body.format,
        "point_count": len(points),
        "points": [point.__dict__ for point in points],
    }


@router.post("/control-points/export")
def export_control_points(body: ControlPointExportIn):
    """Render a no-header Pix4D or DroneDeploy WGS84 control-point CSV."""
    points = [ControlPoint(**point.model_dump()) for point in body.points]
    try:
        contents = render_control_point_csv(points, body.format)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"format": body.format, "point_count": len(points), "contents": contents}


# ---- GCP accuracy report (issue #287) ----


@router.post("/sessions/{session_id}/accuracy-report")
def gcp_accuracy_report(
    session_id: int,
    body: GcpAccuracyRequest,
    db: DBSession = Depends(get_db),
):
    """Compute RMSE of surveyed GCPs against the latest completed reconstruction.

    Survey points must be provided in the reconstruction's local coordinate
    system (UTM-aligned).  The geo-transform from the latest completed
    reconstruction is used for metadata.
    """
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    rec = (
        db.query(Reconstruction)
        .filter(Reconstruction.session_id == session_id, Reconstruction.status == "complete")
        .order_by(Reconstruction.completed_at.desc())
        .first()
    )
    if not rec:
        raise HTTPException(
            status_code=404,
            detail="No completed reconstruction found for this session",
        )

    if not rec.geo_transform:
        raise HTTPException(
            status_code=400,
            detail=(
                "Reconstruction has no geo-transform; "
                "accuracy report requires a georeferenced reconstruction"
            ),
        )

    try:
        geo_transform = json.loads(rec.geo_transform)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail="Stored geo-transform is malformed",
        ) from exc

    survey_points = parse_surveyed_points_3d([p.model_dump() for p in body.points])

    return compute_gcp_accuracy(geo_transform, survey_points)
