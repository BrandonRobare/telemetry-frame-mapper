from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import threading
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_browser_upload_config, get_config
from ..db.database import SessionLocal, get_db
from ..db.models import Session as SessionModel
from ..services.ingest_orchestrator import start_import

router = APIRouter(prefix="/uploads/imports", tags=["uploads"])

_UPLOADS: dict[str, dict[str, Any]] = {}
_UPLOAD_LOCKS: dict[str, threading.Lock] = {}
_UPLOADS_GUARD = threading.Lock()
_MANIFEST_NAME = ".upload.json"
_UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class UploadFilePlan(BaseModel):
    path: str
    size: int = Field(ge=0)


class StartUploadRequest(BaseModel):
    name: str
    total_bytes: int = Field(ge=0)
    files: list[UploadFilePlan]


class StartUploadResponse(BaseModel):
    upload_id: str
    chunk_size: int
    max_file_bytes: int
    max_total_bytes: int
    quota_bytes: int


class UploadProgress(BaseModel):
    upload_id: str
    status: str
    uploaded_bytes: int
    total_bytes: int
    file_count: int
    session_id: int | None = None
    error: str | None = None


class CompleteUploadResponse(UploadProgress):
    session: dict | None = None


def _limits() -> dict:
    cfg = get_browser_upload_config()
    return {
        "chunk_size_bytes": int(cfg["chunk_size_bytes"]),
        "max_file_bytes": int(cfg["max_file_bytes"]),
        "max_total_bytes": int(cfg["max_total_bytes"]),
        "quota_bytes": int(cfg["quota_bytes"]),
        "cleanup_after_hours": int(cfg["cleanup_after_hours"]),
        "accepted_extensions": {
            ext.lower() if str(ext).startswith(".") else f".{str(ext).lower()}"
            for ext in cfg["accepted_extensions"]
        },
    }


