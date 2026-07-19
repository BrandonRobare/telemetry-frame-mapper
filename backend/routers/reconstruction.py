from __future__ import annotations

import json
import logging
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config, get_render_config
from ..db.database import get_db
from ..db.models import Reconstruction, ReconstructionFrame, SessionFrameSelection, TargetArea
from ..services.artifact_cleanup import cleanup_reconstruction_artifacts
from ..services.camera_calibration import build_calibration_drift_report
from ..services.colmap_io import read_model
from ..services.preflight_quality import build_preflight_quality_report
from ..services.quality_report import (
    build_quality_scorecard,
    parse_surveyed_points_3d,
    validate_held_out_checkpoints,
)
from ..services.reconstruction import (
    _export_point_cloud,
    _load_geo_transform_for_reconstruction,
    _safe_export_path,
    _write_mesh_georef,
    build_reconstruction_diagnostics,
    cancel_reconstruction,
    compute_coverage_gaps,
    current_reconstruction_status_version,
    get_rec_log,
    plan_dense_rerun,
    semantic_overlay_bytes,
    start_flythrough_render,
    start_mesh_export,
    start_reconstruction,
    start_semantic_labeling,
    wait_for_reconstruction_status_change,
)
from ..services.semantic_labels import semantic_summary
from ..services.splat_cleanup import cleanup_ply_file
from ..services.splat_transform import (
    cleanup_splat as _splat_transform_cleanup,
)
from ..services.splat_transform import (
    compress_splat as _splat_transform_compress,
)
from ..services.splat_transform import (
    splat_transform_available as _splat_transform_probe,
)

router = APIRouter(prefix="/reconstruction", tags=["reconstruction"])
logger = logging.getLogger(__name__)
VALID_PRESETS = {"quick", "full"}


def _safe_export_http_path(path: Path) -> Path:
    cfg = get_config()
    try:
        return _safe_export_path(path, Path(cfg.exports_dir))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid export path") from exc


def _reconstruction_artifact_path(reconstruction_id: int, filename: str) -> Path:
    cfg = get_config()
    return _safe_export_http_path(Path(cfg.exports_dir) / str(reconstruction_id) / filename)


def _safe_owned_http_path(path: Path, *, allow_processed: bool = False) -> Path:
    cfg = get_config()
    roots = [Path(cfg.exports_dir)]
    if allow_processed:
        roots.append(Path(cfg.processed_dir))
    for root in roots:
        try:
            return _safe_export_path(path, root)
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail="Invalid artifact path")


def _bundle_metadata(rec: Reconstruction, files: dict[str, str | None]) -> dict:
    return {
        "id": rec.id,
        "session_id": rec.session_id,
        "source_session_ids": (
            json.loads(rec.source_session_ids) if rec.source_session_ids else None
        ),
        "status": rec.status,
        "mesh_status": rec.mesh_status,
        "frames_used": rec.frames_used,
        "frames_registered": rec.frames_registered,
        "psnr": rec.psnr,
        "ssim": rec.ssim,
        "files": files,
    }


class StartIn(BaseModel):
    session_id: int | None = None
    session_ids: list[int] | None = None
    preset: str = "quick"
    target_area_id: int | None = None
    parent_reconstruction_id: int | None = None

    @field_validator("preset")
    @classmethod
    def validate_preset(cls, v: str) -> str:
        if v not in VALID_PRESETS:
            raise ValueError(f"preset must be one of {VALID_PRESETS}")
        return v

    @field_validator("session_ids")
    @classmethod
    def validate_session_ids(cls, v: list[int] | None) -> list[int] | None:
        if v is not None and len(v) < 2:
            raise ValueError("session_ids must contain at least two session IDs")
        return v


class DenseRerunIn(BaseModel):
    """Explicit acknowledgement before a weak-area rerun is queued."""

    confirm: bool = False


class ReconstructionOut(BaseModel):
    id: int
    session_id: int
    parent_reconstruction_id: int | None = None
    source_session_ids: list[int] | None = None
    status: str
    preset: str
    progress_pct: float
    step: str
    frames_used: int
    frames_registered: int | None
    gaussian_count: int | None
    psnr: float | None
    ssim: float | None
    training_metrics: list[dict] | None = None
    error_msg: str | None
    geo_transform: str | None
    splat_path: str | None
    pointcloud_path: str | None = None
    mesh_glb_path: str | None = None
    mesh_obj_path: str | None = None
    mesh_mtl_path: str | None = None
    mesh_status: str | None = None
    mesh_error: str | None = None
    flythrough_path: str | None = None
    flythrough_status: str | None = None
    flythrough_error: str | None = None
    semantic_status: str | None = None
    semantic_error: str | None = None
    semantic_labels_path: str | None = None

    model_config = {"from_attributes": True}

    @field_validator("training_metrics", mode="before")
    @classmethod
    def parse_training_metrics(cls, v: object) -> list[dict] | None:
        if isinstance(v, str):
            return json.loads(v)
        return v  # type: ignore[return-value]

    @field_validator("source_session_ids", mode="before")
    @classmethod
    def parse_source_session_ids(cls, v: object) -> list[int] | None:
        if v is None:
            return None
        if isinstance(v, str):
            return json.loads(v)
        if isinstance(v, list):
            return v  # type: ignore[return-value]
        return None


