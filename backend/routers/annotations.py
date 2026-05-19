from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import Annotation, Reconstruction

router = APIRouter(prefix="/reconstruction", tags=["annotations"])


class AnnotationIn(BaseModel):
    label: str
    lat: float
    lon: float
    alt_m: float
    color: str = "#ff6b35"


class AnnotationOut(BaseModel):
    id: int
    reconstruction_id: int
    label: str
    lat: float
    lon: float
    alt_m: float
    color: str
    created_at: datetime

    model_config = {"from_attributes": True}


def _get_reconstruction_or_404(reconstruction_id: int, db: DBSession) -> Reconstruction:
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if rec is None:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    return rec


@router.post(
    "/{reconstruction_id}/annotations",
    response_model=AnnotationOut,
    status_code=201,
)
def create_annotation(
    reconstruction_id: int,
    body: AnnotationIn,
    db: DBSession = Depends(get_db),
):
    _get_reconstruction_or_404(reconstruction_id, db)
    annotation = Annotation(
        reconstruction_id=reconstruction_id,
        label=body.label,
        lat=body.lat,
        lon=body.lon,
        alt_m=body.alt_m,
        color=body.color,
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    return annotation


@router.get(
    "/{reconstruction_id}/annotations",
    response_model=list[AnnotationOut],
)
def list_annotations(reconstruction_id: int, db: DBSession = Depends(get_db)):
    _get_reconstruction_or_404(reconstruction_id, db)
    return (
        db.query(Annotation)
        .filter(Annotation.reconstruction_id == reconstruction_id)
        .order_by(Annotation.created_at)
        .all()
    )


@router.delete("/{reconstruction_id}/annotations/{annotation_id}")
def delete_annotation(
    reconstruction_id: int,
    annotation_id: int,
    db: DBSession = Depends(get_db),
):
    annotation = (
        db.query(Annotation)
        .filter(
            Annotation.id == annotation_id,
            Annotation.reconstruction_id == reconstruction_id,
        )
        .first()
    )
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    db.delete(annotation)
    db.commit()
    return {"ok": True}


@router.get("/{reconstruction_id}/annotations.geojson")
def export_annotations_geojson(
    reconstruction_id: int,
    db: DBSession = Depends(get_db),
):
    _get_reconstruction_or_404(reconstruction_id, db)
    annotations = (
        db.query(Annotation)
        .filter(Annotation.reconstruction_id == reconstruction_id)
        .order_by(Annotation.created_at)
        .all()
    )
    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [a.lon, a.lat, a.alt_m],
            },
            "properties": {
                "id": a.id,
                "label": a.label,
                "color": a.color,
                "created_at": a.created_at.isoformat(),
            },
        }
        for a in annotations
    ]
    return JSONResponse({"type": "FeatureCollection", "features": features})
