from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/auto-import", tags=["auto-import"])


@router.get("/status")
def get_auto_import_status(request: Request) -> dict:
    """Report only configured-root watcher state; it never scans arbitrary paths."""
    watcher = getattr(request.app.state, "auto_import_watcher", None)
    if watcher is not None:
        return watcher.status()
    return {"enabled": False, "running": False, "roots": []}
