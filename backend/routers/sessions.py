from __future__ import annotations

import datetime
import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config
from ..db.database import SessionLocal, get_db
from ..db.models import Image, Project, Reconstruction
from ..db.models import Session as SessionModel
from ..db.session_search import install_session_search_schema
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
        return _normalize_tags(v)


def _normalize_tags(tags: list[str] | None) -> list[str] | None:
    if tags is None:
        return None
    cleaned: list[str] = []
    for tag in tags:
        stripped = tag.strip()
        if not stripped:
            continue
        if len(stripped) > MAX_TAG_LENGTH:
            raise ValueError(f"tag must be at most {MAX_TAG_LENGTH} characters: {stripped!r}")
        if stripped not in cleaned:
            cleaned.append(stripped)
    return cleaned


SearchSource = Literal["session", "log", "defect"]


class SessionSearchMatchOut(BaseModel):
    source: SearchSource
    snippet: str


class SessionSearchOut(SessionOut):
    matches: list[SessionSearchMatchOut]


class DeleteOut(BaseModel):
    ok: bool


BulkOperation = Literal["archive", "assign_project", "replace_tags", "add_tags", "delete"]


class BulkSessionRequest(BaseModel):
    """Apply one small, explicit operation to several sessions.

    Missing session rows are reported per ID so a stale picker selection cannot
    hide work completed for the other selected sessions.
    """

    session_ids: list[int] = Field(min_length=1, max_length=100)
    operation: BulkOperation
    project_id: int | None = Field(default=None, gt=0)
    tags: list[str] | None = None
    confirm: str | None = None

    @field_validator("session_ids")
    @classmethod
    def validate_session_ids(cls, session_ids: list[int]) -> list[int]:
        if any(session_id <= 0 for session_id in session_ids):
            raise ValueError("session_ids must contain positive integers")
        if len(set(session_ids)) != len(session_ids):
            raise ValueError("session_ids must not contain duplicates")
        return session_ids

    @field_validator("tags")
    @classmethod
    def normalize_bulk_tags(cls, tags: list[str] | None) -> list[str] | None:
        return _normalize_tags(tags)

    @model_validator(mode="after")
    def validate_operation_fields(self) -> BulkSessionRequest:
        if self.operation == "assign_project" and self.project_id is None:
            raise ValueError("project_id is required when assigning a project")
        if self.operation in ("replace_tags", "add_tags") and self.tags is None:
            raise ValueError("tags are required for tag operations")
        if self.operation == "delete" and self.confirm != "DELETE":
            raise ValueError('delete requires confirm: "DELETE"')
        return self


class BulkSessionOutcome(BaseModel):
    session_id: int
    ok: bool
    error: str | None = None
    bundle_path: str | None = None


class BulkSessionResponse(BaseModel):
    operation: BulkOperation
    outcomes: list[BulkSessionOutcome]


@router.get("/", response_model=list[SessionOut])
def list_sessions(db: DBSession = Depends(get_db)):
    return db.query(SessionModel).order_by(SessionModel.imported_at.desc()).all()


def _ensure_session_search_schema(db: DBSession) -> None:
    """Cover fresh metadata-only SQLite databases used by local development and tests."""
    if db.get_bind().dialect.name != "sqlite":
        raise HTTPException(
            status_code=501,
            detail=(
                "Cross-session search requires SQLite FTS5; PostgreSQL search is not implemented."
            ),
        )
    present = db.execute(text("""
        SELECT count(*) FROM sqlite_master
        WHERE type IN ('table', 'trigger')
          AND name IN ('session_search', 'session_search_sessions_ai')
    """)).scalar_one()
    if present == 2:
        return
    install_session_search_schema(db.connection())
    db.commit()


def _fts_query(query: str) -> str:
    terms = re.findall(r"\w+", query, flags=re.UNICODE)
    if not terms:
        raise HTTPException(status_code=422, detail="Search query must include letters or numbers")
    return " AND ".join(f'"{term}"' for term in terms)


@router.get(
    "/search",
    response_model=list[SessionSearchOut],
    responses={501: {"description": "Available only for SQLite databases with FTS5."}},
)
def search_sessions(
    q: str = Query(min_length=1, max_length=100),
    source: SearchSource | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: DBSession = Depends(get_db),
):
    """Search session metadata, timeline messages, and defects with SQLite FTS5."""
    _ensure_session_search_schema(db)
    rows = db.execute(
        text("""
            SELECT session_id, source, snippet(session_search, 3, '', '', '…', 14) AS snippet
            FROM session_search
            WHERE session_search MATCH :query
              AND (:source IS NULL OR source = :source)
            ORDER BY bm25(session_search, 2.0, 0.0, 0.0, 1.0)
            LIMIT :row_limit
        """),
        {"query": _fts_query(q), "source": source, "row_limit": limit * 4},
    ).mappings().all()
    matches_by_session: dict[int, list[SessionSearchMatchOut]] = {}
    for row in rows:
        session_id = int(row["session_id"])
        matches = matches_by_session.setdefault(session_id, [])
        if len(matches) < 2:
            matches.append(SessionSearchMatchOut(source=row["source"], snippet=row["snippet"]))

    session_ids = list(matches_by_session)[:limit]
    if not session_ids:
        return []
    sessions = db.query(SessionModel).filter(SessionModel.id.in_(session_ids)).all()
    by_id = {session.id: session for session in sessions}
    return [
        SessionSearchOut(
            **SessionOut.model_validate(by_id[session_id]).model_dump(),
            matches=matches_by_session[session_id],
        )
        for session_id in session_ids
        if session_id in by_id
    ]


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


