from __future__ import annotations

import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config
from ..db.database import get_db
from ..db.models import Image
from ..db.models import Session as SessionModel

router = APIRouter(prefix="/export", tags=["export"])


@router.post("/webodm-georeferencing-csv")
def export_webodm_georeferencing_csv(session_id: int, db: DBSession = Depends(get_db)):
    """Build a WebODM/OpenDroneMap georeferencing CSV-only zip.

    The archive intentionally contains only ``odm_georeferencing.csv`` for
    workflows that need the ODM georeferencing sidecar, not a full image bundle.
    """
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    images = (
        db.query(Image)
        .filter(Image.session_id == session_id, Image.usable == True)  # noqa: E712
        .all()
    )
    exports_dir = Path(get_config().exports_dir)
    exports_dir.mkdir(parents=True, exist_ok=True)
    zip_path = exports_dir / f"webodm_georeferencing_csv_{session_id}.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        csv_rows = "filename,latitude,longitude,altitude\n"
        for img in images:
            # Use explicit None checks — 0.0 is a valid coordinate value
            lat = "" if img.latitude is None else img.latitude
            lon = "" if img.longitude is None else img.longitude
            alt = "" if img.altitude_m is None else img.altitude_m
            csv_rows += f"{img.filename},{lat},{lon},{alt}\n"
        zf.writestr("odm_georeferencing.csv", csv_rows)
    return {
        "zip_path": str(zip_path),
        "image_count": len(images),
        "contents": ["odm_georeferencing.csv"],
        "export_type": "webodm_georeferencing_csv_only",
    }


@router.post("/reconstructions/{reconstruction_id}/share-bundle")
def export_reconstruction_share_bundle(reconstruction_id: int, db: DBSession = Depends(get_db)):
    """Create a static share bundle for a completed reconstruction."""
    from ..db.models import Reconstruction
    from ..services.share_bundle import build_share_bundle

    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    return build_share_bundle(
        Path(get_config().exports_dir) / f"reconstruction_{reconstruction_id}_share.zip", rec
    )
