from __future__ import annotations

import csv
import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from shapely.geometry import LineString, Point, shape
from sqlalchemy.orm import Session as DBSession
from starlette.background import BackgroundTask

from ..core.config import get_cesium_ion_config, get_config
from ..db.database import get_db
from ..db.models import (
    FlightLog,
    FlightLogPoint,
    Footprint,
    Image,
    Measurement,
    Reconstruction,
    ShareLink,
)
from ..db.models import Session as SessionModel
from ..services.geometry_exports import feature_collection, geometry_feature

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/reconstructions/{reconstruction_id}/usd")
def export_usd_handoff(reconstruction_id: int, db: DBSession = Depends(get_db)):
    """Download a self-contained USDA mesh and georeferencing handoff ZIP."""
    from ..services.reconstruction import _load_geo_transform_for_reconstruction, _safe_export_path
    from ..services.usd_export import write_usda_handoff

    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(
            status_code=422, detail="Reconstruction must be complete before USD export"
        )
    if not rec.mesh_obj_path:
        raise HTTPException(
            status_code=422, detail="USD geometry export requires an existing OBJ mesh"
        )

    exports_dir = Path(get_config().exports_dir)
    try:
        obj_path = _safe_export_path(Path(rec.mesh_obj_path), exports_dir)
        if not obj_path.is_file():
            raise ValueError("OBJ mesh file not found on disk")
        glb_path = None
        if rec.mesh_glb_path:
            glb_path = _safe_export_path(Path(rec.mesh_glb_path), exports_dir)
            if not glb_path.is_file():
                raise ValueError("GLB mesh file not found on disk")
        output_dir = _safe_export_path(exports_dir / str(rec.id), exports_dir)
        usda_path, sidecar_path = write_usda_handoff(
            output_dir,
            obj_path,
            reconstruction_id=rec.id,
            session_id=rec.session_id,
            geo_transform=_load_geo_transform_for_reconstruction(rec),
            source_glb=glb_path,
        )
        bundle_path = output_dir / f"mesh_{rec.id}_usd_handoff.zip"
        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(usda_path, "mesh.usda")
            bundle.write(sidecar_path, "mesh.usd.georef.json")
            bundle.write(obj_path, "source/mesh.obj")
            if glb_path:
                bundle.write(glb_path, "source/mesh.glb")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FileResponse(
        bundle_path,
        media_type="application/zip",
        filename=f"mesh_{rec.id}_usd_handoff.zip",
    )


@router.get("/reconstructions/{reconstruction_id}/geopackage")
def export_geopackage(
    reconstruction_id: int,
    comparison_id: int | None = None,
    db: DBSession = Depends(get_db),
):
    """Download mapped session products as a target-CRS, multi-layer GeoPackage.

    A layer is written only when its persisted source geometry is available. DSM
    and DEM files are recorded as external references, never embedded or created.
    """
    reconstruction = (
        db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    )
    if not reconstruction:
        raise HTTPException(status_code=404, detail="Reconstruction not found")

    try:
        output_path = _write_mapped_products_geopackage(reconstruction, comparison_id, db)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    filename = f"reconstruction_{reconstruction_id}_mapped_products.gpkg"
    download_path = _download_snapshot(output_path)
    return FileResponse(
        download_path,
        media_type="application/geopackage+sqlite3",
        filename=filename,
        background=BackgroundTask(download_path.unlink, missing_ok=True),
    )


@router.post("/reconstructions/{reconstruction_id}/gis-project-files")
def export_gis_project_files(
    reconstruction_id: int,
    comparison_id: int | None = None,
    db: DBSession = Depends(get_db),
):
    """Create QGIS and ArcGIS Pro references for the current mapped-products GeoPackage."""
    reconstruction = (
        db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    )
    if not reconstruction:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    try:
        geopackage = _write_mapped_products_geopackage(reconstruction, comparison_id, db)
        from ..services.gis_project_files import write_gis_project_files

        manifest = write_gis_project_files(geopackage.parent)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"reconstruction_id": reconstruction_id, **manifest}


