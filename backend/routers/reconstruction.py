from __future__ import annotations

import json
import logging
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config, get_render_config
from ..db.database import get_db
from ..db.models import Reconstruction, SessionFrameSelection, TargetArea
from ..services.artifact_cleanup import cleanup_reconstruction_artifacts
from ..services.preflight_quality import build_preflight_quality_report
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
    start_flythrough_render,
    start_mesh_export,
    start_reconstruction,
    wait_for_reconstruction_status_change,
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
        "status": rec.status,
        "mesh_status": rec.mesh_status,
        "frames_used": rec.frames_used,
        "frames_registered": rec.frames_registered,
        "psnr": rec.psnr,
        "ssim": rec.ssim,
        "files": files,
    }


class StartIn(BaseModel):
    session_id: int
    preset: str = "quick"
    target_area_id: int | None = None

    @field_validator("preset")
    @classmethod
    def validate_preset(cls, v: str) -> str:
        if v not in VALID_PRESETS:
            raise ValueError(f"preset must be one of {VALID_PRESETS}")
        return v


class ReconstructionOut(BaseModel):
    id: int
    session_id: int
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

    model_config = {"from_attributes": True}

    @field_validator("training_metrics", mode="before")
    @classmethod
    def parse_training_metrics(cls, v: object) -> list[dict] | None:
        if isinstance(v, str):
            return json.loads(v)
        return v  # type: ignore[return-value]


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


LIVE_RECONSTRUCTION_STATUSES = {"pending", "running_colmap", "running_gsplat", "cancelling"}


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
def download_pointcloud(reconstruction_id: int, db: DBSession = Depends(get_db)):
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(status_code=202, detail="Reconstruction still in progress")

    canonical = _reconstruction_artifact_path(rec.id, "pointcloud.las")

    if not canonical.exists():
        if not rec.colmap_dir:
            raise HTTPException(status_code=404, detail="COLMAP workspace not found")
        if not rec.splat_path or not Path(rec.splat_path).exists():
            raise HTTPException(status_code=404, detail="Splat file not found on disk")
        try:
            _export_point_cloud(Path(rec.colmap_dir), Path(rec.splat_path), canonical)
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"Failed to export point cloud: {exc}"
            ) from exc
        rec.pointcloud_path = str(canonical)
        db.commit()

    return FileResponse(
        canonical,
        media_type="application/vnd.las",
        filename=f"pointcloud_{reconstruction_id}.las",
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
