from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import Measurement, Reconstruction

router = APIRouter(prefix="/reconstruction", tags=["measurements"])

MeasurementKind = Literal["distance", "area", "point"]


class MeasurementPoint(BaseModel):
    x: float
    y: float
    z: float
    lat: float | None = None
    lon: float | None = None
    alt: float | None = None


class MeasurementIn(BaseModel):
    kind: MeasurementKind
    points: list[MeasurementPoint] = Field(min_length=1)
    value: float | None = None
    unit: str | None = None
    label: str | None = None


class MeasurementOut(BaseModel):
    id: int
    reconstruction_id: int
    kind: str
    points: list[MeasurementPoint]
    value: float | None
    unit: str | None
    label: str | None
    created_at: datetime


def _get_reconstruction_or_404(reconstruction_id: int, db: DBSession) -> Reconstruction:
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if rec is None:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    return rec


def _serialize_measurement(m: Measurement) -> MeasurementOut:
    return MeasurementOut(
        id=m.id,
        reconstruction_id=m.reconstruction_id,
        kind=m.kind,
        points=[MeasurementPoint(**p) for p in json.loads(m.points_json)],
        value=m.value,
        unit=m.unit,
        label=m.label,
        created_at=m.created_at,
    )


@router.post(
    "/{reconstruction_id}/measurements",
    response_model=MeasurementOut,
    status_code=201,
)
def create_measurement(
    reconstruction_id: int,
    body: MeasurementIn,
    db: DBSession = Depends(get_db),
):
    _get_reconstruction_or_404(reconstruction_id, db)
    measurement = Measurement(
        reconstruction_id=reconstruction_id,
        kind=body.kind,
        points_json=json.dumps([p.model_dump() for p in body.points]),
        value=body.value,
        unit=body.unit,
        label=body.label,
    )
    db.add(measurement)
    db.commit()
    db.refresh(measurement)
    return _serialize_measurement(measurement)


@router.get(
    "/{reconstruction_id}/measurements",
    response_model=list[MeasurementOut],
)
def list_measurements(reconstruction_id: int, db: DBSession = Depends(get_db)):
    _get_reconstruction_or_404(reconstruction_id, db)
    measurements = (
        db.query(Measurement)
        .filter(Measurement.reconstruction_id == reconstruction_id)
        .order_by(Measurement.created_at)
        .all()
    )
    return [_serialize_measurement(m) for m in measurements]


@router.delete("/{reconstruction_id}/measurements/{measurement_id}")
def delete_measurement(
    reconstruction_id: int,
    measurement_id: int,
    db: DBSession = Depends(get_db),
):
    measurement = (
        db.query(Measurement)
        .filter(
            Measurement.id == measurement_id,
            Measurement.reconstruction_id == reconstruction_id,
        )
        .first()
    )
    if measurement is None:
        raise HTTPException(status_code=404, detail="Measurement not found")
    db.delete(measurement)
    db.commit()
    return {"ok": True}
