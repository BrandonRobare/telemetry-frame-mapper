from __future__ import annotations

import datetime
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config
from ..db.database import SessionLocal, get_db
from ..db.models import Project as ProjectModel
from ..db.models import Session as SessionModel
from ..services.ingest_orchestrator import start_import

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: datetime.datetime | None
    session_count: int

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    id: int
    name: str
    folder_path: str
    imported_at: datetime.datetime | None
    photo_count: int
    usable_count: int
    project_id: int | None

    model_config = {"from_attributes": True}


class ImportRequest(BaseModel):
    folder_path: str
    name: str


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
        created_at=datetime.datetime.now(datetime.timezone.utc),
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
    # Cascade delete sessions via SQLAlchemy relationship.
    db.delete(p)
    db.commit()
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


@router.post("/{project_id}/sessions/import", response_model=SessionOut)
def create_project_session(
    project_id: int, req: ImportRequest, db: DBSession = Depends(get_db)
):
    p = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

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
    project_subtree = imports_root.joinpath(p.name)
    folder = project_subtree.joinpath(*user_path.parts).resolve()
    if not folder.is_relative_to(project_subtree):
        raise HTTPException(
            status_code=400,
            detail="Folder must be inside the project's imports directory",
        )
    if not folder.is_dir():
        # Also try the flat imports dir for backward compat
        flat = imports_root.joinpath(*user_path.parts).resolve()
        if flat.is_relative_to(imports_root) and flat.is_dir():
            folder = flat
        else:
            raise HTTPException(status_code=400, detail=f"Folder not found: {raw}")

    s = SessionModel(
        name=req.name,
        folder_path=str(folder),
        project_id=project_id,
        imported_at=datetime.datetime.now(datetime.timezone.utc),
        photo_count=0,
        usable_count=0,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    start_import(s.id, folder, SessionLocal)
    return s