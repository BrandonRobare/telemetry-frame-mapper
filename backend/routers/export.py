from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session as DBSession

from ..core.config import get_config
from ..db.database import get_db
from ..db.models import Image, Measurement, Reconstruction
from ..db.models import Session as SessionModel
from ..services.geometry_exports import feature_collection, geometry_feature

router = APIRouter(prefix="/export", tags=["export"])


@router.post("/webodm-georeferencing-csv")
def export_webodm_georeferencing_csv(session_id: int, db: DBSession = Depends(get_db)):
    """Build a WebODM/OpenDroneMap georeferencing CSV-only zip.

    The archive intentionally contains only ``odm_georeferencing.csv`` for
    workflows that need the ODM georeferencing sidecar, not a full image bundle.
    """
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    images = (
        db.query(Image)
        .filter(Image.session_id == session_id, Image.usable == True)  # noqa: E712
        .all()
    )
    exports_dir = Path(get_config().exports_dir)
    exports_dir.mkdir(parents=True, exist_ok=True)
    zip_path = exports_dir / f"webodm_georeferencing_csv_{session_id}.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        csv_rows = "filename,latitude,longitude,altitude\n"
        for img in images:
            # Use explicit None checks — 0.0 is a valid coordinate value
            lat = "" if img.latitude is None else img.latitude
            lon = "" if img.longitude is None else img.longitude
            alt = "" if img.altitude_m is None else img.altitude_m
            csv_rows += f"{img.filename},{lat},{lon},{alt}\n"
        zf.writestr("odm_georeferencing.csv", csv_rows)
    return {
        "zip_path": str(zip_path),
        "image_count": len(images),
        "contents": ["odm_georeferencing.csv"],
        "export_type": "webodm_georeferencing_csv_only",
    }


def _safe_manifest_artifact_path(raw_path: str) -> Path:
    from ..services.reconstruction import _safe_export_path

    cfg = get_config()
    for root_value in (cfg.imports_dir, cfg.processed_dir, cfg.exports_dir, cfg.data_dir):
        root = Path(root_value)
        try:
            return _safe_export_path(Path(raw_path), root)
        except ValueError:
            continue
    raise HTTPException(
        status_code=422,
        detail="artifact_path is outside configured safe directories",
    )


@router.post("/reproducibility-manifest")
def export_reproducibility_manifest(workflow: str, artifact_path: str | None = None):
    """Generate a reproducibility manifest for an import/reconstruction/export artifact."""
    from ..services.reproducibility_manifest import build_reproducibility_manifest

    cfg = get_config()
    settings = {
        k: getattr(cfg, k)
        for k in ("target_crs", "default_basemap", "exports_dir", "processed_dir")
    }
    artifacts = [_safe_manifest_artifact_path(artifact_path)] if artifact_path else []
    return build_reproducibility_manifest(workflow=workflow, settings=settings, artifacts=artifacts)


@router.post("/reconstructions/{reconstruction_id}/share-bundle")
def export_reconstruction_share_bundle(reconstruction_id: int, db: DBSession = Depends(get_db)):
    """Create a static share bundle for a completed reconstruction."""
    from ..db.models import Reconstruction
    from ..services.share_bundle import build_share_bundle

    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    try:
        return build_share_bundle(
            Path(get_config().exports_dir) / f"reconstruction_{reconstruction_id}_share.zip", rec
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/reconstructions/{reconstruction_id}/orthomosaic", status_code=202)
def export_orthomosaic(reconstruction_id: int, db: DBSession = Depends(get_db)):
    """Start an orthomosaic GeoTIFF export for a completed reconstruction.

    The export runs asynchronously. Poll ``/reconstruction/{id}/ortho/status`` for progress.
    Returns 202 with the updated reconstruction object (including ``ortho_status``).
    """
    from ..db.models import Reconstruction
    from ..services.orthomosaic_export import start_orthomosaic_export

    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")

    # Guard: must have a point source
    if not rec.splat_path and not rec.pointcloud_path and not rec.colmap_dir:
        raise HTTPException(
            status_code=422,
            detail=(
                "Reconstruction has no splat, point cloud, or COLMAP workspace. "
                "At least one point source is required for orthomosaic export."
            ),
        )

    try:
        rec = start_orthomosaic_export(reconstruction_id, db)
        return rec
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ponytail: flat {name: keep_ratio} dict, not a preset framework — add
# structure only when a preset needs more than an opacity keep-ratio knob.
_SPLAT_EXPORT_PRESETS = {
    "web": 1.0,
    "preview": 0.10,
    "medium": 0.50,
}


@router.post("/reconstructions/{reconstruction_id}/splat")
def export_compact_splat(
    reconstruction_id: int, preset: str = "web", db: DBSession = Depends(get_db)
):
    """Export a dependency-free, web-optimized compact ``.splat`` (antimatter15 format).

    SH quantization: higher-order SH is dropped and the DC term becomes a flat
    RGBA byte per gaussian. See ``ply_io.write_splat`` for the exact layout.
    """
    from ..services import ply_io

    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if not rec.splat_path:
        raise HTTPException(status_code=422, detail="Reconstruction has no splat")
    if preset not in _SPLAT_EXPORT_PRESETS:
        raise HTTPException(status_code=422, detail=f"Unknown preset: {preset}")

    cloud = ply_io.read_3dgs_ply(Path(rec.splat_path))
    if cloud.means.shape[0] == 0:
        raise HTTPException(status_code=422, detail="Splat has no Gaussians")

    keep_ratio = _SPLAT_EXPORT_PRESETS[preset]
    if keep_ratio < 1.0:
        order = ply_io.prune_order(cloud.opacities, keep_ratio)
        cloud = ply_io.GaussianCloud(
            means=cloud.means[order],
            sh0=cloud.sh0[order],
            shN=cloud.shN[order],
            opacities=cloud.opacities[order],
            scales=cloud.scales[order],
            quats=cloud.quats[order],
        )

    out_path = Path(get_config().exports_dir) / f"reconstruction_{reconstruction_id}_{preset}.splat"
    ply_io.write_splat(cloud, out_path)
    return {
        "splat_path": str(out_path),
        "point_count": int(cloud.means.shape[0]),
        "byte_size": out_path.stat().st_size,
        "preset": preset,
    }


@router.post("/reconstructions/{reconstruction_id}/share-link")
def create_share_link(reconstruction_id: int, db: DBSession = Depends(get_db)):
    """Create a signed, time-limited public share link for a completed reconstruction."""
    from ..db.models import Reconstruction
    from ..services.share_links import SHARE_LINK_PREFIX, create_share_token

    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(
            status_code=422, detail="Only completed reconstructions can be shared"
        )
    token = create_share_token(rec.id, rec.session_id)
    # The full share link is <prefix><token> — the frontend builds the URL.
    return {
        "share_token": SHARE_LINK_PREFIX + token,
        "reconstruction_id": rec.id,
        "session_id": rec.session_id,
    }


@router.post("/survey-report")
def export_survey_report(
    session_id: int,
    format: str = "json",
    db: DBSession = Depends(get_db),
):
    """Generate a professional survey report for a session.

    Returns structured JSON by default. Pass ``format=html`` for self-contained
    HTML, or ``format=pdf`` for a PDF when WeasyPrint is installed.
    """
    from fastapi.responses import HTMLResponse, Response

    from ..services.survey_report import build_survey_report

    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        report = build_survey_report(session_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if format == "html":
        return HTMLResponse(content=report["html"], status_code=200)
    if format == "pdf":
        try:
            from weasyprint import HTML
        except ImportError as exc:
            raise HTTPException(
                status_code=422,
                detail="PDF export requires the optional weasyprint package",
            ) from exc
        pdf_bytes = HTML(string=report["html"]).write_pdf()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (f'attachment; filename="survey_report_{session_id}.pdf"')
            },
        )
    if format != "json":
        raise HTTPException(status_code=422, detail="format must be json, html, or pdf")
    return report