def _write_mapped_products_geopackage(
    reconstruction: Reconstruction, comparison_id: int | None, db: DBSession
) -> Path:
    from ..services.geopackage_export import write_geopackage
    from ..services.reconstruction import _safe_export_path

    exports_dir = Path(get_config().exports_dir)
    output_dir = _safe_export_path(exports_dir / str(reconstruction.id), exports_dir)
    output_path = output_dir / "mapped_products.gpkg"
    temporary_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    write_geopackage(
        temporary_path,
        _geopackage_layers(reconstruction, comparison_id, db),
        get_config().target_crs,
        _elevation_sidecars(reconstruction),
    )
    os.replace(temporary_path, output_path)
    return output_path


def _download_snapshot(output_path: Path) -> Path:
    """Keep the durable export replaceable while an HTTP client reads its own copy."""
    with tempfile.NamedTemporaryFile(
        prefix=f".{output_path.stem}.download-", suffix=output_path.suffix, dir=output_path.parent,
        delete=False,
    ) as temporary_file:
        download_path = Path(temporary_file.name)
    try:
        shutil.copyfile(output_path, download_path)
    except OSError:
        download_path.unlink(missing_ok=True)
        raise
    return download_path


def _geopackage_layers(
    reconstruction: Reconstruction, comparison_id: int | None, db: DBSession
) -> list[tuple[str, list[dict], str]]:
    session_id = reconstruction.session_id
    layers: list[tuple[str, list[dict], str]] = []
    image_records = []
    for image in db.query(Image).filter(Image.session_id == session_id).order_by(Image.id):
        if image.latitude is None or image.longitude is None:
            continue
        image_records.append({
            "image_id": image.id,
            "filename": image.filename,
            "timestamp": image.timestamp.isoformat() if image.timestamp else None,
            "altitude_m": image.altitude_m,
            "gps_source": image.gps_source,
            "usable": image.usable,
            "geometry": Point(image.longitude, image.latitude),
        })
    layers.append(("image_locations", image_records, "EPSG:4326"))

    footprint_records = []
    footprint_rows = (
        db.query(Footprint, Image)
        .join(Image, Image.id == Footprint.image_id)
        .filter(Image.session_id == session_id)
        .order_by(Image.id)
        .all()
    )
    for footprint, image in footprint_rows:
        geometry = _shape_geometry(footprint.geom_geojson)
        if geometry is None:
            continue
        footprint_records.append({
            "footprint_id": footprint.id,
            "image_id": image.id,
            "filename": image.filename,
            "ground_width_m": footprint.ground_width_m,
            "ground_height_m": footprint.ground_height_m,
            "heading_estimated": footprint.heading_estimated,
            "pitch_oblique": footprint.pitch_oblique,
            "geometry": geometry,
        })
    layers.append(("footprints", footprint_records, "EPSG:4326"))

    flight_records = []
    flight_logs = (
        db.query(FlightLog).filter(FlightLog.session_id == session_id).order_by(FlightLog.id)
    )
    for flight_log in flight_logs:
        points = (
            db.query(FlightLogPoint)
            .filter(FlightLogPoint.flight_log_id == flight_log.id)
            .filter(FlightLogPoint.latitude.is_not(None), FlightLogPoint.longitude.is_not(None))
            .order_by(FlightLogPoint.timestamp, FlightLogPoint.id)
            .all()
        )
        if len(points) < 2:
            continue
        flight_records.append({
            "flight_log_id": flight_log.id,
            "filename": flight_log.filename,
            "point_count": len(points),
            "geometry": LineString([(point.longitude, point.latitude) for point in points]),
        })
    layers.append(("flight_paths", flight_records, "EPSG:4326"))

    coverage_records, coverage_crs = _coverage_gap_records(reconstruction)
    layers.append(("coverage_gaps", coverage_records, coverage_crs))

    measurement_records = []
    measurements = (
        db.query(Measurement)
        .filter(Measurement.reconstruction_id == reconstruction.id)
        .order_by(Measurement.created_at, Measurement.id)
    )
    for measurement in measurements:
        try:
            geometry = _measurement_geometry(measurement.kind, json.loads(measurement.points_json))
        except (json.JSONDecodeError, TypeError):
            geometry = None
        if not geometry:
            continue
        measurement_records.append({
            "measurement_id": measurement.id,
            "kind": measurement.kind,
            "label": measurement.label,
            "value": measurement.value,
            "unit": measurement.unit,
            "created_at": measurement.created_at.isoformat(),
            "geometry": shape(geometry),
        })
    layers.append(("measurements", measurement_records, "EPSG:4326"))

    comparison_records, comparison_crs = _comparison_records(reconstruction, comparison_id, db)
    layers.append(("comparison_change_cells", comparison_records, comparison_crs))
    return layers