class HistogramBin(BaseModel):
    min: float
    max: float
    count: int


class PreflightCompletenessOut(BaseModel):
    missing: int
    completeness_pct: float


class PreflightTimestampOut(PreflightCompletenessOut):
    duplicate_groups: int
    duplicate_frames: int
    gap_count: int
    max_gap_s: float
    typical_gap_s: float | None
    gap_threshold_s: float | None


class PreflightImageQualityOut(BaseModel):
    blur_threshold: float
    dark_threshold: float
    bright_threshold: float
    blur_count: int
    dark_count: int
    bright_count: int
    blur_pct: float
    dark_pct: float
    bright_pct: float
    flag_counts: dict[str, int]
    sharpness_histogram: list[HistogramBin]
    brightness_histogram: list[HistogramBin]


class PreflightCoverageOut(BaseModel):
    footprint_count: int
    footprint_coverage_pct: float
    estimated_overlap_pct: float | None
    union_area: float
    summed_footprint_area: float
    warnings: list[str]


class PreflightReportOut(BaseModel):
    session_id: int
    total_frames: int
    usable_frames: int
    gps: PreflightCompletenessOut
    timestamps: PreflightTimestampOut
    quality: PreflightImageQualityOut
    coverage: PreflightCoverageOut
    warnings: list[str]
    safe_to_reconstruct: str
    score: int
    recommended_action: str
    match_density: dict | None = None

class ReconstructionImageDiagnostic(BaseModel):
    id: int
    filename: str
    timestamp: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = None
    colmap_error_px: float | None = None
    registered: bool


class ReconstructionTimelineBucket(BaseModel):
    bucket: int
    start_index: int
    end_index: int
    total: int
    unregistered: int
    unregistered_pct: float


class ReconstructionMapHeatPoint(BaseModel):
    id: int
    filename: str
    latitude: float
    longitude: float
    weight: int


class ReconstructionSuggestion(BaseModel):
    code: str
    title: str
    detail: str
    setting: dict | None = None


class ReconstructionDiagnosticsOut(BaseModel):
    reconstruction_id: int
    summary: dict
    registered_images: list[ReconstructionImageDiagnostic]
    unregistered_images: list[ReconstructionImageDiagnostic]
    timeline_heatmap: list[ReconstructionTimelineBucket]
    map_heatmap: list[ReconstructionMapHeatPoint]
    suggestions: list[ReconstructionSuggestion]



class MeshStatusOut(BaseModel):
    id: int
    mesh_status: str | None = None
    mesh_error: str | None = None
    mesh_glb_path: str | None = None
    mesh_obj_path: str | None = None
    mesh_mtl_path: str | None = None

    model_config = {"from_attributes": True}


class FlythroughStatusOut(BaseModel):
    id: int
    flythrough_status: str | None = None
    flythrough_error: str | None = None
    flythrough_path: str | None = None

    model_config = {"from_attributes": True}



class SemanticStatusOut(BaseModel):
    id: int
    semantic_status: str | None = None
    semantic_error: str | None = None
    semantic_labels_path: str | None = None

    model_config = {"from_attributes": True}

