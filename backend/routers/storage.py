from __future__ import annotations

import time
from pathlib import Path, PurePosixPath, PureWindowsPath

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


def _invalid_directory_error() -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=f"directory must be one of {sorted(VALID_DIRECTORIES)}",
    )


def _storage_base(directory: str) -> Path:
    if directory not in VALID_DIRECTORIES:
        raise _invalid_directory_error()

    cfg = get_config()
    if directory == "imports":
        return Path(cfg.imports_dir).resolve()
    if directory == "processed":
        return Path(cfg.processed_dir).resolve()
    if directory == "exports":
        return Path(cfg.exports_dir).resolve()
    if directory == "data":
        return Path(cfg.data_dir).resolve()
    raise _invalid_directory_error()


def _validate_filename(filename: str) -> None:
    posix_path = PurePosixPath(filename)
    windows_path = PureWindowsPath(filename)
    if (
        not filename
        or ":" in filename
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or posix_path.name != filename
        or windows_path.name != filename
        or any(part in ("", ".", "..") for part in posix_path.parts)
        or any(part in ("", ".", "..") for part in windows_path.parts)
    ):
        raise HTTPException(status_code=400, detail="Invalid filename")


@router.get("/files")
def list_files(directory: str = Query("imports")):
    base = _storage_base(directory)
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
    _validate_filename(filename)
    base = _storage_base(directory)
    if not base.exists():
        raise HTTPException(status_code=404, detail="File not found")

    base_resolved = base.resolve()
    for candidate in base.iterdir():
        if candidate.name != filename:
            continue

        resolved = candidate.resolve()
        if not resolved.is_relative_to(base_resolved):
            raise HTTPException(
                status_code=403,
                detail="File must be inside storage directory",
            )
        if not resolved.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")
        resolved.unlink()
        return {"deleted": str(resolved)}

    raise HTTPException(status_code=404, detail="File not found")


@router.get("/summary")
def get_storage_summary():
    now = time.monotonic()
    if _cache["data"] is None or now - _cache["ts"] > _CACHE_TTL:
        _cache["data"] = _compute_summary()
        _cache["ts"] = now
    return _cache["data"]
