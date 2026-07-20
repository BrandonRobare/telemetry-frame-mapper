from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config, get_webodm_config
from ..db.database import get_db
from ..db.models import Image
from ..db.models import Session as SessionModel
from ..services.webodm import (
    WebODMError,
    cancel_task,
    create_project,
    create_task,
    download_asset,
    get_task,
)

router = APIRouter(prefix="/webodm", tags=["webodm"])
_RELEVANT_ASSETS = {"orthophoto.tif", "georeferenced_model.las", "georeferenced_model.ply"}


class TaskOption(BaseModel):
    name: str = Field(min_length=1)
    value: str | int | float | bool


class SubmitTaskIn(BaseModel):
    project_name: str | None = Field(default=None, min_length=1, max_length=255)
    task_name: str | None = Field(default=None, min_length=1, max_length=255)
    options: list[TaskOption] = Field(default_factory=list)


class PullResultsIn(BaseModel):
    assets: list[str] | None = None


def _webodm_error(exc: WebODMError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.post("/sessions/{session_id}/tasks", status_code=201)
def submit_session_task(
    session_id: int, body: SubmitTaskIn, db: DBSession = Depends(get_db)
):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    image_rows = db.query(Image).filter(
        Image.session_id == session_id, Image.usable.is_(True)
    ).all()
    images = [Path(image.filepath) for image in image_rows if Path(image.filepath).is_file()]
    if len(images) < 2:
        raise HTTPException(status_code=422, detail="Session needs at least two usable image files")
    config = get_webodm_config()
    try:
        project_id = create_project(config, body.project_name or session.name)
        task_id = create_task(
            config,
            project_id,
            body.task_name or session.name,
            images,
            [option.model_dump() for option in body.options],
        )
    except WebODMError as exc:
        raise _webodm_error(exc) from exc
    return {"project_id": project_id, "task_id": task_id, "images_submitted": len(images)}


@router.get("/projects/{project_id}/tasks/{task_id}")
def task_status(project_id: int, task_id: int):
    try:
        task = get_task(get_webodm_config(), project_id, task_id)
    except WebODMError as exc:
        raise _webodm_error(exc) from exc
    return {
        "project_id": project_id,
        "task_id": task_id,
        "status": task.get("status"),
        "status_name": {10: "queued", 20: "running", 30: "failed", 40: "completed"}.get(
            task.get("status"), "unknown"
        ),
        "progress": task.get("running_progress"),
        "upload_progress": task.get("upload_progress"),
        "error": task.get("last_error"),
        "available_assets": task.get("available_assets", []),
    }


@router.post("/projects/{project_id}/tasks/{task_id}/cancel", status_code=202)
def cancel_webodm_task(project_id: int, task_id: int):
    try:
        cancel_task(get_webodm_config(), project_id, task_id)
    except WebODMError as exc:
        raise _webodm_error(exc) from exc
    return {"project_id": project_id, "task_id": task_id, "status": "cancelling"}


@router.post("/projects/{project_id}/tasks/{task_id}/results")
def pull_task_results(project_id: int, task_id: int, body: PullResultsIn):
    config = get_webodm_config()
    try:
        task = get_task(config, project_id, task_id)
        if task.get("status") != 40:
            raise HTTPException(status_code=409, detail="WebODM task is not completed")
        available = set(task.get("available_assets") or [])
        requested = set(body.assets) if body.assets is not None else _RELEVANT_ASSETS & available
        unknown = requested - available
        if unknown:
            detail = f"WebODM assets unavailable: {', '.join(sorted(unknown))}"
            raise HTTPException(status_code=422, detail=detail)
        if not requested:
            raise HTTPException(
                status_code=422, detail="WebODM task has no supported mapping assets"
            )
        output_dir = Path(get_config().exports_dir) / "webodm" / str(project_id) / str(task_id)
        saved = [
            str(download_asset(config, project_id, task_id, asset, output_dir))
            for asset in sorted(requested)
        ]
    except WebODMError as exc:
        raise _webodm_error(exc) from exc
    return {"project_id": project_id, "task_id": task_id, "saved_assets": saved}
