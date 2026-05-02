from __future__ import annotations
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

from src.drone_video_geotagger.telemetry import parse_srt

router = APIRouter(prefix="/srt", tags=["srt"])


@router.post("/process")
async def process_srt(file: UploadFile = File(...)):
    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        try:
            points = parse_srt(Path(tmp_path))
        except (ValueError, Exception) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return [
            {
                "start_s": p.start_s,
                "end_s": p.end_s,
                "lat": p.lat,
                "lon": p.lon,
                "alt_m": p.rel_alt_m,
            }
            for p in points
        ]
    finally:
        os.unlink(tmp_path)