class FlythroughKeyframe(BaseModel):
    position: list[float]
    target: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    duration_s: float = 3.0

    @field_validator("position", "target")
    @classmethod
    def validate_vec3(cls, v: list[float]) -> list[float]:
        if len(v) != 3:
            raise ValueError("must contain exactly three numbers")
        return [float(value) for value in v]

    @field_validator("duration_s")
    @classmethod
    def validate_duration(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("duration_s must be positive")
        return v


class RenderVideoIn(BaseModel):
    keyframes: list[FlythroughKeyframe]
    fps: int = Field(
        default_factory=lambda: int(get_render_config().get("flythrough_fps", 30)),
        ge=1,
        le=60,
    )
    width: int = Field(
        default_factory=lambda: int(get_render_config().get("flythrough_width", 1920)),
        ge=320,
        le=7680,
    )
    height: int = Field(
        default_factory=lambda: int(get_render_config().get("flythrough_height", 1080)),
        ge=240,
        le=4320,
    )

    @field_validator("keyframes")
    @classmethod
    def validate_keyframes(cls, v: list[FlythroughKeyframe]) -> list[FlythroughKeyframe]:
        if len(v) < 2:
            raise ValueError("At least two keyframes are required")
        return v


# ---- Quality report request / response models ----


class SurveyedPointIn(BaseModel):
    """A surveyed checkpoint in local reconstruction coordinates."""
    label: str | None = None
    x: float
    y: float
    z: float


class CheckpointValidationIn(BaseModel):
    points: list[SurveyedPointIn]

    @field_validator("points")
    @classmethod
    def at_least_one(cls, v: list[SurveyedPointIn]) -> list[SurveyedPointIn]:
        if len(v) == 0:
            raise ValueError("At least one checkpoint is required")
        return v


def _raise_start_error(exc: ValueError) -> None:
    msg = str(exc)
    if "not found" in msg.lower():
        raise HTTPException(status_code=404, detail=msg) from exc
    if "already running" in msg:
        raise HTTPException(status_code=409, detail=msg) from exc
    raise HTTPException(status_code=422, detail=msg) from exc


@router.get("/preflight/{session_id}", response_model=PreflightReportOut)
def get_preflight_report(session_id: int, db: DBSession = Depends(get_db)):
    try:
        return build_preflight_quality_report(session_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/start", response_model=ReconstructionOut, status_code=201)
def start(body: StartIn, db: DBSession = Depends(get_db)):
    if body.session_ids is not None:
        # Multi-session merge
        from ..services.session_merge import (
            SessionMergeError,
            validate_sessions_for_merge,
        )

        try:
            validate_sessions_for_merge(body.session_ids, db)
        except SessionMergeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        target_area_geojson: str | None = None
        if body.target_area_id is not None:
            ta = db.query(TargetArea).filter(TargetArea.id == body.target_area_id).first()
            if not ta:
                raise HTTPException(status_code=404, detail="Target area not found")
            if not ta.geom_geojson:
                raise HTTPException(
                    status_code=422, detail="Target area has no geometry defined"
                )
            target_area_geojson = ta.geom_geojson

        try:
            rec = start_reconstruction(
                body.session_id or body.session_ids[0],
                body.preset,
                db,
                target_area_geojson=target_area_geojson,
                source_session_ids=body.session_ids,
                parent_reconstruction_id=body.parent_reconstruction_id,
            )
        except ValueError as exc:
            msg = str(exc)
            if "already in progress" in msg:
                raise HTTPException(status_code=409, detail=msg) from exc
            raise HTTPException(status_code=422, detail=msg) from exc
        return rec

    # Single-session path (backward compatible)
    if body.session_id is None:
        raise HTTPException(
            status_code=422,
            detail="Either session_id or session_ids must be provided",
        )

    target_area_geojson: str | None = None
    if body.target_area_id is not None:
        ta = db.query(TargetArea).filter(TargetArea.id == body.target_area_id).first()
        if not ta:
            raise HTTPException(status_code=404, detail="Target area not found")
        if not ta.geom_geojson:
            raise HTTPException(status_code=422, detail="Target area has no geometry defined")
        target_area_geojson = ta.geom_geojson
    try:
        rec = start_reconstruction(
            body.session_id, body.preset, db,
            target_area_geojson=target_area_geojson,
            parent_reconstruction_id=body.parent_reconstruction_id,
        )
    except ValueError as exc:
        msg = str(exc)
        if "already in progress" in msg:
            raise HTTPException(status_code=409, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
    return rec


@router.get("/{reconstruction_id}/status", response_model=ReconstructionOut)
def get_status(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    return rec


@router.get("/{reconstruction_id}/diagnostics", response_model=ReconstructionDiagnosticsOut)
def get_diagnostics(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    return build_reconstruction_diagnostics(db, rec)


def _dense_rerun_plan_or_http_error(rec: Reconstruction, db: DBSession) -> dict:
    try:
        return plan_dense_rerun(db, rec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{reconstruction_id}/dense-rerun-plan")
def get_dense_rerun_plan(reconstruction_id: int, db: DBSession = Depends(get_db)):
    """Preview the explicit child rerun; this endpoint never starts work."""
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    return _dense_rerun_plan_or_http_error(rec, db)


@router.post("/{reconstruction_id}/dense-rerun", response_model=ReconstructionOut, status_code=201)
def start_dense_rerun(
    reconstruction_id: int, body: DenseRerunIn, db: DBSession = Depends(get_db)
):
    """Queue a denser child reconstruction only after an explicit confirmation."""
    if not body.confirm:
        raise HTTPException(status_code=422, detail="Set confirm=true to queue the dense rerun")
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    active_child = db.query(Reconstruction).filter(
        Reconstruction.parent_reconstruction_id == rec.id,
        Reconstruction.status.in_(["pending", "running_colmap", "running_gsplat"]),
    ).first()
    if active_child:
        raise HTTPException(
            status_code=409,
            detail=f"Dense rerun {active_child.id} is already in progress",
        )
    plan = _dense_rerun_plan_or_http_error(rec, db)
    try:
        return start_reconstruction(
            rec.session_id,
            plan["preset"],
            db,
            parent_reconstruction_id=rec.id,
            selected_image_ids=plan["rerun_image_ids"],
        )
    except ValueError as exc:
        _raise_start_error(exc)


def _ancestor_chain(rec: Reconstruction) -> list[int]:
    chain: list[int] = []
    seen = {rec.id}
    current = rec.parent
    while current is not None and current.id not in seen:
        chain.append(current.id)
        seen.add(current.id)
        current = current.parent
    return chain


@router.get("/{reconstruction_id}/lineage")
def get_lineage(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    return {
        "id": rec.id,
        "parent_reconstruction_id": rec.parent_reconstruction_id,
        "ancestor_ids": _ancestor_chain(rec),
        "child_ids": [c.id for c in rec.children],
    }


def _status_sse_payload(rec: Reconstruction) -> str:
    body = ReconstructionOut.model_validate(rec).model_dump(mode="json")
    return f"event: status\ndata: {json.dumps(body, separators=(',', ':'))}\n\n"


@router.get("/{reconstruction_id}/status/events")
def stream_status_events(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    # Release the FastAPI request-scoped session immediately — we create
    # short-lived sessions per poll iteration inside the generator so that
    # long-running SSE connections don't hold pooled connections open for
    # the duration of the reconstruction run.
    db.close()

    from backend.db.database import SessionLocal as _SessionLocal

    def events() -> Iterator[str]:
        version = current_reconstruction_status_version(reconstruction_id)
        deadline = time.monotonic() + 3600.0  # 1h hard cap
        while time.monotonic() < deadline:
            sdb = _SessionLocal()
            try:
                rec = sdb.query(Reconstruction).filter(
                    Reconstruction.id == reconstruction_id
                ).first()
                if rec is None:
                    yield "event: deleted\ndata: {}\n\n"
                    return
                yield _status_sse_payload(rec)
            finally:
                sdb.close()
            new_version = wait_for_reconstruction_status_change(reconstruction_id, version)
            if new_version == version:
                yield ": keepalive\n\n"
            else:
                version = new_version

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


LIVE_RECONSTRUCTION_STATUSES = {
    "pending", "running_colmap", "running_gsplat", "running_remote", "cancelling"
}


@router.post("/{reconstruction_id}/cancel", response_model=ReconstructionOut)
def request_cancel(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status not in LIVE_RECONSTRUCTION_STATUSES:
        raise HTTPException(status_code=409, detail="Reconstruction is not running")

    cancel_reconstruction(reconstruction_id)
    rec.status = "cancelling"
    rec.step = "cancelling"
    rec.error_msg = None
    db.commit()
    db.refresh(rec)
    return rec


@router.delete("/{reconstruction_id}")
def delete_reconstruction(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status in LIVE_RECONSTRUCTION_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                "Cancel running reconstruction and wait for it to stop "
                "before deleting artifacts"
            ),
        )
    cleanup_reconstruction_artifacts(rec, get_config())
    db.delete(rec)
    db.commit()
    return {"ok": True}


class FrameSelectionIn(BaseModel):
    session_id: int
    image_ids: list[int]


@router.post("/frame-selection", status_code=204)
def set_frame_selection(body: FrameSelectionIn, db: DBSession = Depends(get_db)):
    try:
        db.query(SessionFrameSelection).filter(
            SessionFrameSelection.session_id == body.session_id
        ).delete()
        for image_id in body.image_ids:
            db.add(SessionFrameSelection(session_id=body.session_id, image_id=image_id))
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"Invalid frame selection: {exc}") from exc


@router.delete("/frame-selection/{session_id}", status_code=204)
def clear_frame_selection(session_id: int, db: DBSession = Depends(get_db)):
    try:
        db.query(SessionFrameSelection).filter(
            SessionFrameSelection.session_id == session_id
        ).delete()
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=422, detail=f"Failed to clear frame selection: {exc}"
        ) from exc


@router.get("/frame-selection/{session_id}")
def get_frame_selection(session_id: int, db: DBSession = Depends(get_db)):
    rows = db.query(SessionFrameSelection).filter(
        SessionFrameSelection.session_id == session_id
    ).all()
    return {"image_ids": [r.image_id for r in rows]}


@router.get("/{reconstruction_id}/splat")
def download_splat(
    reconstruction_id: int,
    lod: str = Query("full", pattern="^(full|medium|preview)$"),
    db: DBSession = Depends(get_db),
):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(status_code=202, detail="Reconstruction still in progress")

    path_map = {
        "full": rec.splat_path,
        "medium": rec.splat_medium_path,
        "preview": rec.splat_preview_path,
    }
    splat_path = path_map[lod]
    if not splat_path or not Path(splat_path).exists():
        raise HTTPException(status_code=404, detail=f"Splat file ({lod}) not found on disk")

    return FileResponse(
        splat_path,
        media_type="application/octet-stream",
        filename=f"splat_{reconstruction_id}_{lod}.ply",
    )


@router.get("/{reconstruction_id}/pointcloud")
def download_pointcloud(
    reconstruction_id: int,
    format: str = Query("las", pattern="^(las|laz)$"),
    db: DBSession = Depends(get_db),
):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(status_code=202, detail="Reconstruction still in progress")

    ext = "laz" if format == "laz" else "las"
    canonical = _reconstruction_artifact_path(rec.id, f"pointcloud.{ext}")

    if not canonical.exists():
        if not rec.colmap_dir:
            raise HTTPException(status_code=404, detail="COLMAP workspace not found")
        if not rec.splat_path or not Path(rec.splat_path).exists():
            raise HTTPException(status_code=404, detail="Splat file not found on disk")
        try:
            _export_point_cloud(
                Path(rec.colmap_dir),
                Path(rec.splat_path),
                canonical,
                laz_backend=(format == "laz"),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"Failed to export point cloud: {exc}"
            ) from exc
        # Cache the pointcloud path: track both so the reconstruct-out model
        # can surface which formats are available.
        if ext == "las":
            rec.pointcloud_path = str(canonical)
        db.commit()

    media_type = "application/vnd.las" if ext == "las" else "application/octet-stream"
    filename = f"pointcloud_{reconstruction_id}.{ext}"
    return FileResponse(
        canonical,
        media_type=media_type,
        filename=filename,
    )


@router.post("/{reconstruction_id}/mesh", response_model=MeshStatusOut, status_code=202)
def generate_mesh(reconstruction_id: int, db: DBSession = Depends(get_db)):
    try:
        return start_mesh_export(reconstruction_id, db)
    except ValueError as exc:
        _raise_start_error(exc)


@router.get("/{reconstruction_id}/mesh/status", response_model=MeshStatusOut)
def get_mesh_status(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    return rec


@router.get("/{reconstruction_id}/mesh")
def download_mesh(
    reconstruction_id: int,
    format: str = Query("glb", pattern="^(glb|obj|mtl)$"),
    db: DBSession = Depends(get_db),
):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.mesh_status != "complete":
        raise HTTPException(status_code=202, detail="Mesh export still in progress")

    path_map = {
        "glb": rec.mesh_glb_path,
        "obj": rec.mesh_obj_path,
        "mtl": rec.mesh_mtl_path,
    }
    mesh_path_raw = path_map[format]
    if not mesh_path_raw:
        raise HTTPException(status_code=404, detail=f"Mesh file ({format}) not found on disk")
    safe_mesh_path = _safe_export_http_path(Path(mesh_path_raw))
    if not safe_mesh_path.exists():
        raise HTTPException(status_code=404, detail=f"Mesh file ({format}) not found on disk")

    media_types = {
        "glb": "model/gltf-binary",
        "obj": "text/plain",
        "mtl": "text/plain",
    }
    return FileResponse(
        safe_mesh_path,
        media_type=media_types[format],
        filename=f"mesh_{reconstruction_id}.{format}",
    )


@router.get("/{reconstruction_id}/download-bundle")
def download_reconstruction_bundle(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(status_code=202, detail="Reconstruction still in progress")
    if rec.mesh_status in {"pending", "running"}:
        raise HTTPException(status_code=202, detail="Mesh export still in progress")
    if not rec.mesh_glb_path:
        raise HTTPException(status_code=404, detail="GLB mesh file not found on disk")

    glb_path = _safe_owned_http_path(Path(rec.mesh_glb_path))
    if not glb_path.exists():
        raise HTTPException(status_code=404, detail="GLB mesh file not found on disk")

    thumb_path: Path | None = None
    if rec.thumb_path:
        thumb_path = _safe_owned_http_path(Path(rec.thumb_path), allow_processed=True)
        if not thumb_path.exists():
            thumb_path = None

    georef_path = _reconstruction_artifact_path(rec.id, "mesh_georef.json")
    if not georef_path.exists():
        try:
            geo = _load_geo_transform_for_reconstruction(rec)
            georef_path = _write_mesh_georef(georef_path.parent, rec, geo)
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"Failed to build mesh georef sidecar: {exc}"
            ) from exc

    bundle_path = _reconstruction_artifact_path(rec.id, f"reconstruction_{rec.id}_bundle.zip")
    bundle_path.parent.mkdir(parents=True, exist_ok=True)

    thumbnail_name = f"thumbnail{thumb_path.suffix.lower() or '.jpg'}" if thumb_path else None
    files = {
        "glb": "mesh.glb",
        "thumbnail": thumbnail_name,
        "mesh_georef": "mesh_georef.json",
        "metadata": "metadata.json",
    }
    metadata = _bundle_metadata(rec, files)

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(glb_path, "mesh.glb")
        if thumb_path and thumbnail_name:
            zf.write(thumb_path, thumbnail_name)
        zf.write(georef_path, "mesh_georef.json")
        zf.writestr("metadata.json", json.dumps(metadata, indent=2, sort_keys=True))

    return FileResponse(
        bundle_path,
        media_type="application/zip",
        filename=f"reconstruction_{reconstruction_id}_bundle.zip",
    )


@router.post(
    "/{reconstruction_id}/render-video",
    response_model=FlythroughStatusOut,
    status_code=202,
)
def render_video(
    reconstruction_id: int,
    body: RenderVideoIn,
    db: DBSession = Depends(get_db),
):
    keyframes = [frame.model_dump() for frame in body.keyframes]
    try:
        return start_flythrough_render(
            reconstruction_id,
            db,
            keyframes,
            fps=body.fps,
            width=body.width,
            height=body.height,
        )
    except ValueError as exc:
        _raise_start_error(exc)


@router.get("/{reconstruction_id}/flythrough/status", response_model=FlythroughStatusOut)
def get_flythrough_status(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    return rec


@router.get("/{reconstruction_id}/flythrough")
def download_flythrough(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.flythrough_status != "complete":
        raise HTTPException(status_code=202, detail="Flythrough render still in progress")

    canonical = _reconstruction_artifact_path(rec.id, "flythrough.mp4")
    if not canonical.exists():
        raise HTTPException(status_code=404, detail="Flythrough file not found on disk")

    return FileResponse(
        canonical,
        media_type="video/mp4",
        filename=f"flythrough_{reconstruction_id}.mp4",
    )


@router.post(
    "/{reconstruction_id}/semantic-labels",
    response_model=SemanticStatusOut,
    status_code=202,
)
def generate_semantic_labels(reconstruction_id: int, db: DBSession = Depends(get_db)):
    try:
        return start_semantic_labeling(reconstruction_id, db)
    except ValueError as exc:
        _raise_start_error(exc)


@router.get("/{reconstruction_id}/semantic-labels/status", response_model=SemanticStatusOut)
def get_semantic_status(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    return rec


@router.get("/{reconstruction_id}/semantic-labels")
def get_semantic_labels_summary(
    reconstruction_id: int,
    lod: str = Query("full", pattern="^(full|medium|preview)$"),
    db: DBSession = Depends(get_db),
):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.semantic_status in {"pending", "running"}:
        raise HTTPException(status_code=202, detail="Semantic labeling still in progress")
    labels_path = Path(rec.semantic_labels_path) if rec.semantic_labels_path else None
    if labels_path is None or not labels_path.exists():
        if rec.splat_path:
            fallback = Path(rec.splat_path).parent / "semantic_labels.npz"
            if fallback.exists():
                labels_path = fallback
    if labels_path is None or not labels_path.exists():
        raise HTTPException(status_code=404, detail="Semantic labels not found")
    try:
        return semantic_summary(labels_path, lod=lod)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to read semantic labels: {exc}",
        ) from exc


@router.get("/{reconstruction_id}/semantic-labels/overlay")
def get_semantic_overlay(
    reconstruction_id: int,
    lod: str = Query("preview", pattern="^(preview|medium)$"),
    db: DBSession = Depends(get_db),
):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.semantic_status in {"pending", "running"}:
        raise HTTPException(status_code=202, detail="Semantic labeling still in progress")
    try:
        payload = semantic_overlay_bytes(rec, lod=lod)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=payload, media_type="application/octet-stream")


@router.get("/{reconstruction_id}/geo-transform")
def get_geo_transform(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if not rec.geo_transform:
        raise HTTPException(status_code=404, detail="Geo-transform not yet available")
    try:
        return json.loads(rec.geo_transform)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500, detail="Stored geo-transform data is malformed"
        ) from exc


@router.get("/{reconstruction_id}/ortho/status")
def get_ortho_status(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    return {
        "id": rec.id,
        "ortho_status": getattr(rec, "ortho_status", None),
        "ortho_error": getattr(rec, "ortho_error", None),
        "ortho_path": getattr(rec, "ortho_path", None),
    }


@router.get("/{reconstruction_id}/ortho")
def download_ortho(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")

    ortho_status = getattr(rec, "ortho_status", None)
    if ortho_status != "complete":
        raise HTTPException(status_code=202, detail="Orthomosaic export still in progress")

    ortho_path_str = getattr(rec, "ortho_path", None)
    if not ortho_path_str:
        raise HTTPException(status_code=404, detail="Orthomosaic file path not recorded")

    canonical = _safe_export_http_path(Path(ortho_path_str))
    if not canonical.exists():
        raise HTTPException(status_code=404, detail="Orthomosaic file not found on disk")

    return FileResponse(
        canonical,
        media_type="image/tiff",
        filename=f"orthomosaic_{reconstruction_id}.tif",
    )


@router.get("/{reconstruction_id}/log")
def get_log(
    reconstruction_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: DBSession = Depends(get_db),
):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    lines = get_rec_log(reconstruction_id)
    return {"lines": lines[-limit:]}


class CleanupOut(BaseModel):
    n_before: int
    n_after: int
    cleaned_path: str
    stats: dict


class CleanupIn(BaseModel):
    opacity_keep_ratio: float | None = Field(default=None, gt=0.0, le=1.0)
    scale_std_threshold: float | None = Field(default=None, gt=0.0)
    outlier_k: int | None = Field(default=None, ge=0)
    outlier_std_threshold: float | None = Field(default=None, gt=0.0)
    target_area_id: int | None = None


@router.post("/{reconstruction_id}/cleanup", response_model=CleanupOut, status_code=201)
def cleanup_splat(
    reconstruction_id: int,
    body: CleanupIn | None = None,
    db: DBSession = Depends(get_db),
):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(
            status_code=422, detail="Reconstruction must be complete before cleanup"
        )
    if not rec.splat_path:
        raise HTTPException(
            status_code=404, detail="No splat file available for this reconstruction"
        )
    src = Path(rec.splat_path)
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Splat file not found on disk: {src}")

    dst = _reconstruction_artifact_path(rec.id, "splat_cleaned.ply")
    options = body.model_dump(exclude_none=True) if body else {}
    target_area_id = options.pop("target_area_id", None)
    if target_area_id is not None:
        ta = db.query(TargetArea).filter(TargetArea.id == target_area_id).first()
        if not ta:
            raise HTTPException(status_code=404, detail="Target area not found")
        if not ta.geom_geojson:
            raise HTTPException(status_code=422, detail="Target area has no geometry defined")
        options["target_area_geojson"] = ta.geom_geojson
    try:
        stats, n_before, n_after = cleanup_ply_file(src, dst, **options)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Splat cleanup failed: {exc}"
        ) from exc
    return CleanupOut(
        n_before=n_before,
        n_after=n_after,
        cleaned_path=str(dst),
        stats=stats,
    )


@router.get("/{reconstruction_id}/coverage-gaps")
def get_coverage_gaps(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(status_code=404, detail="Reconstruction not complete")
    if not rec.splat_path:
        raise HTTPException(status_code=404, detail="No splat available")

    splat_path = Path(rec.splat_path)

    if rec.coverage_gaps_path and Path(rec.coverage_gaps_path).exists():
        return json.loads(Path(rec.coverage_gaps_path).read_text())

    try:
        cells, output_path = compute_coverage_gaps(splat_path, reconstruction_id)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Failed to compute coverage gaps: {exc}"
        ) from exc

    rec.coverage_gaps_path = str(output_path)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist coverage gaps cache path")
    return cells


# ---- Quality report endpoints ----


def _parse_training_metrics(rec: Reconstruction) -> list[dict] | None:
    if rec.training_metrics:
        try:
            return json.loads(rec.training_metrics)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _load_coverage_gaps_from_disk(rec: Reconstruction) -> list[dict] | None:
    if rec.coverage_gaps_path:
        gaps_path = Path(rec.coverage_gaps_path)
        if gaps_path.exists():
            try:
                return json.loads(gaps_path.read_text())
            except (json.JSONDecodeError, OSError):
                return None
    return None


@router.get("/{reconstruction_id}/quality-scorecard")
def get_quality_scorecard(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(status_code=202, detail="Reconstruction still in progress")

    frames = db.query(ReconstructionFrame).filter(
        ReconstructionFrame.reconstruction_id == reconstruction_id
    ).all()
    training_metrics = _parse_training_metrics(rec)
    coverage_gaps = _load_coverage_gaps_from_disk(rec)

    return build_quality_scorecard(rec, frames, training_metrics, coverage_gaps)


@router.get("/{reconstruction_id}/calibration-drift-report")
def get_calibration_drift_report(reconstruction_id: int, db: DBSession = Depends(get_db)):
    """Return a bounded consistency report from COLMAP's completed sparse model."""
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(status_code=202, detail="Reconstruction still in progress")

    sparse_dir = Path(rec.colmap_dir or "") / "sparse" / "0"
    try:
        cameras = list(read_model(sparse_dir).cameras.values()) if rec.colmap_dir else []
    except (OSError, RuntimeError, ValueError):
        cameras = []
    return build_calibration_drift_report(cameras)


@router.post("/{reconstruction_id}/validate-checkpoints")
def validate_checkpoints(
    reconstruction_id: int,
    body: CheckpointValidationIn,
    db: DBSession = Depends(get_db),
):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(status_code=202, detail="Reconstruction still in progress")

    survey_points = parse_surveyed_points_3d(
        [p.model_dump() for p in body.points]
    )
    result = validate_held_out_checkpoints(rec, survey_points)

    if not result.get("available"):
        raise HTTPException(
            status_code=422,
            detail=result.get("reason", "No surface source available for validation"),
        )

    return result


# ---------------------------------------------------------------------------
# Splat transform: cleanup + compression (Node/npx gated)
# ---------------------------------------------------------------------------

class SplatTransformCleanupIn(BaseModel):
    opacity_floor: float | None = Field(default=0.01, ge=0.0, le=1.0)
    sh_bands: int | None = Field(default=0, ge=0, le=3)
    decimate: float | None = Field(default=None, gt=0.0, le=1.0)
    morton: bool = True


class SplatTransformCleanupOut(BaseModel):
    cleaned_path: str
    returncode: int
    stdout: str
    stderr: str


@router.post(
    "/{reconstruction_id}/splat-transform-cleanup",
    response_model=SplatTransformCleanupOut,
    status_code=201,
)
def splat_transform_cleanup(
    reconstruction_id: int,
    body: SplatTransformCleanupIn | None = None,
    db: DBSession = Depends(get_db),
):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(
            status_code=422,
            detail="Reconstruction must be complete before cleanup",
        )
    if not rec.splat_path:
        raise HTTPException(status_code=404, detail="No splat file available")
    src = Path(rec.splat_path)
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Splat file not found on disk: {src}")

    options = body.model_dump(exclude_none=False) if body else {}
    dst = _reconstruction_artifact_path(rec.id, "splat_transform_cleaned.ply")

    try:
        result = _splat_transform_cleanup(
            src,
            dst,
            opacity_floor=options.get("opacity_floor"),
            sh_bands=options.get("sh_bands"),
            decimate=options.get("decimate"),
            morton=options.get("morton", True),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SplatTransformCleanupOut(
        cleaned_path=str(dst),
        returncode=result.returncode,
        stdout=result.stdout[:5000],
        stderr=result.stderr[:5000],
    )


class SplatTransformCompressIn(BaseModel):
    format: str = Field("spz", pattern="^(spz|sog)$")
    quality: int | None = Field(default=None, ge=1, le=100)


class SplatTransformCompressOut(BaseModel):
    compressed_path: str
    returncode: int
    stdout: str
    stderr: str


@router.post(
    "/{reconstruction_id}/splat-transform-compress",
    response_model=SplatTransformCompressOut,
    status_code=201,
)
def splat_transform_compress(
    reconstruction_id: int,
    body: SplatTransformCompressIn | None = None,
    db: DBSession = Depends(get_db),
):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(
            status_code=422,
            detail="Reconstruction must be complete before compression",
        )
    if not rec.splat_path:
        raise HTTPException(status_code=404, detail="No splat file available")
    src = Path(rec.splat_path)
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Splat file not found on disk: {src}")

    fmt = body.format if body else "spz"
    quality = body.quality if body else None
    ext = fmt if fmt == "spz" else "sog"
    dst = _reconstruction_artifact_path(rec.id, f"splat_compressed.{ext}")

    try:
        result = _splat_transform_compress(src, dst, format=fmt, quality=quality)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SplatTransformCompressOut(
        compressed_path=str(dst),
        returncode=result.returncode,
        stdout=result.stdout[:5000],
        stderr=result.stderr[:5000],
    )


@router.get("/splat-transform-available")
def splat_transform_status():
    return _splat_transform_probe()
