from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import Image
from ..db.models import Session as SessionModel
from ..services.georeferencing_workflows import (
    GcpPoint,
    detect_precision_workflow,
    render_gcp_list,
)

router = APIRouter(prefix="/georeferencing", tags=["georeferencing"])


class GcpPointIn(BaseModel):
    image_filename: str
    pixel_x: float = Field(ge=0)
    pixel_y: float = Field(ge=0)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    altitude_m: float | None = None
    label: str | None = None


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