def _shape_geometry(raw_geometry: str | None):
    if not raw_geometry:
        return None
    try:
        return shape(json.loads(raw_geometry))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _coverage_gap_records(reconstruction: Reconstruction) -> tuple[list[dict], str]:
    if not reconstruction.coverage_gaps_path:
        return [], "EPSG:4326"
    try:
        import numpy as np

        cells = json.loads(Path(reconstruction.coverage_gaps_path).read_text(encoding="utf-8"))
        from ..services.reconstruction import (
            _load_geo_transform_for_reconstruction,
            _utm_epsg,
            _world_points_to_utm,
        )

        geo_transform = _load_geo_transform_for_reconstruction(reconstruction)
        epsg = _utm_epsg(str(geo_transform.get("utm_zone", "")))
        if epsg is None:
            return [], "EPSG:4326"
        valid_cells = [
            cell for cell in cells
            if all(isinstance(cell.get(key), (int, float)) for key in ("x", "y", "z", "size"))
        ]
        if not valid_cells:
            return [], f"EPSG:{epsg}"
        world_points = np.asarray([[cell["x"], cell["y"], cell["z"]] for cell in valid_cells])
        utm_points = _world_points_to_utm(world_points, geo_transform)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return [], "EPSG:4326"

    records = [
        {
            "reconstruction_id": reconstruction.id,
            "level": cell.get("level"),
            "size_m": cell["size"],
            "geometry": Point(x, y, z),
        }
        for cell, (x, y, z) in zip(valid_cells, utm_points, strict=True)
    ]
    return records, f"EPSG:{epsg}"


def _comparison_records(
    reconstruction: Reconstruction, comparison_id: int | None, db: DBSession
) -> tuple[list[dict], str]:
    if comparison_id is None:
        return [], "EPSG:4326"
    from ..db.models import SessionComparison
    from ..services.reconstruction import _utm_epsg

    comparison = db.query(SessionComparison).filter(SessionComparison.id == comparison_id).first()
    if comparison is None:
        raise ValueError("Comparison not found")
    if reconstruction.id not in {comparison.reconstruction_a_id, comparison.reconstruction_b_id}:
        raise ValueError("Comparison does not include this reconstruction")
    if comparison.status != "complete" or not comparison.diff_path:
        return [], "EPSG:4326"
    try:
        diff = json.loads(Path(comparison.diff_path).read_text(encoding="utf-8"))
        epsg = _utm_epsg(str(diff.get("utm_zone") or ""))
        if epsg is None:
            return [], "EPSG:4326"
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return [], "EPSG:4326"

    records = []
    for change_type in ("new", "removed"):
        for cell in diff.get(change_type, []):
            if not all(isinstance(cell.get(key), (int, float)) for key in ("x", "y", "z", "size")):
                continue
            records.append({
                "comparison_id": comparison.id,
                "change_type": change_type,
                "size_m": cell["size"],
                "geometry": Point(cell["x"], cell["y"], cell["z"]),
            })
    return records, f"EPSG:{epsg}"


def _elevation_sidecars(reconstruction: Reconstruction) -> list[dict]:
    root = Path(get_config().exports_dir) / str(reconstruction.id)
    return [
        {"product": product, "path": str(path)}
        for product in ("dsm", "dem")
        if (path := root / f"{product}.tif").is_file()
    ]


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


