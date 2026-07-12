from __future__ import annotations

import datetime
import json
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config
from ..db.database import SessionLocal, get_db
from ..db.models import Image, Reconstruction
from ..db.models import Session as SessionModel
from ..services.artifact_cleanup import cleanup_session_artifacts
from ..services.ingest_orchestrator import get_progress, start_import
from ..services.preflight_quality import build_quick_report
from ..services.reconstruction import cancel_reconstruction

router = APIRouter(prefix="/sessions", tags=["sessions"])

# Tags are short organizational labels ("roof", "north-field"); cap the length so
# they stay chip-sized in the UI and cheap to filter on.
MAX_TAG_LENGTH = 40


class SessionOut(BaseModel):
    id: int
    name: str
    folder_path: str
    imported_at: datetime.datetime | None
    photo_count: int
    usable_count: int
    project_id: int | None = None
    tags: list[str] = []
    notes: str | None = None

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v: object) -> list[str]:
        """The DB stores tags as a JSON string in a Text column; decode for the API."""
        if v is None:
            return []
        if isinstance(v, str):
            return json.loads(v)
        return v  # type: ignore[return-value]


class SessionPatch(BaseModel):
    """PATCH body — omitted (None) fields are left unchanged.

    ``tags`` replaces the whole list; ``notes: ""`` clears the notes.
    """

    tags: list[str] | None = None
    notes: str | None = None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned: list[str] = []
        for tag in v:
            stripped = tag.strip()
            if not stripped:
                continue
            if len(stripped) > MAX_TAG_LENGTH:
                raise ValueError(f"tag must be at most {MAX_TAG_LENGTH} characters: {stripped!r}")
            if stripped not in cleaned:
                cleaned.append(stripped)
        return cleaned


class DeleteOut(BaseModel):
    ok: bool


@router.get("/", response_model=list[SessionOut])
def list_sessions(db: DBSession = Depends(get_db)):
    return db.query(SessionModel).order_by(SessionModel.imported_at.desc()).all()


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: DBSession = Depends(get_db)):
    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s


@router.patch("/{session_id}", response_model=SessionOut)
def patch_session(session_id: int, body: SessionPatch, db: DBSession = Depends(get_db)):
    """Update field-organization metadata (tags, operator notes) on a session."""
    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if body.tags is not None:
        s.tags = json.dumps(body.tags) if body.tags else None
    if body.notes is not None:
        s.notes = body.notes.strip() or None
    db.commit()
    db.refresh(s)
    return s


@router.delete("/{session_id}", response_model=DeleteOut)
def delete_session(session_id: int, db: DBSession = Depends(get_db)):
    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    reconstructions = db.query(Reconstruction).filter(
        Reconstruction.session_id == session_id
    ).all()
    images = db.query(Image).filter(Image.session_id == session_id).all()
    for rec in reconstructions:
        cancel_reconstruction(rec.id)
    cleanup_session_artifacts(session_id, images, reconstructions, get_config())
    db.delete(s)
    db.commit()
    return {"ok": True}


class ImportRequest(BaseModel):
    folder_path: str
    name: str


@router.post("/import", response_model=SessionOut)
def import_session(req: ImportRequest, db: DBSession = Depends(get_db)):
    cfg = get_config()
    imports_root = Path(cfg.imports_dir).resolve()
    raw = req.folder_path.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Folder path must not be empty")
    user_path = PurePosixPath(raw.replace("\\", "/"))
    if user_path.is_absolute():
        raise HTTPException(status_code=400, detail="Folder path must be relative")
    if any(part in ("", ".", "..") for part in user_path.parts):
        raise HTTPException(status_code=400, detail="Folder path contains invalid segments")
    folder = imports_root.joinpath(*user_path.parts).resolve()
    if not folder.is_relative_to(imports_root):
        raise HTTPException(status_code=400, detail="Folder must be inside the imports directory")
    if not folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Folder not found: {raw}")
    s = SessionModel(
        name=req.name,
        folder_path=str(folder),
        imported_at=datetime.datetime.now(datetime.timezone.utc),
        photo_count=0,
        usable_count=0,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    start_import(s.id, folder, SessionLocal)
    return s


@router.get("/{session_id}/progress")
def session_progress(session_id: int):
    return get_progress(session_id)


class QuickReportOut(BaseModel):
    session_id: int
    total_frames: int
    usable_frames: int
    score: int
    safe_to_reconstruct: str
    recommended_action: str
    warnings: list[str]
    gps_completeness_pct: float
    timestamp_completeness_pct: float
    blur_pct: float
    exposure_issue_pct: float
    estimated_overlap_pct: float | None
    match_density_weak_ratio: float | None = None
    match_density_avg_matches: float | None = None


@router.get("/{session_id}/quick-report", response_model=QuickReportOut)
def get_quick_report(session_id: int, db: DBSession = Depends(get_db)):
    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        report = build_quick_report(session_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    match_density = report.get("match_density")
    weak_ratio = None
    avg_matches = None
    if isinstance(match_density, dict):
        weak_ratio = match_density.get("weak_ratio")
        avg_matches = match_density.get("avg_matches")

    return QuickReportOut(
        session_id=report["session_id"],
        total_frames=report["total_frames"],
        usable_frames=report["usable_frames"],
        score=report["score"],
        safe_to_reconstruct=report["safe_to_reconstruct"],
        recommended_action=report["recommended_action"],
        warnings=report["warnings"],
        gps_completeness_pct=report["gps"]["completeness_pct"],
        timestamp_completeness_pct=report["timestamps"]["completeness_pct"],
        blur_pct=report["quality"]["blur_pct"],
        exposure_issue_pct=report["quality"]["dark_pct"] + report["quality"]["bright_pct"],
        estimated_overlap_pct=report["coverage"]["estimated_overlap_pct"],
        match_density_weak_ratio=weak_ratio,
        match_density_avg_matches=avg_matches,
    )
