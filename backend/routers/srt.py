from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from src.drone_video_geotagger.telemetry import parse_srt
from ..core.config import get_config

router = APIRouter(prefix="/srt", tags=["srt"])


@router.post("/process")
async def process_srt(file: UploadFile = File(...)):
    # Get upload size limit from settings (default 10MB)
    config = get_config()
    max_size_mb = config.flight_log_max_upload_size_mb  # Reuse the same setting as flight logs
    max_size_bytes = max_size_mb * 1024 * 1024
    
    # Check file size before reading
    if file.size is not None and file.size > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"SRT file too large. Maximum allowed size is {max_size_mb} MB"
        )
    
    content = await file.read()
    
    # If file size was not provided, check again after reading
    if file.size is None and len(content) > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"SRT file too large. Maximum allowed size is {max_size_mb} MB"
        )
    
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        try:
            points = parse_srt(Path(tmp_path))
        except ValueError as exc:
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
