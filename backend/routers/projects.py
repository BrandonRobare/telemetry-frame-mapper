from __future__ import annotations

import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config
from ..core.paths import confine_path
from ..db.database import SessionLocal, get_db
from ..db.models import CoverageRun, Reconstruction
from ..db.models import Project as ProjectModel
from ..db.models import Session as SessionModel
from ..services.ingest_orchestrator import start_import
from .sessions import SessionOut, _delete_session

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        error = _project_name_error(value)
        if error:
            raise ValueError(error)
        return value


def _project_name_error(name: str) -> str | None:
    if not name.strip():
        return "Project name must not be empty or whitespace"
    if name in (".", ".."):
        return "Project name must not be a dot segment"
    if "/" in name or "\\" in name:
        return "Project name must not contain path separators"
    if PureWindowsPath(name).drive:
        return "Project name must not be drive-qualified"
    return None


def _safe_project_name(name: str) -> str:
    error = _project_name_error(name)
    if error:
        raise HTTPException(status_code=400, detail=f"Project name is unsafe: {error}")
    return name


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: datetime.datetime | None
    session_count: int

    model_config = {"from_attributes": True}


class ImportRequest(BaseModel):
    folder_path: str
    name: str


class SiteTrendPointOut(BaseModel):
    """One existing session's read-only quality and reconstruction snapshot."""

    session_id: int
    session_name: str
    imported_at: datetime.datetime | None
    photo_count: int
    usable_count: int
    usable_pct: float | None
    coverage_pct: float | None
    reconstruction_id: int | None
    frames_registered: int | None
    psnr: float | None
    ssim: float | None


class SiteTrendOut(BaseModel):
    project_id: int
    points: list[SiteTrendPointOut]


@router.get("/", response_model=list[ProjectOut])
def list_projects(db: DBSession = Depends(get_db)):
    projects = db.query(ProjectModel).order_by(ProjectModel.created_at.desc()).all()
    result: list[ProjectOut] = []
    for p in projects:
        session_count = (
            db.query(SessionModel).filter(SessionModel.project_id == p.id).count()
        )
        result.append(
            ProjectOut(
                id=p.id,
                name=p.name,
                description=p.description,
                created_at=p.created_at,
                session_count=session_count,
            )
        )
    return result


@router.post("/", response_model=ProjectOut, status_code=201)
def create_project(req: ProjectCreate, db: DBSession = Depends(get_db)):
    existing = db.query(ProjectModel).filter(ProjectModel.name == req.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Project with this name already exists")
    p = ProjectModel(
        name=req.name,
        description=req.description,
        created_at=datetime.datetime.now(datetime.UTC),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return ProjectOut(
        id=p.id,
        name=p.name,
        description=p.description,
        created_at=p.created_at,
        session_count=0,
    )


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: DBSession = Depends(get_db)):
    p = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    session_count = (
        db.query(SessionModel).filter(SessionModel.project_id == p.id).count()
    )
    return ProjectOut(
        id=p.id,
        name=p.name,
        description=p.description,
        created_at=p.created_at,
        session_count=session_count,
    )


@router.delete("/{project_id}")
def delete_project(project_id: int, db: DBSession = Depends(get_db)):
    p = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    sessions = db.query(SessionModel).filter(SessionModel.project_id == p.id).all()
    try:
        for session in sessions:
            _delete_session(session, db, commit=False)
        db.delete(p)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                "Project deletion stopped; database unchanged. Some child jobs may have been "
                "cancelled or artifacts removed before the failure."
            ),
        ) from exc
    return {"ok": True}


@router.get("/{project_id}/sessions", response_model=list[SessionOut])
def list_project_sessions(project_id: int, db: DBSession = Depends(get_db)):
    p = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    sessions = (
        db.query(SessionModel)
        .filter(SessionModel.project_id == project_id)
        .order_by(SessionModel.imported_at.desc())
        .all()
    )
    return sessions


