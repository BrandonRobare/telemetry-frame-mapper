from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from ..core.config import get_config

router = APIRouter(prefix="/storage", tags=["storage"])

_cache: dict = {"data": None, "ts": 0.0}
_CACHE_TTL = 30.0


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _compute_summary() -> dict:
    cfg = get_config()
    dirs = {
        "imports": Path(cfg.imports_dir),
        "processed": Path(cfg.processed_dir),
        "exports": Path(cfg.exports_dir),
        "data": Path(cfg.data_dir),
    }
    by_type: dict[str, int] = {}
    for name, d in dirs.items():
        by_type[name] = _dir_size(d)

    total = sum(by_type.values())
    return {"total_bytes": total, "by_type": by_type, "by_session": []}


VALID_DIRECTORIES = {"imports", "processed", "exports", "data"}


@router.get("/files")
def list_files(directory: str = Query("imports")):
    if directory not in VALID_DIRECTORIES:
        raise HTTPException(
            status_code=422,
            detail=f"directory must be one of {sorted(VALID_DIRECTORIES)}",
        )
    cfg = get_config()
    dir_map = {
        "imports": cfg.imports_dir,
        "processed": cfg.processed_dir,
        "exports": cfg.exports_dir,
        "data": cfg.data_dir,
    }
    base = Path(dir_map[directory])
    if not base.exists():
        return {"directory": directory, "files": []}
    files = []
    for f in sorted(base.iterdir()):
        if f.is_file():
            stat = f.stat()
            files.append({
                "name": f.name,
                "path": str(f),
                "size_bytes": stat.st_size,
                "modified": stat.st_mtime,
            })
    return {"directory": directory, "files": files}


@router.delete("/file")
def delete_file(
    directory: str = Query(...),
    filename: str = Query(...),
):
    if directory not in VALID_DIRECTORIES:
        raise HTTPException(
            status_code=422,
            detail=f"directory must be one of {sorted(VALID_DIRECTORIES)}",
        )
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    cfg = get_config()
    dir_map = {
        "imports": cfg.imports_dir,
        "processed": cfg.processed_dir,
        "exports": cfg.exports_dir,
        "data": cfg.data_dir,
    }
    p = Path(dir_map[directory]) / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if not p.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")
    p.unlink()
    return {"deleted": str(p)}


@router.get("/summary")
def get_storage_summary():
    now = time.monotonic()
    if _cache["data"] is None or now - _cache["ts"] > _CACHE_TTL:
        _cache["data"] = _compute_summary()
        _cache["ts"] = now
    return _cache["data"]
