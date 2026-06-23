from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import Footprint, Image
from ..services.geometry_exports import (
    feature_collection,
    geojson_to_kml,
    geometry_feature,
    kml_to_kmz,
    parse_geojson_geometry,
)

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


@router.get("/export")
def export_footprints(
    session_id: int,
    format: str = Query("geojson", pattern="^(geojson|kml|kmz)$"),
    db: DBSession = Depends(get_db),
):
    rows = (
        db.query(Footprint, Image)
        .join(Image, Image.id == Footprint.image_id)
        .filter(Image.session_id == session_id)
        .order_by(Image.id)
        .all()
    )
    features = []
    for footprint, image in rows:
        feature = geometry_feature(
            parse_geojson_geometry(footprint.geom_geojson),
            name=image.filename,
            properties={
                "footprint_id": footprint.id,
                "image_id": image.id,
                "filename": image.filename,
                "ground_width_m": footprint.ground_width_m,
                "ground_height_m": footprint.ground_height_m,
                "heading_estimated": footprint.heading_estimated,
            },
        )
        if feature:
            features.append(feature)

    if not features:
        raise HTTPException(status_code=404, detail="No footprint geometry found for session")

    collection = feature_collection(features)
    filename = f"session_{session_id}_footprints"
    if format == "geojson":
        return JSONResponse(
            collection,
            media_type="application/geo+json",
            headers={"Content-Disposition": f'attachment; filename="{filename}.geojson"'},
        )

    kml = geojson_to_kml(collection, f"Session {session_id} footprints")
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
