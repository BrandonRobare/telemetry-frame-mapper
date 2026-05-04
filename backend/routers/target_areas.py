from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import TargetArea

router = APIRouter(prefix="/target-areas", tags=["target-areas"])


class TargetAreaIn(BaseModel):
    name: str
    geom_geojson: str


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
