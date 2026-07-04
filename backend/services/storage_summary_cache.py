from __future__ import annotations

_cache: dict = {"data": None, "ts": 0.0}


def invalidate_storage_summary_cache() -> None:
    _cache["data"] = None
    _cache["ts"] = 0.0