def _upload_root() -> Path:
    root = _safe_child_path(Path(get_config().imports_dir), PurePosixPath(".browser_uploads"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _cleanup_old_uploads(root: Path, cleanup_after_hours: int) -> None:
    cutoff = datetime.datetime.now(datetime.timezone.utc).timestamp() - cleanup_after_hours * 3600
    for child in root.iterdir():
        if child.is_dir() and child.stat().st_mtime < cutoff:
            shutil.rmtree(child, ignore_errors=True)


def _safe_upload_path(raw: str) -> PurePosixPath:
    text = raw.strip().replace("\\", "/")
    posix = PurePosixPath(text)
    windows = PureWindowsPath(raw.strip())
    if (
        not text
        or posix.is_absolute()
        or windows.is_absolute()
        or ":" in raw
        or any(part in ("", ".", "..") for part in posix.parts)
    ):
        raise HTTPException(status_code=400, detail=f"Invalid upload path: {raw}")
    return posix


def _validate_plan(req: StartUploadRequest, limits: dict) -> dict[str, UploadFilePlan]:
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Session name is required")
    if not req.files:
        raise HTTPException(status_code=400, detail="At least one file is required")
    if req.total_bytes > limits["max_total_bytes"]:
        raise HTTPException(status_code=413, detail="Upload exceeds total browser import limit")

    seen: set[str] = set()
    planned_total = 0
    by_path: dict[str, UploadFilePlan] = {}
    for item in req.files:
        rel = _safe_upload_path(item.path)
        normalized = rel.as_posix()
        if normalized in seen:
            raise HTTPException(status_code=400, detail=f"Duplicate upload path: {normalized}")
        seen.add(normalized)
        if rel.suffix.lower() not in limits["accepted_extensions"]:
            raise HTTPException(status_code=400, detail=f"Unsupported upload type: {normalized}")
        if item.size > limits["max_file_bytes"]:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds browser import limit: {normalized}",
            )
        planned_total += item.size
        by_path[normalized] = item

    if planned_total != req.total_bytes:
        raise HTTPException(status_code=400, detail="File sizes do not match declared total")
    return by_path


def _safe_child_path(root: Path, rel: PurePosixPath) -> Path:
    root_path = os.path.normpath(os.path.realpath(root))
    candidate = os.path.normpath(os.path.realpath(os.path.join(root_path, *rel.parts)))
    root_cmp = os.path.normcase(root_path)
    candidate_cmp = os.path.normcase(candidate)
    root_prefix = root_cmp if root_cmp.endswith(os.sep) else f"{root_cmp}{os.sep}"
    if candidate_cmp != root_cmp and not candidate_cmp.startswith(root_prefix):
        raise HTTPException(status_code=400, detail="Invalid upload path")
    return Path(candidate)


def _manifest_path(root: Path) -> Path:
    return _safe_child_path(root, PurePosixPath(_MANIFEST_NAME))


def _upload_dir(upload_id: str) -> Path:
    if not _UPLOAD_ID_RE.fullmatch(upload_id):
        raise HTTPException(status_code=404, detail="Upload not found")
    return _safe_child_path(_upload_root(), PurePosixPath(upload_id))


def _safe_upload_dest(root: Path, rel: PurePosixPath) -> Path:
    return _safe_child_path(root, rel)


def _state_for_disk(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": state["id"],
        "name": state["name"],
        "files": state["files"],
        "uploaded_bytes": state["uploaded_bytes"],
        "total_bytes": state["total_bytes"],
        "status": state["status"],
        "session_id": state.get("session_id"),
        "error": state.get("error"),
    }


def _persist_state(state: dict[str, Any]) -> None:
    root = _upload_dir(str(state["id"]))
    root.mkdir(parents=True, exist_ok=True)
    manifest = _manifest_path(root)
    tmp = manifest.with_suffix(f"{manifest.suffix}.tmp")
    tmp.write_text(json.dumps(_state_for_disk(state), sort_keys=True))
    tmp.replace(manifest)


def _load_state_from_manifest(upload_id: str) -> dict[str, Any] | None:
    root = _upload_dir(upload_id)
    manifest = _manifest_path(root)
    if not manifest.exists():
        return None
    try:
        raw = json.loads(manifest.read_text())
    except json.JSONDecodeError:
        return None
    if raw.get("id") != upload_id:
        return None
    raw["root"] = root
    return raw


def _lock_for(upload_id: str) -> threading.Lock:
    with _UPLOADS_GUARD:
        return _UPLOAD_LOCKS.setdefault(upload_id, threading.Lock())


def _remember_state(state: dict[str, Any]) -> dict[str, Any]:
    with _UPLOADS_GUARD:
        _UPLOADS[state["id"]] = state
        _UPLOAD_LOCKS.setdefault(state["id"], threading.Lock())
    return state


def _state(upload_id: str) -> dict[str, Any]:
    state = _UPLOADS.get(upload_id)
    if state is None:
        state = _load_state_from_manifest(upload_id)
        if state is not None:
            _remember_state(state)
    if state is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    if state.get("status") == "cancelled":
        raise HTTPException(status_code=409, detail="Upload was cancelled")
    if state.get("status") == "error":
        raise HTTPException(status_code=409, detail=state.get("error") or "Upload failed")
    return state


def _progress(state: dict[str, Any]) -> UploadProgress:
    return UploadProgress(
        upload_id=state["id"],
        status=state["status"],
        uploaded_bytes=state["uploaded_bytes"],
        total_bytes=state["total_bytes"],
        file_count=len(state["files"]),
        session_id=state.get("session_id"),
        error=state.get("error"),
    )


@router.post("/start", response_model=StartUploadResponse)
def start_browser_import_upload(req: StartUploadRequest):
    limits = _limits()
    root = _upload_root()
    _cleanup_old_uploads(root, limits["cleanup_after_hours"])
    by_path = _validate_plan(req, limits)
    if _dir_size(root) + req.total_bytes > limits["quota_bytes"]:
        raise HTTPException(status_code=507, detail="Browser upload storage quota exceeded")

    upload_id = uuid.uuid4().hex
    dest = root / upload_id
    dest.mkdir(parents=True)
    state = {
        "id": upload_id,
        "name": req.name.strip(),
        "root": dest,
        "files": {path: {"size": plan.size, "received": 0} for path, plan in by_path.items()},
        "uploaded_bytes": 0,
        "total_bytes": req.total_bytes,
        "status": "uploading",
        "session_id": None,
        "error": None,
    }
    _persist_state(state)
    _remember_state(state)
    return StartUploadResponse(
        upload_id=upload_id,
        chunk_size=limits["chunk_size_bytes"],
        max_file_bytes=limits["max_file_bytes"],
        max_total_bytes=limits["max_total_bytes"],
        quota_bytes=limits["quota_bytes"],
    )


@router.post("/{upload_id}/chunk", response_model=UploadProgress)
async def upload_import_chunk(
    upload_id: str,
    path: str = Form(...),
    offset: int = Form(...),
    chunk: UploadFile = File(...),
):
    state = _state(upload_id)
    data = await chunk.read()
    with _lock_for(upload_id):
        if state["status"] != "uploading":
            raise HTTPException(status_code=409, detail="Upload is not accepting chunks")
        rel_path = _safe_upload_path(path)
        rel = rel_path.as_posix()
        planned = state["files"].get(rel)
        if planned is None:
            raise HTTPException(status_code=400, detail="Chunk path was not in upload plan")

        limits = _limits()
        if len(data) > limits["chunk_size_bytes"]:
            raise HTTPException(status_code=413, detail="Chunk exceeds configured size")
        if planned["received"] + len(data) > planned["size"]:
            raise HTTPException(status_code=413, detail="Chunk exceeds planned file size")

        dest = _safe_upload_dest(state["root"], rel_path)
        actual_size = dest.stat().st_size if dest.exists() else 0
        if offset != planned["received"] or offset != actual_size:
            raise HTTPException(status_code=409, detail="Chunk offset does not match server state")

        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("ab") as f:
            f.write(data)

        planned["received"] += len(data)
        state["uploaded_bytes"] += len(data)
        _persist_state(state)
        return _progress(state)


@router.post("/{upload_id}/complete", response_model=CompleteUploadResponse)
def complete_browser_import_upload(upload_id: str, db: DBSession = Depends(get_db)):
    state = _state(upload_id)
    with _lock_for(upload_id):
        incomplete = [p for p, meta in state["files"].items() if meta["received"] != meta["size"]]
        if incomplete:
            raise HTTPException(status_code=409, detail=f"Upload is incomplete: {incomplete[0]}")

        state["status"] = "importing"
        session = SessionModel(
            name=state["name"],
            folder_path=str(state["root"]),
            imported_at=datetime.datetime.now(datetime.timezone.utc),
            photo_count=0,
            usable_count=0,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        state["session_id"] = session.id
        _persist_state(state)
        start_import(session.id, state["root"], SessionLocal)
    return CompleteUploadResponse(
        upload_id=upload_id,
        status=state["status"],
        uploaded_bytes=state["uploaded_bytes"],
        total_bytes=state["total_bytes"],
        file_count=len(state["files"]),
        session_id=session.id,
        session={
            "id": session.id,
            "name": session.name,
            "folder_path": session.folder_path,
            "imported_at": session.imported_at,
            "photo_count": session.photo_count,
            "usable_count": session.usable_count,
        },
    )


@router.post("/{upload_id}/cancel", response_model=UploadProgress)
def cancel_browser_import_upload(upload_id: str):
    state = _UPLOADS.get(upload_id) or _load_state_from_manifest(upload_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    with _lock_for(upload_id):
        state["status"] = "cancelled"
        progress = _progress(state)
        shutil.rmtree(state["root"], ignore_errors=True)
        with _UPLOADS_GUARD:
            _UPLOADS.pop(upload_id, None)
            _UPLOAD_LOCKS.pop(upload_id, None)
        return progress


@router.get("/{upload_id}", response_model=UploadProgress)
def get_browser_import_upload(upload_id: str):
    state = _state(upload_id)
    return _progress(state)
