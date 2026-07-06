"""Public share viewer endpoints — no auth, token-validated access only."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config
from ..db.database import get_db
from ..db.models import Reconstruction
from ..services.reconstruction import _safe_export_path
from ..services.share_links import SHARE_LINK_PREFIX, build_public_viewer_payload, parse_share_token

router = APIRouter(prefix="/share", tags=["share"])


def _resolve_token(token: str, db: DBSession) -> Reconstruction:
    """Validate the share token and return the referenced reconstruction.

    Raises HTTPException with 403/404 semantics on any failure.
    """
    if token.startswith(SHARE_LINK_PREFIX):
        token = token[len(SHARE_LINK_PREFIX):]
    try:
        parsed = parse_share_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=403, detail="Invalid or expired share link"
        ) from exc
    rec = db.query(Reconstruction).filter(Reconstruction.id == parsed.reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(status_code=410, detail="Reconstruction not available")
    return rec


def _safe_artifact_access(path_str: str) -> Path:
    """Validate that an artifact path is within configured safe directories.

    Checks exports_dir first (most artifacts land there), then processed_dir.
    """
    cfg = get_config()
    for root in (cfg.exports_dir, cfg.processed_dir):
        try:
            return _safe_export_path(Path(path_str), Path(root))
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail="Artifact access denied")


@router.get("/token/{token}")
def public_viewer_metadata(token: str, db: DBSession = Depends(get_db)):
    """Public viewer: return read-only reconstruction metadata."""
    rec = _resolve_token(token, db)
    return build_public_viewer_payload(rec)


@router.get("/{reconstruction_id}/pointcloud")
def public_pointcloud(
    reconstruction_id: int,
    token: str = Query(..., description="Valid share token for this reconstruction"),
    db: DBSession = Depends(get_db),
):
    """Public pointcloud download — token-gated."""
    rec = _resolve_token(token, db)
    if rec.id != reconstruction_id:
        raise HTTPException(status_code=403, detail="Token does not match reconstruction")
    if not rec.pointcloud_path:
        raise HTTPException(status_code=404, detail="Point cloud not available")
    safe_path = _safe_artifact_access(rec.pointcloud_path)
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="Point cloud file not found on disk")
    return FileResponse(
        safe_path,
        media_type="application/vnd.las",
        filename=f"pointcloud_{reconstruction_id}.las",
    )


@router.get("/{reconstruction_id}/splat")
def public_splat(
    reconstruction_id: int,
    token: str = Query(..., description="Valid share token for this reconstruction"),
    lod: str = Query("full", pattern="^(full|medium|preview)$"),
    db: DBSession = Depends(get_db),
):
    """Public splat download — token-gated."""
    rec = _resolve_token(token, db)
    if rec.id != reconstruction_id:
        raise HTTPException(status_code=403, detail="Token does not match reconstruction")
    path_map = {
        "full": rec.splat_path,
        "medium": rec.splat_medium_path,
        "preview": rec.splat_preview_path,
    }
    splat_path = path_map[lod]
    if not splat_path:
        raise HTTPException(status_code=404, detail=f"Splat ({lod}) not available")
    safe_path = _safe_artifact_access(splat_path)
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail=f"Splat file ({lod}) not found on disk")
    return FileResponse(
        safe_path,
        media_type="application/octet-stream",
        filename=f"splat_{reconstruction_id}_{lod}.ply",
    )


@router.get("/{reconstruction_id}/mesh")
def public_mesh(
    reconstruction_id: int,
    token: str = Query(..., description="Valid share token for this reconstruction"),
    format: str = Query("glb", pattern="^(glb|obj|mtl)$"),
    db: DBSession = Depends(get_db),
):
    """Public mesh download — token-gated."""
    rec = _resolve_token(token, db)
    if rec.id != reconstruction_id:
        raise HTTPException(status_code=403, detail="Token does not match reconstruction")
    path_map = {
        "glb": rec.mesh_glb_path,
        "obj": rec.mesh_obj_path,
        "mtl": rec.mesh_mtl_path,
    }
    mesh_path_raw = path_map[format]
    if not mesh_path_raw:
        raise HTTPException(status_code=404, detail=f"Mesh file ({format}) not available")
    safe_path = _safe_artifact_access(mesh_path_raw)
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail=f"Mesh file ({format}) not found on disk")
    media_types = {
        "glb": "model/gltf-binary",
        "obj": "text/plain",
        "mtl": "text/plain",
    }
    return FileResponse(
        safe_path,
        media_type=media_types[format],
        filename=f"mesh_{reconstruction_id}.{format}",
    )