def _delete_session(s: SessionModel, db: DBSession) -> None:
    """Delete one session using the same cleanup path as the single-session API."""
    reconstructions = db.query(Reconstruction).filter(Reconstruction.session_id == s.id).all()
    images = db.query(Image).filter(Image.session_id == s.id).all()
    for rec in reconstructions:
        cancel_reconstruction(rec.id)
    cleanup_session_artifacts(s.id, images, reconstructions, get_config())
    db.delete(s)
    db.commit()


@router.post("/bulk", response_model=BulkSessionResponse)
def bulk_sessions(body: BulkSessionRequest, db: DBSession = Depends(get_db)):
    """Apply a single organization/archive/delete operation per selected session.

    Each session is committed independently. One stale ID or filesystem failure
    therefore reports an outcome without rolling back successful peers.
    """
    if body.operation == "assign_project":
        project = db.query(Project).filter(Project.id == body.project_id).first()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

    outcomes: list[BulkSessionOutcome] = []
    for session_id in body.session_ids:
        s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if s is None:
            outcomes.append(
                BulkSessionOutcome(session_id=session_id, ok=False, error="Session not found")
            )
            continue
        try:
            if body.operation == "archive":
                from ..services.session_bundle import build_session_archive

                zip_path = Path(get_config().exports_dir) / f"session_{session_id}_archive.zip"
                archive = build_session_archive(zip_path, s, db)
                outcomes.append(
                    BulkSessionOutcome(
                        session_id=session_id, ok=True, bundle_path=archive["bundle_path"]
                    )
                )
                continue
            if body.operation == "assign_project":
                s.project_id = body.project_id
            elif body.operation == "replace_tags":
                s.tags = json.dumps(body.tags) if body.tags else None
            elif body.operation == "add_tags":
                current_tags = SessionOut.model_validate(s).tags
                merged_tags = current_tags + [
                    tag for tag in body.tags or [] if tag not in current_tags
                ]
                s.tags = json.dumps(merged_tags) if merged_tags else None
            elif body.operation == "delete":
                _delete_session(s, db)
                outcomes.append(BulkSessionOutcome(session_id=session_id, ok=True))
                continue
            db.commit()
            outcomes.append(BulkSessionOutcome(session_id=session_id, ok=True))
        except Exception as exc:
            db.rollback()
            outcomes.append(BulkSessionOutcome(session_id=session_id, ok=False, error=str(exc)))
    return BulkSessionResponse(operation=body.operation, outcomes=outcomes)


@router.delete("/{session_id}", response_model=DeleteOut)
def delete_session(session_id: int, db: DBSession = Depends(get_db)):
    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    _delete_session(s, db)
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
    lighting_inconsistent: bool = False
    lighting_p10_p90_spread: float | None = None


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
        lighting_inconsistent=report["quality"]["lighting"]["inconsistent"],
        lighting_p10_p90_spread=report["quality"]["lighting"]["p10_p90_spread"],
    )


# ---- archive / restore bundle for machine moves (issue #370) ----


@router.post("/{session_id}/archive")
def archive_session(session_id: int, db: DBSession = Depends(get_db)):
    """Export a session as a portable .zip: its row, every cascaded child row, and
    any artifact files that exist on disk. Restore it elsewhere with POST /sessions/restore.
    """
    from ..services.reconstruction import _safe_export_path
    from ..services.session_bundle import build_session_archive

    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    exports_dir = Path(get_config().exports_dir)
    zip_path = _safe_export_path(exports_dir / f"session_{session_id}_archive.zip", exports_dir)
    return build_session_archive(zip_path, s, db)


class RestoreRequest(BaseModel):
    zip_path: str


@router.post("/restore")
def restore_session(req: RestoreRequest, db: DBSession = Depends(get_db)):
    """Restore a session archive (from POST /sessions/{id}/archive) as a brand-new
    session with fresh IDs. Never modifies or clobbers an existing session.
    """
    from ..services.reconstruction import _safe_export_path
    from ..services.session_bundle import restore_session_archive

    # zip_path is user-supplied; confine it to the app's own data roots so it can't be
    # used to read arbitrary files off the server filesystem.
    cfg = get_config()
    zip_path = None
    for root in (cfg.imports_dir, cfg.exports_dir, cfg.data_dir):
        try:
            zip_path = _safe_export_path(Path(req.zip_path), Path(root))
            break
        except ValueError:
            continue
    if zip_path is None:
        raise HTTPException(status_code=400, detail="Archive path is outside allowed directories")
    if not zip_path.is_file():
        raise HTTPException(status_code=404, detail="Archive zip not found")
    try:
        return restore_session_archive(zip_path, db)
    except (KeyError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid archive: {exc}") from exc
