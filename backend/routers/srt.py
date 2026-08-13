from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.core.config import get_upload_limits_config
from backend.services.upload_reader import read_upload_with_limit
from src.drone_video_geotagger.gps_quality import assess_gps_lock, samples_from_telemetry
from src.drone_video_geotagger.telemetry import parse_srt

router = APIRouter(prefix="/srt", tags=["srt"])

@router.post("/process")
async def process_srt(file: UploadFile = File(...)):
    limits = get_upload_limits_config()
    max_bytes = limits["srt_max_bytes"]
    content = await read_upload_with_limit(
        file,
        max_bytes,
        too_large_detail=f"SRT upload exceeds {max_bytes} byte limit",
    )
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        try:
            points = parse_srt(Path(tmp_path))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        gps_lock = assess_gps_lock(samples_from_telemetry(points))
        return {
            "points": [
                {
                    "start_s": p.start_s,
                    "end_s": p.end_s,
                    "lat": p.lat,
                    "lon": p.lon,
                    "alt_m": p.rel_alt_m,
                }
                for p in points
            ],
            "gps_lock_warnings": list(gps_lock.warnings),
        }
    finally:
        os.unlink(tmp_path)
