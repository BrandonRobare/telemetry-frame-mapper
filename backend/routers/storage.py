from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter

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


@router.get("/summary")
def get_storage_summary():
    now = time.monotonic()
    if _cache["data"] is None or now - _cache["ts"] > _CACHE_TTL:
        _cache["data"] = _compute_summary()
        _cache["ts"] = now
    return _cache["data"]