@router.get("/{project_id}/trends", response_model=SiteTrendOut)
def get_project_trends(project_id: int, db: DBSession = Depends(get_db)):
    """Return a time-ordered, read-only trend projection for one project.

    The projection deliberately reads only session, coverage-run, and completed
    reconstruction rows. It does not create a snapshot or run any quality work.
    """
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    sessions = (
        db.query(SessionModel)
        .filter(SessionModel.project_id == project_id)
        .order_by(
            SessionModel.imported_at.is_(None),
            SessionModel.imported_at.asc(),
            SessionModel.id.asc(),
        )
        .all()
    )
    session_ids = [session.id for session in sessions]
    if not session_ids:
        return SiteTrendOut(project_id=project_id, points=[])

    latest_reconstruction: dict[int, Reconstruction] = {}
    reconstructions = (
        db.query(Reconstruction)
        .filter(
            Reconstruction.session_id.in_(session_ids),
            Reconstruction.status == "complete",
        )
        .order_by(
            Reconstruction.completed_at.is_(None),
            Reconstruction.completed_at.desc(),
            Reconstruction.id.desc(),
        )
        .all()
    )
    for reconstruction in reconstructions:
        latest_reconstruction.setdefault(reconstruction.session_id, reconstruction)

    latest_coverage: dict[int, CoverageRun] = {}
    coverage_runs = (
        db.query(CoverageRun)
        .filter(CoverageRun.session_ids.in_([str(session_id) for session_id in session_ids]))
        .order_by(CoverageRun.run_at.desc(), CoverageRun.id.desc())
        .all()
    )
    for coverage_run in coverage_runs:
        # CoverageRun currently persists one session id as text (see coverage router).
        session_id = int(coverage_run.session_ids)
        latest_coverage.setdefault(session_id, coverage_run)

    return SiteTrendOut(
        project_id=project_id,
        points=[
            SiteTrendPointOut(
                session_id=session.id,
                session_name=session.name,
                imported_at=session.imported_at,
                photo_count=session.photo_count or 0,
                usable_count=session.usable_count or 0,
                usable_pct=(
                    round((session.usable_count or 0) / session.photo_count * 100, 1)
                    if session.photo_count
                    else None
                ),
                coverage_pct=(
                    latest_coverage[session.id].coverage_pct
                    if session.id in latest_coverage
                    else None
                ),
                reconstruction_id=(
                    latest_reconstruction[session.id].id
                    if session.id in latest_reconstruction
                    else None
                ),
                frames_registered=(
                    latest_reconstruction[session.id].frames_registered
                    if session.id in latest_reconstruction
                    else None
                ),
                psnr=(
                    latest_reconstruction[session.id].psnr
                    if session.id in latest_reconstruction
                    else None
                ),
                ssim=(
                    latest_reconstruction[session.id].ssim
                    if session.id in latest_reconstruction
                    else None
                ),
            )
            for session in sessions
        ],
    )


@router.post("/{project_id}/sessions/import", response_model=SessionOut)
def create_project_session(
    project_id: int, req: ImportRequest, db: DBSession = Depends(get_db)
):
    p = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    project_name = _safe_project_name(str(p.name))
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

    # Per-project subtree: imports/<project_name>/<folder_path>
    try:
        project_subtree = confine_path(imports_root / project_name, imports_root)
        folder = confine_path(project_subtree.joinpath(*user_path.parts), project_subtree)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Folder must be inside the project's imports directory"
        ) from exc
    if not folder.is_dir():
        # Also try the flat imports dir for backward compat
        try:
            flat = confine_path(imports_root.joinpath(*user_path.parts), imports_root)
        except ValueError:
            flat = None
        if flat is not None and flat.is_dir():
            folder = flat
        else:
            raise HTTPException(status_code=400, detail=f"Folder not found: {raw}")

    s = SessionModel(
        name=req.name,
        folder_path=str(folder),
        project_id=project_id,
        imported_at=datetime.datetime.now(datetime.UTC),
        photo_count=0,
        usable_count=0,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    start_import(s.id, folder, SessionLocal)
    return s
