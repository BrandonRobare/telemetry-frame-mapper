"""Public share viewer endpoints for persisted and legacy share links."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config
from ..db.database import get_db
from ..db.models import Reconstruction, ShareLink, ShareLinkUnlockSession
from ..services.pin_lock import record_unlock_failure, reset_unlock_attempts, unlock_retry_after
from ..services.reconstruction import _safe_export_path
from ..services.share_links import (
    SHARE_LINK_PREFIX,
    UNLOCK_COOKIE_NAME,
    build_public_viewer_payload,
    create_opaque_token,
    now_utc,
    parse_share_token,
    token_hash,
    verify_password,
)

router = APIRouter(prefix="/share", tags=["share"])


class ShareLinkUnlockRequest(BaseModel):
    password: str


def _bare_token(token: str) -> str:
    return token.removeprefix(SHARE_LINK_PREFIX)


def _active_link(link: ShareLink) -> None:
    if link.revoked_at is not None or link.expires_at <= now_utc():
        raise HTTPException(status_code=410, detail="Share link has expired or been revoked")


def _reconstruction_for_link(link: ShareLink, db: DBSession) -> Reconstruction:
    _active_link(link)
    rec = db.query(Reconstruction).filter(Reconstruction.id == link.reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(status_code=410, detail="Reconstruction not available")
    return rec


def _unlock_link(
    request: Request, db: DBSession, *, include_expired: bool = False
) -> ShareLink | None:
    session_token = request.cookies.get(UNLOCK_COOKIE_NAME)
    if not session_token:
        return None
    session = (
        db.query(ShareLinkUnlockSession)
        .filter(ShareLinkUnlockSession.token_hash == token_hash(session_token))
        .first()
    )
    if not session or (session.expires_at <= now_utc() and not include_expired):
        return None
    link = db.query(ShareLink).filter(ShareLink.id == session.share_link_id).first()
    if not link:
        return None
    return link


def _cookie_secure(request: Request) -> bool:
    """Use Secure on HTTPS, including a TLS-terminating reverse proxy."""
    forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    return request.url.scheme == "https" or forwarded.lower() == "https"


def _set_unlock_cookie(
    response: Response, request: Request, link: ShareLink, db: DBSession
) -> None:
    existing = _unlock_link(request, db)
    if existing and existing.id == link.id:
        return
    raw_session = create_opaque_token()
    db.add(
        ShareLinkUnlockSession(
            share_link_id=link.id,
            token_hash=token_hash(raw_session),
            expires_at=link.expires_at,
        )
    )
    db.commit()
    response.set_cookie(
        UNLOCK_COOKIE_NAME,
        raw_session,
        max_age=max(1, int((link.expires_at - now_utc()).total_seconds())),
        path="/share",
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(request),
    )


def _resolve_legacy_token(token: str, db: DBSession) -> Reconstruction:
    """Keep signed links behaving exactly as they did before persisted links."""
    try:
        parsed = parse_share_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid or expired share link") from exc
    rec = db.query(Reconstruction).filter(Reconstruction.id == parsed.reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(status_code=410, detail="Reconstruction not available")
    return rec


def _resolve_metadata_link(
    token: str, request: Request, response: Response, db: DBSession
) -> tuple[Reconstruction, bool]:
    """Resolve a new link first; unrecognised values retain the legacy path."""
    raw_token = _bare_token(token)
    link = db.query(ShareLink).filter(ShareLink.token_hash == token_hash(raw_token)).first()
    if not link:
        return _resolve_legacy_token(raw_token, db), True
    rec = _reconstruction_for_link(link, db)
    if link.password_hash:
        unlocked = _unlock_link(request, db)
        if not unlocked or unlocked.id != link.id:
            raise HTTPException(status_code=401, detail="Share link password required")
    _set_unlock_cookie(response, request, link, db)
    return rec, False


def _resolve_artifact_link(
    reconstruction_id: int, token: str | None, request: Request, db: DBSession
) -> Reconstruction:
    """New links use the HttpOnly session; legacy links retain token query access."""
    if token:
        rec = _resolve_legacy_token(_bare_token(token), db)
    else:
        link = _unlock_link(request, db, include_expired=True)
        if not link:
            raise HTTPException(status_code=401, detail="Share link unlock required")
        rec = _reconstruction_for_link(link, db)
    if rec.id != reconstruction_id:
        raise HTTPException(status_code=403, detail="Share link does not match reconstruction")
    return rec


def _safe_artifact_access(path_str: str) -> Path:
    """Validate that an artifact path is within configured safe directories."""
    cfg = get_config()
    for root in (cfg.exports_dir, cfg.processed_dir):
        try:
            return _safe_export_path(Path(path_str), Path(root))
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail="Artifact access denied")


@router.post("/token/{token}/unlock", status_code=204)
def unlock_share_link(
    token: str,
    body: ShareLinkUnlockRequest,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
):
    """Verify a link password and issue a scoped HttpOnly unlock session."""
    attempts = request.app.state.share_unlock_attempts
    client = request.client.host if request.client else "unknown"
    retry_after = unlock_retry_after(attempts, client)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts",
            headers={"Retry-After": str(retry_after)},
        )
    raw_token = _bare_token(token)
    link = db.query(ShareLink).filter(ShareLink.token_hash == token_hash(raw_token)).first()
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")
    _reconstruction_for_link(link, db)
    if not link.password_hash:
        raise HTTPException(status_code=403, detail="Share link does not require a password")
    if not verify_password(body.password, link.password_hash):
        record_unlock_failure(attempts, client)
        raise HTTPException(status_code=403, detail="Incorrect share link password")
    reset_unlock_attempts(attempts, client)
    _set_unlock_cookie(response, request, link, db)


@router.get("/token/{token}")
def public_viewer_metadata(
    token: str,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
):
    """Return read-only reconstruction metadata after required link access checks."""
    rec, legacy = _resolve_metadata_link(token, request, response, db)
    return build_public_viewer_payload(rec, legacy=legacy)


@router.get("/{reconstruction_id}/pointcloud")
def public_pointcloud(
    reconstruction_id: int,
    request: Request,
    token: str | None = Query(None, description="Legacy signed share token"),
    db: DBSession = Depends(get_db),
):
    """Download a point cloud using a new cookie session or legacy signed token."""
    rec = _resolve_artifact_link(reconstruction_id, token, request, db)
    if not rec.pointcloud_path:
        raise HTTPException(status_code=404, detail="Point cloud not available")
    safe_path = _safe_artifact_access(rec.pointcloud_path)
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="Point cloud file not found on disk")
    return FileResponse(
        safe_path,
        media_type="application/vnd.las",
        filename=f"pointcloud_{rec.id}.las",
    )


@router.get("/{reconstruction_id}/splat")
def public_splat(
    reconstruction_id: int,
    request: Request,
    token: str | None = Query(None, description="Legacy signed share token"),
    lod: str = Query("full", pattern="^(full|medium|preview)$"),
    db: DBSession = Depends(get_db),
):
    """Download a splat using a new cookie session or legacy signed token."""
    rec = _resolve_artifact_link(reconstruction_id, token, request, db)
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
        filename=f"splat_{rec.id}_{lod}.ply",
    )


@router.get("/{reconstruction_id}/mesh")
def public_mesh(
    reconstruction_id: int,
    request: Request,
    token: str | None = Query(None, description="Legacy signed share token"),
    format: str = Query("glb", pattern="^(glb|obj|mtl)$"),
    db: DBSession = Depends(get_db),
):
    """Download a mesh using a new cookie session or legacy signed token."""
    rec = _resolve_artifact_link(reconstruction_id, token, request, db)
    mesh_path = {
        "glb": rec.mesh_glb_path,
        "obj": rec.mesh_obj_path,
        "mtl": rec.mesh_mtl_path,
    }[format]
    if not mesh_path:
        raise HTTPException(status_code=404, detail=f"Mesh file ({format}) not available")
    safe_path = _safe_artifact_access(mesh_path)
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail=f"Mesh file ({format}) not found on disk")
    return FileResponse(
        safe_path,
        media_type={"glb": "model/gltf-binary", "obj": "text/plain", "mtl": "text/plain"}[format],
        filename=f"mesh_{rec.id}.{format}",
    )
