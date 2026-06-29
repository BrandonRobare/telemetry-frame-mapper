from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.core.config import get_upload_limits_config
from src.drone_video_geotagger.telemetry import parse_srt

router = APIRouter(prefix="/srt", tags=["srt"])

_SRT_CHUNK_SIZE = 1024 * 1024


async def _read_upload_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = await file.read(_SRT_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"SRT upload exceeds {max_bytes} byte limit",
            )
        chunks.append(chunk)

    return b"".join(chunks)


@router.post("/process")
async def process_srt(file: UploadFile = File(...)):
    limits = get_upload_limits_config()
    content = await _read_upload_with_limit(file, limits["srt_max_bytes"])
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
