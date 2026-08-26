from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from shapely.errors import ShapelyError
from shapely.geometry import shape
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import TargetArea

router = APIRouter(prefix="/target-areas", tags=["target-areas"])

_VALID_GEOM_TYPES = {"Polygon", "MultiPolygon"}


class TargetAreaIn(BaseModel):
    name: str
    geom_geojson: str

    @field_validator("geom_geojson")
    @classmethod
    def validate_geom_geojson(cls, v: str) -> str:
        # Every downstream consumer (coverage, mission planning, reconstruction
        # filtering) does `shape(json.loads(v))` with no error handling, so this
        # is the one place to catch a bad geometry before it reaches the DB (#638).
        try:
            geom = shape(json.loads(v))
        except (
            json.JSONDecodeError,
            ShapelyError,
            TypeError,
            ValueError,
            AttributeError,
            KeyError,
        ) as e:
            raise ValueError(f"geom_geojson must be valid GeoJSON geometry: {e}") from e
        if geom.geom_type not in _VALID_GEOM_TYPES:
            raise ValueError(
                f"geom_geojson must be a Polygon or MultiPolygon, got {geom.geom_type}"
            )
        if geom.is_empty:
            raise ValueError("geom_geojson must not be an empty geometry")
        return v


class TargetAreaOut(BaseModel):
    id: int
    name: str
    geom_geojson: str | None

    model_config = {"from_attributes": True}


class DeleteOut(BaseModel):
    ok: bool


@router.post("/", response_model=TargetAreaOut)
def create_target_area(body: TargetAreaIn, db: DBSession = Depends(get_db)):
    area = TargetArea(name=body.name, geom_geojson=body.geom_geojson)
    db.add(area)
    db.commit()
    db.refresh(area)
    return area


@router.get("/", response_model=list[TargetAreaOut])
def list_target_areas(db: DBSession = Depends(get_db)):
    return db.query(TargetArea).all()


@router.delete("/{area_id}", response_model=DeleteOut)
def delete_target_area(area_id: int, db: DBSession = Depends(get_db)):
    area = db.query(TargetArea).filter(TargetArea.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Target area not found")
    db.delete(area)
    db.commit()
    return {"ok": True}
