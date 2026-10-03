from __future__ import annotations

import datetime
import json
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
from ..core.paths import confine_path
from ..db.database import SessionLocal, get_db
from ..db.models import Session as SessionModel
from ..services.duplicate_detection import find_duplicate_matches
from ..services.ingest_orchestrator import start_import
from ..services.upload_reader import read_upload_with_limit
from .sessions import SessionOut

router = APIRouter(prefix="/uploads/imports", tags=["uploads"])

_UPLOADS: dict[str, dict[str, Any]] = {}
_UPLOAD_LOCKS: dict[str, threading.Lock] = {}
_UPLOADS_GUARD = threading.Lock()
_MANIFEST_NAME = ".upload.json"
_IMPORTED_DIR_NAME = "browser_imports"
_UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_MAX_ACTIVE_RESERVATIONS = 8


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


class CompleteUploadContract(CompleteUploadResponse):
    """Document the existing six-field session projection without filtering it."""

    session: SessionOut | None = None


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


def _import_dir(upload_id: str) -> Path:
    """The folder a completed upload is moved to and its session imports from (#944)."""
    if not _UPLOAD_ID_RE.fullmatch(upload_id):
        raise HTTPException(status_code=404, detail="Upload not found")
    return _safe_child_path(
        Path(get_config().imports_dir), PurePosixPath(_IMPORTED_DIR_NAME, upload_id)
    )


def _is_in_flight(state: dict[str, Any]) -> bool:
    """True while an upload still takes chunks, i.e. it has not reached /complete.

    Only an in-flight upload is a reservation, may be cancelled, or may be swept:
    once /complete has run, its files back a session (#944).
    """
    return state.get("status") == "uploading" and state.get("session_id") is None


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _reserved_bytes(root: Path) -> int:
    """Bytes on disk plus the not-yet-written remainder of every in-flight upload.

    A started upload holds its whole plan against the quota until it finishes, is
    cancelled, or is swept, so a reservation is visible before any chunk arrives.
    Counting only the remainder means bytes already written are never counted twice,
    and reading it off the manifests makes reservations survive a restart (#601).
    """
    total = _dir_size(root)
    for child in root.iterdir():
        if not child.is_dir():
            continue
        state = _read_manifest(child)
        if state is None:
            continue
        if _is_in_flight(state):
            total += max(0, state.get("total_bytes", 0) - state.get("uploaded_bytes", 0))
        else:
            # Imported in place by an earlier release: session data, not a reservation.
            total -= _dir_size(child)
    return total


def _active_reservations(root: Path) -> int:
    """Uploads still taking chunks; one that reached /complete is not a slot (#944)."""
    count = 0
    for child in root.iterdir():
        if child.is_dir():
            state = _read_manifest(child)
            if state is not None and _is_in_flight(state):
                count += 1
    return count


def _cleanup_old_uploads(root: Path, cleanup_after_hours: int) -> None:
    """Remove staging dirs of uploads abandoned before /complete.

    A completed upload is moved out of staging, but one an earlier release imported
    in place still holds a session's source images, so a dir whose manifest shows
    the upload reached /complete is never swept (#944).
    """
    cutoff = datetime.datetime.now(datetime.UTC).timestamp() - cleanup_after_hours * 3600
    for child in root.iterdir():
        if not child.is_dir() or child.stat().st_mtime >= cutoff:
            continue
        state = _read_manifest(child)
        if state is not None and not _is_in_flight(state):
            continue
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
    try:
        return confine_path(root.joinpath(*rel.parts), root, allow_root=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid upload path") from exc


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
    # The manifest lives with the files: in staging, or in the import folder once
    # /complete has moved them there (#944).
    root = Path(state["root"])
    root.mkdir(parents=True, exist_ok=True)
    manifest = _manifest_path(root)
    tmp = manifest.with_suffix(f"{manifest.suffix}.tmp")
    tmp.write_text(json.dumps(_state_for_disk(state), sort_keys=True))
    tmp.replace(manifest)


def _read_manifest(root: Path) -> dict[str, Any] | None:
    """Load the manifest of the upload whose files are in *root*, if it has one."""
    if not _UPLOAD_ID_RE.fullmatch(root.name):
        return None
    manifest = _manifest_path(root)
    if not manifest.exists():
        return None
    try:
        raw = json.loads(manifest.read_text())
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict) or raw.get("id") != root.name:
        return None
    raw["root"] = root
    return raw


def _load_state_from_manifest(upload_id: str) -> dict[str, Any] | None:
    # A completed upload's manifest moved with its files into the import folder.
    return _read_manifest(_upload_dir(upload_id)) or _read_manifest(_import_dir(upload_id))


