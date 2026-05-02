from __future__ import annotations

import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from ..db.database import get_db
from ..db.models import Image, Session as SessionModel

router = APIRouter(prefix="/export", tags=["export"])
EXPORTS_DIR = Path(__file__).parent.parent / "exports"


@router.post("/webodm")
def export_webodm(session_id: int, db: DBSession = Depends(get_db)):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    images = (
        db.query(Image)
        .filter(Image.session_id == session_id, Image.usable == True)  # noqa: E712
        .all()
    )
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = EXPORTS_DIR / f"webodm_{session_id}.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        csv_rows = "filename,latitude,longitude,altitude\n"
        for img in images:
            csv_rows += (
                f"{img.filename},"
                f"{img.latitude or ''},"
                f"{img.longitude or ''},"
                f"{img.altitude_m or ''}\n"
            )
        zf.writestr("odm_georeferencing.csv", csv_rows)
    return {"zip_path": str(zip_path), "image_count": len(images)}