@router.post("/webodm-package")
def export_webodm_package(
    session_id: int,
    mode: str = "exif",
    include_images: bool = True,
    include_gcp: bool = False,
    db: DBSession = Depends(get_db),
):
    """Build a complete WebODM/OpenDroneMap package with images and options manifest."""
    from ..services.webodm_package import WebodmPackageOptions, build_webodm_package

    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    images = db.query(Image).filter(Image.session_id == session_id, Image.usable == True).all()  # noqa: E712
    try:
        return build_webodm_package(
            Path(get_config().exports_dir) / f"webodm_package_{session_id}_{mode}.zip",
            images,
            WebodmPackageOptions(mode=mode, include_images=include_images, include_gcp=include_gcp),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _get_measurements(reconstruction_id: int, db: DBSession) -> list[Measurement]:
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    return (
        db.query(Measurement)
        .filter(Measurement.reconstruction_id == reconstruction_id)
        .order_by(Measurement.created_at)
        .all()
    )


@router.get("/reconstructions/{reconstruction_id}/measurements.csv")
def export_measurements_csv(reconstruction_id: int, db: DBSession = Depends(get_db)):
    """Export a reconstruction's persisted measurements as a flat CSV, one row per measurement."""
    measurements = _get_measurements(reconstruction_id, db)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "kind", "label", "value", "unit", "created_at", "points"])
    for m in measurements:
        writer.writerow(
            [
                m.id, m.kind, m.label or "", m.value, m.unit or "",
                m.created_at.isoformat(), m.points_json,
            ]
        )
    filename = f"measurements_{reconstruction_id}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _measurement_geometry(kind: str, points: list[dict]) -> dict | None:
    coords = [
        [p.get("lon"), p.get("lat"), p.get("alt") or 0]
        for p in points
        if p.get("lat") is not None and p.get("lon") is not None
    ]
    if len(coords) != len(points) or not coords:
        return None  # any point missing GPS -> geometry can't be built
    if kind == "point":
        return {"type": "Point", "coordinates": coords[0]}
    if kind == "area":
        if len(coords) < 3:
            return None
        return {"type": "Polygon", "coordinates": [[*coords, coords[0]]]}
    if len(coords) < 2:
        return None
    return {"type": "LineString", "coordinates": coords}  # "distance" and any other kind


@router.get("/reconstructions/{reconstruction_id}/measurements.geojson")
def export_measurements_geojson(reconstruction_id: int, db: DBSession = Depends(get_db)):
    """Export a reconstruction's persisted measurements as a GeoJSON FeatureCollection."""
    measurements = _get_measurements(reconstruction_id, db)
    features = []
    for m in measurements:
        geometry = _measurement_geometry(m.kind, json.loads(m.points_json))
        feature = geometry_feature(
            geometry,
            name=m.label or f"measurement-{m.id}",
            properties={
                "id": m.id,
                "label": m.label,
                "value": m.value,
                "unit": m.unit,
                "created_at": m.created_at.isoformat(),
            },
        )
        if feature:
            features.append(feature)
    return JSONResponse(feature_collection(features))