def _move_to_import_folder(state: dict[str, Any]) -> Path:
    """Move a finished upload out of staging into the folder its session imports from.

    Staging is swept and counted against the upload quota, so a session's source
    images must not live there (#944). One rename moves the files and the manifest
    together, so the upload is either wholly staged or wholly imported.
    """
    src = Path(state["root"])
    dest = _import_dir(str(state["id"]))
    if src == dest:
        return dest  # a /complete retried after the move already happened
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise HTTPException(status_code=409, detail="Upload import folder already exists")
    # Under the start lock, so a concurrent sweep or quota scan never races the move.
    with _UPLOADS_GUARD:
        src.rename(dest)
    return dest


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
    by_path = _validate_plan(req, limits)
    # Sweep, measure and reserve in one critical section, so two concurrent starts
    # cannot both pass the quota check against the same measurement (#601).
    # ponytail: one process-wide lock serializes every start and rescans the staging
    # tree each time; shard per upload root if a second staging root ever exists.
    with _UPLOADS_GUARD:
        _cleanup_old_uploads(root, limits["cleanup_after_hours"])
        # Bound concurrent reservations: each in-flight manifest is one browser
        # import, and unbounded starts would let a LAN client exhaust disk with
        # empty reservations (#864).
        if _active_reservations(root) >= _MAX_ACTIVE_RESERVATIONS:
            raise HTTPException(
                status_code=409,
                detail="Too many concurrent uploads; wait for an import to finish or cancel one",
            )
        if _reserved_bytes(root) + req.total_bytes > limits["quota_bytes"]:
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
        # The manifest is the reservation: it is what the next start measures.
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
    limits = _limits()
    data = await read_upload_with_limit(
        chunk,
        limits["chunk_size_bytes"],
        too_large_detail="Chunk exceeds configured size",
    )
    with _lock_for(upload_id):
        if state["status"] != "uploading":
            raise HTTPException(status_code=409, detail="Upload is not accepting chunks")
        rel_path = _safe_upload_path(path)
        rel = rel_path.as_posix()
        planned = state["files"].get(rel)
        if planned is None:
            raise HTTPException(status_code=400, detail="Chunk path was not in upload plan")

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


@router.post(
    "/{upload_id}/complete", response_model=CompleteUploadResponse,
    responses={200: {"model": CompleteUploadContract}},
)
def complete_browser_import_upload(upload_id: str, db: DBSession = Depends(get_db)):
    with _lock_for(upload_id):
        # Read the state under the lock so a concurrent /complete that already imported
        # is visible here, and replay it instead of importing twice (#602).
        state = _state(upload_id)
        if state.get("session_id") is None:
            incomplete = [
                p for p, meta in state["files"].items() if meta["received"] != meta["size"]
            ]
            if incomplete:
                raise HTTPException(
                    status_code=409, detail=f"Upload is incomplete: {incomplete[0]}"
                )

            # Leave staging before any session points at the files, so neither the
            # sweep nor the quota ever sees a session's source images (#944).
            state["root"] = _move_to_import_folder(state)
            state["status"] = "importing"
            session = SessionModel(
                name=state["name"],
                folder_path=str(state["root"]),
                imported_at=datetime.datetime.now(datetime.UTC),
                photo_count=0,
                usable_count=0,
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            state["session_id"] = session.id
            _persist_state(state)
            start_import(session.id, state["root"], SessionLocal)
        session = db.get(SessionModel, state["session_id"])
    return CompleteUploadResponse(
        upload_id=upload_id,
        status=state["status"],
        uploaded_bytes=state["uploaded_bytes"],
        total_bytes=state["total_bytes"],
        file_count=len(state["files"]),
        session_id=state["session_id"],
        session=None
        if session is None
        else {
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
    if _UPLOADS.get(upload_id) is None and _load_state_from_manifest(upload_id) is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    with _lock_for(upload_id):
        # Re-read under the lock: a /complete holding it may have started the import.
        state = _UPLOADS.get(upload_id) or _load_state_from_manifest(upload_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Upload not found")
        if not _is_in_flight(state):
            # The files now back a session; cancelling must leave them alone (#944).
            raise HTTPException(
                status_code=409, detail="Upload is already importing and cannot be cancelled"
            )
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


# ---- pre-import duplicate check (issue #392) ----


class DuplicateCheckRequest(BaseModel):
    folder_path: str | None = None
    filenames: list[str] = []


class DuplicateMatch(BaseModel):
    session_id: int
    name: str
    reason: str
    overlap: float


class DuplicateCheckResponse(BaseModel):
    duplicate: bool
    matches: list[DuplicateMatch]


@router.post("/check-duplicate", response_model=DuplicateCheckResponse)
def check_duplicate_import(req: DuplicateCheckRequest, db: DBSession = Depends(get_db)):
    """Advisory-only: flags likely-duplicate sessions, never blocks the import."""
    matches = find_duplicate_matches(db, req.folder_path, req.filenames)
    return DuplicateCheckResponse(duplicate=bool(matches), matches=matches)
