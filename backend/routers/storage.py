from __future__ import annotations

import time
from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..core.config import get_config
from ..services.storage_summary_cache import _cache, invalidate_storage_summary_cache

router = APIRouter(prefix="/storage", tags=["storage"])
_CACHE_TTL = 30.0


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _data_db_size(path: Path) -> int:
    """Measure only DB and config files in the data directory."""
    if not path.exists():
        return 0
    return sum(
        f.stat().st_size
        for f in path.rglob("*")
        if f.is_file() and f.suffix.lower() in {".db", ".yaml", ".yml", ".json"}
    )


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
        if name == "data":
            by_type[name] = _data_db_size(d)
        else:
            by_type[name] = _dir_size(d)

    total = sum(by_type.values())
    # Per-session breakdown: walk sessions under processed_dir and sum sizes.
    # Uses the same cache TTL as the top-level summary; cache is invalidated
    # on delete / import completion.
    try:
        processed = Path(get_config().processed_dir)
        by_session = []
        if processed.exists():
            for session_dir in sorted(processed.iterdir()):
                if session_dir.is_dir():
                    size = sum(
                        f.stat().st_size
                        for f in session_dir.rglob("*")
                        if f.is_file()
                    )
                    by_session.append({
                        "session_id": session_dir.name,
                        "bytes": size,
                    })
    except Exception:
        by_session = []
    return {"total_bytes": total, "by_type": by_type, "by_session": by_session}


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
        invalidate_storage_summary_cache()
        return {"deleted": str(resolved)}

    raise HTTPException(status_code=404, detail="File not found")


@router.get("/summary")
def get_storage_summary():
    now = time.monotonic()
    if _cache["data"] is None or now - _cache["ts"] > _CACHE_TTL:
        _cache["data"] = _compute_summary()
        _cache["ts"] = now
    return _cache["data"]


class PolicyRuleInput(BaseModel):
    target: str  # "raw_frames" | "colmap_intermediates" | "reconstruction_artifacts"
    age_days: int | None = None
    disk_pct: float | None = None


class ApplyPolicyRequest(BaseModel):
    rules: list[PolicyRuleInput]
    execute: bool = False


@router.post("/apply-policy")
def apply_storage_policy(body: ApplyPolicyRequest):
    """Preview or execute storage lifecycle rules.

    **Dry-run** (default, ``execute=false``): returns a side-effect-free
    listing of every candidate file/directory with ``path``, ``bytes``,
    ``reason``, and ``action``.

    **Execute** (``execute=true``): performs the actions. Only paths inside
    the configured storage roots (imports_dir, processed_dir, exports_dir,
    data_dir) are ever touched. Prefers delete for COLMAP intermediates,
    archive for raw frames and reconstruction artifacts when age-based.
    """
    from ..db.database import SessionLocal
    from ..services.storage_lifecycle import apply_policy

    rules = [r.model_dump() for r in body.rules]
    db = SessionLocal() if body.execute else None
    try:
        result = apply_policy(rules, execute=body.execute, db=db)
    finally:
        if db is not None:
            db.close()
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result
