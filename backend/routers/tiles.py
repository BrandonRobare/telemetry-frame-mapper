from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config
from ..core.paths import confine_path
from ..db.database import get_db
from ..db.models import Reconstruction

router = APIRouter(prefix="/tiles", tags=["tiles"])
_MAX_IMAGE_SIZE = 4096
_WEB_MERCATOR_LIMIT = 20037508.342789244


def _orthomosaic_path(rec: Reconstruction) -> Path:
    if rec.ortho_status != "complete":
        raise HTTPException(status_code=409, detail="Orthomosaic export is not complete")
    if not rec.ortho_path:
        raise HTTPException(status_code=404, detail="Orthomosaic file path not recorded")
    try:
        path = confine_path(Path(rec.ortho_path), Path(get_config().exports_dir))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid orthomosaic export path") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Orthomosaic file not found on disk")
    return path


def _png(path: Path, bounds: tuple[float, float, float, float], width: int, height: int) -> bytes:
    try:
        import numpy as np
        import rasterio
        from PIL import Image
        from rasterio.enums import Resampling
        from rasterio.transform import from_bounds
        from rasterio.vrt import WarpedVRT
    except ImportError as exc:
        raise HTTPException(
            status_code=501, detail="Raster tile support requires rasterio and Pillow"
        ) from exc

    if width < 1 or height < 1 or width > _MAX_IMAGE_SIZE or height > _MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="WIDTH and HEIGHT must be between 1 and 4096")
    west, south, east, north = bounds
    if not west < east or not south < north:
        raise HTTPException(
            status_code=400, detail="BBOX must be west,south,east,north with non-zero area"
        )
    with rasterio.open(path) as source:
        if source.crs is None:
            raise HTTPException(status_code=422, detail="Orthomosaic has no CRS")
        with WarpedVRT(
            source,
            crs="EPSG:3857",
            transform=from_bounds(west, south, east, north, width, height),
            width=width,
            height=height,
            resampling=Resampling.bilinear,
            add_alpha=True,
        ) as raster:
            data = raster.read(out_dtype="uint8")
    if data.shape[0] == 1:
        data = np.repeat(data, 3, axis=0)
    if data.shape[0] == 2:
        data = np.concatenate((np.repeat(data[:1], 3, axis=0), data[1:2]), axis=0)
    if data.shape[0] == 3:
        data = np.concatenate((data, np.full((1, height, width), 255, dtype=np.uint8)), axis=0)
    output = BytesIO()
    Image.fromarray(np.moveaxis(data[:4], 0, -1), "RGBA").save(output, format="PNG")
    return output.getvalue()


def _slippy_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    if not 0 <= z <= 22:
        raise HTTPException(status_code=400, detail="Tile zoom z must be between 0 and 22")
    limit = 1 << z
    if not 0 <= x < limit or not 0 <= y < limit:
        raise HTTPException(status_code=400, detail="Tile x and y must be within the zoom range")
    size = 2 * _WEB_MERCATOR_LIMIT / limit
    west, north = -_WEB_MERCATOR_LIMIT + x * size, _WEB_MERCATOR_LIMIT - y * size
    return west, north - size, west + size, north


def _reconstruction(reconstruction_id: int, db: DBSession) -> Reconstruction:
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    return rec


@router.get(
    "/{reconstruction_id}/wmts/{z}/{x}/{y}.png", responses={200: {"content": {"image/png": {}}}}
)
def wmts_tile(reconstruction_id: int, z: int, x: int, y: int, db: DBSession = Depends(get_db)):
    """Serve one Web Mercator XYZ tile from the completed orthomosaic."""
    return Response(
        content=_png(
            _orthomosaic_path(_reconstruction(reconstruction_id, db)),
            _slippy_bounds(z, x, y),
            256,
            256,
        ),
        media_type="image/png",
    )


@router.get("/{reconstruction_id}/wms")
def wms(
    reconstruction_id: int,
    request: str = Query("GetCapabilities", alias="REQUEST"),
    service: str = Query("WMS", alias="SERVICE"),
    layers: str | None = Query(None, alias="LAYERS"),
    crs: str | None = Query(None, alias="CRS"),
    srs: str | None = Query(None, alias="SRS"),
    bbox: str | None = Query(None, alias="BBOX"),
    width: int | None = Query(None, alias="WIDTH"),
    height: int | None = Query(None, alias="HEIGHT"),
    format: str = Query("image/png", alias="FORMAT"),
    db: DBSession = Depends(get_db),
):
    """Minimal WMS 1.3.0 discovery and GetMap interface for one orthomosaic."""
    path = _orthomosaic_path(_reconstruction(reconstruction_id, db))
    if service.upper() != "WMS":
        raise HTTPException(status_code=400, detail="SERVICE must be WMS")
    operation, layer = request.upper(), f"reconstruction-{reconstruction_id}"
    if operation == "GETCAPABILITIES":
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<WMS_Capabilities version="1.3.0"><Service><Name>WMS</Name>'
            "<Title>Drone Mapping orthomosaic</Title></Service><Capability><Request>"
            "<GetCapabilities/><GetMap><Format>image/png</Format></GetMap></Request><Layer>"
            f"<Name>{layer}</Name><Title>Reconstruction {reconstruction_id} orthomosaic</Title>"
            "<CRS>EPSG:3857</CRS>"
            '<ResourceURL format="image/png" resourceType="tile" '
            f'template="/tiles/{reconstruction_id}/wmts/{{z}}/{{x}}/{{y}}.png"/>'
            "</Layer></Capability></WMS_Capabilities>"
        )
        return Response(content=xml, media_type="application/xml")
    if operation != "GETMAP":
        raise HTTPException(status_code=400, detail="REQUEST must be GetCapabilities or GetMap")
    if layers != layer:
        raise HTTPException(status_code=400, detail=f"LAYERS must be {layer}")
    if (crs or srs or "").upper() != "EPSG:3857":
        raise HTTPException(status_code=400, detail="CRS or SRS must be EPSG:3857")
    if format.lower() != "image/png":
        raise HTTPException(status_code=400, detail="FORMAT must be image/png")
    if not bbox or width is None or height is None:
        raise HTTPException(status_code=400, detail="GetMap requires BBOX, WIDTH, and HEIGHT")
    try:
        bounds = tuple(float(value) for value in bbox.split(","))
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="BBOX must contain four numeric values"
        ) from exc
    if len(bounds) != 4:
        raise HTTPException(status_code=400, detail="BBOX must contain four numeric values")
    return Response(content=_png(path, bounds, width, height), media_type="image/png")