@router.post("/reproducibility-manifest")
def export_reproducibility_manifest(workflow: str, artifact_path: str | None = None):
    """Generate a reproducibility manifest for an import/reconstruction/export artifact."""
    from ..services.reproducibility_manifest import build_reproducibility_manifest

    cfg = get_config()
    settings = {
        k: getattr(cfg, k)
        for k in ("target_crs", "default_basemap", "exports_dir", "processed_dir")
    }
    roots = [
        Path(value) for value in (cfg.imports_dir, cfg.processed_dir, cfg.exports_dir, cfg.data_dir)
    ]
    artifacts = [Path(artifact_path)] if artifact_path else []
    try:
        return build_reproducibility_manifest(
            workflow=workflow,
            settings=settings,
            artifacts=artifacts,
            artifact_roots=roots,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/reconstructions/{reconstruction_id}/share-bundle")
def export_reconstruction_share_bundle(reconstruction_id: int, db: DBSession = Depends(get_db)):
    """Create a static share bundle for a completed reconstruction."""
    from ..db.models import Reconstruction
    from ..services.reconstruction import _safe_export_path
    from ..services.share_bundle import build_share_bundle

    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    try:
        exports_dir = Path(get_config().exports_dir)
        bundle_path = _safe_export_path(
            exports_dir / f"reconstruction_{reconstruction_id}_share.zip", exports_dir
        )
        return build_share_bundle(bundle_path, rec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/reconstructions/{reconstruction_id}/cesium-ion")
def upload_reconstruction_to_cesium_ion(reconstruction_id: int, db: DBSession = Depends(get_db)):
    """Publish the existing Cesium-ready 3D Tiles share bundle to Cesium ion."""
    from ..services.cesium_ion import CesiumIonError, upload_tileset
    from ..services.reconstruction import _safe_export_path
    from ..services.share_bundle import build_share_bundle

    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    exports_dir = Path(get_config().exports_dir)
    bundle = _safe_export_path(
        exports_dir / f"reconstruction_{reconstruction_id}_share.zip", exports_dir
    )
    try:
        build_share_bundle(bundle, rec)
        name = f"Reconstruction {reconstruction_id}"
        return upload_tileset(get_cesium_ion_config(), bundle, name)
    except (CesiumIonError, ValueError) as exc:
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


@router.post("/reconstructions/{reconstruction_id}/elevation")
def export_elevation(
    reconstruction_id: int,
    product: str,
    resolution_m: float,
    db: DBSession = Depends(get_db),
):
    """Create a DSM or ground-classified DEM GeoTIFF from a cached LAS point cloud."""
    from ..services.elevation_export import export_elevation_geotiff
    from ..services.reconstruction import _safe_export_path

    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(
            status_code=422, detail="Reconstruction must be complete before elevation export"
        )
    if product not in {"dsm", "dem"}:
        raise HTTPException(status_code=422, detail="product must be dsm or dem")
    if resolution_m <= 0:
        raise HTTPException(status_code=422, detail="resolution_m must be greater than zero")
    if not rec.pointcloud_path:
        raise HTTPException(
            status_code=422,
            detail="LAS point cloud is unavailable; export the reconstruction point cloud first",
        )

    exports_dir = Path(get_config().exports_dir)
    try:
        pointcloud_path = _safe_export_path(Path(rec.pointcloud_path), exports_dir)
        output_path = _safe_export_path(
            exports_dir / str(rec.id) / f"{product}.tif", exports_dir
        )
        if not pointcloud_path.exists():
            raise ValueError("LAS point cloud file not found on disk")
        return export_elevation_geotiff(
            pointcloud_path, output_path, product=product, resolution_m=resolution_m
        )
    except (ValueError, ImportError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/reconstructions/{reconstruction_id}/slope")
def get_slope_overlay(reconstruction_id: int, db: DBSession = Depends(get_db)):
    """Return a cached transparent PNG slope overlay for an existing DSM export."""
    from ..services.reconstruction import _safe_export_path
    from ..services.slope_overlay import build_slope_overlay

    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")

    exports_dir = Path(get_config().exports_dir)
    try:
        export_dir = _safe_export_path(exports_dir / str(rec.id), exports_dir)
        result = build_slope_overlay(export_dir / "dsm.tif", export_dir / "slope.png")
    except (ValueError, ImportError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FileResponse(
        result["path"],
        media_type="image/png",
        headers={"X-Slope-Bounds": json.dumps(result["bounds"], separators=(",", ":"))},
    )


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

    from ..services.reconstruction import _safe_export_path

    exports_dir = Path(get_config().exports_dir)
    # preset is user-supplied and lands in the filename; confine the resolved path to
    # exports_dir (matches _safe_export_http_path / _safe_manifest_artifact_path elsewhere).
    out_path = _safe_export_path(
        exports_dir / f"reconstruction_{reconstruction_id}_{preset}.splat", exports_dir
    )
    ply_io.write_splat(cloud, out_path)
    return {
        "splat_path": str(out_path),
        "point_count": int(cloud.means.shape[0]),
        "byte_size": out_path.stat().st_size,
        "preset": preset,
    }


class CreateShareLinkRequest(BaseModel):
    expires_in_s: int = Field(default=7 * 24 * 3600, ge=60, le=365 * 24 * 3600)
    password: str | None = Field(default=None, max_length=1024)


def _share_link_owner_payload(link: ShareLink) -> dict:
    """Return owner-visible lifecycle state without bearer or password secrets."""
    return {
        "id": link.id,
        "reconstruction_id": link.reconstruction_id,
        "expires_at": link.expires_at.isoformat(),
        "password_protected": bool(link.password_hash),
        "revoked_at": link.revoked_at.isoformat() if link.revoked_at else None,
        "created_at": link.created_at.isoformat(),
    }


@router.post("/reconstructions/{reconstruction_id}/share-link", status_code=201)
def create_share_link(
    reconstruction_id: int,
    body: CreateShareLinkRequest = CreateShareLinkRequest(),
    db: DBSession = Depends(get_db),
):
    """Create a persisted opaque share link; its bearer token is returned only once."""
    from ..services.share_links import (
        SHARE_LINK_PREFIX,
        create_opaque_token,
        hash_password,
        now_utc,
        token_hash,
    )

    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    if rec.status != "complete":
        raise HTTPException(
            status_code=422, detail="Only completed reconstructions can be shared"
        )
    if body.password == "":
        raise HTTPException(status_code=422, detail="Share link password cannot be empty")
    raw_token = create_opaque_token()
    link = ShareLink(
        reconstruction_id=rec.id,
        token_hash=token_hash(raw_token),
        expires_at=now_utc() + timedelta(seconds=body.expires_in_s),
        password_hash=hash_password(body.password) if body.password else None,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return {
        "share_token": SHARE_LINK_PREFIX + raw_token,
        "share_link_id": link.id,
        "reconstruction_id": rec.id,
        "session_id": rec.session_id,
        "expires_at": link.expires_at.isoformat(),
        "password_protected": bool(link.password_hash),
    }


@router.get("/reconstructions/{reconstruction_id}/share-links")
def list_share_links(reconstruction_id: int, db: DBSession = Depends(get_db)):
    """List owner-visible share-link lifecycle state without secrets."""
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconstruction not found")
    links = (
        db.query(ShareLink)
        .filter(ShareLink.reconstruction_id == reconstruction_id)
        .order_by(ShareLink.created_at.desc())
        .all()
    )
    return [_share_link_owner_payload(link) for link in links]


@router.post("/reconstructions/{reconstruction_id}/share-links/{share_link_id}/revoke")
def revoke_share_link(reconstruction_id: int, share_link_id: int, db: DBSession = Depends(get_db)):
    """Revoke a persisted link and every unlock session attached to it."""
    from ..services.share_links import now_utc

    link = (
        db.query(ShareLink)
        .filter(ShareLink.id == share_link_id, ShareLink.reconstruction_id == reconstruction_id)
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")
    if link.revoked_at is None:
        link.revoked_at = now_utc()
        db.commit()
        db.refresh(link)
    return _share_link_owner_payload(link)


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
    from ..services.reconstruction import _safe_export_path
    from ..services.webodm_package import (
        WebodmPackageOptions,
        build_webodm_package,
        odm_options_for,
    )

    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    images = db.query(Image).filter(Image.session_id == session_id, Image.usable == True).all()  # noqa: E712
    try:
        options = WebodmPackageOptions(
            mode=mode, include_images=include_images, include_gcp=include_gcp
        )
        # Validate before the value contributes to an output filename.
        odm_options_for(options.mode, has_gcp=options.include_gcp)
        exports_dir = Path(get_config().exports_dir)
        zip_path = _safe_export_path(
            exports_dir / f"webodm_package_{session_id}_{options.mode}.zip", exports_dir
        )
        return build_webodm_package(
            zip_path,
            images,
            options,
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
