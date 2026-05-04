from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import Footprint, Image

router = APIRouter(prefix="/footprints", tags=["footprints"])


class FootprintOut(BaseModel):
    id: int
    image_id: int
    geom_wkt: str | None
    geom_geojson: str | None
    ground_width_m: float | None
    ground_height_m: float | None
    heading_estimated: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[FootprintOut])
def list_footprints(session_id: int, db: DBSession = Depends(get_db)):
    return (
        db.query(Footprint)
        .join(Image, Image.id == Footprint.image_id)
        .filter(Image.session_id == session_id)
        .all()
    )
