from __future__ import annotations

import threading
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from backend.core.config import get_config
from backend.db.database import SessionLocal
from backend.db.models import Reconstruction

_ERROR_MSG_MAX_CHARS = 5000
_ortho_jobs: set[int] = set()
_ortho_jobs_lock = threading.Lock()


def _reconstruction_export_dir(reconstruction_id: int) -> Path:
    cfg = get_config()
    return Path(cfg.exports_dir) / str(reconstruction_id)


def _load_geo_transform_for_reconstruction(rec: Reconstruction) -> dict:
    import json as _json

    from backend.services.reconstruction import _LOCAL_FRAME_GEO

    if rec.geo_transform:
        return _json.loads(rec.geo_transform)
    if rec.colmap_dir:
        from backend.services.reconstruction import _extract_geo_transform

        return _extract_geo_transform(Path(rec.colmap_dir)) or _LOCAL_FRAME_GEO
    return dict(_LOCAL_FRAME_GEO)


def _load_points_utm(rec: Reconstruction) -> tuple:
    """Return (Nx3 float64 UTM points, geo dict)."""

    from backend.services.reconstruction import (
        _load_las_positions,
        _load_ply_positions_and_colors,
        _pick_best_submodel,
        _read_colmap_points3d,
        _world_points_to_utm,
    )

    geo = _load_geo_transform_for_reconstruction(rec)

    # Prefer dense point cloud, then splat, then COLMAP sparse
    if rec.pointcloud_path and Path(rec.pointcloud_path).exists():
        points = _load_las_positions(Path(rec.pointcloud_path))
    elif rec.splat_path and Path(rec.splat_path).exists():
        points, _rgb = _load_ply_positions_and_colors(Path(rec.splat_path))
        points = _world_points_to_utm(points, geo)
    elif rec.colmap_dir:
        colmap_dir = Path(rec.colmap_dir)
        points, _rgb = _read_colmap_points3d(
            _pick_best_submodel(colmap_dir / "sparse") / "points3D.txt"
        )
        points = _world_points_to_utm(points, geo)
    else:
        raise RuntimeError(f"Reconstruction {rec.id} has no point source for orthomosaic")

    return points, geo


def _rasterize_to_orthomosaic(
    points_utm, geo: dict, resolution: float = 0.1, channels: int = 3
) -> tuple:
    """Rasterize UTM points to an orthomosaic grid.

    Returns (image: HxWxC uint8, geotransform: tuple, crs_wkt: str | None).
    """
    import math

    import numpy as np

    from backend.services.reconstruction import _utm_epsg

    x = points_utm[:, 0]
    y = points_utm[:, 1]
    if points_utm.shape[1] >= 6:
        colors = points_utm[:, 3:6].copy()
    else:
        colors = np.full((len(points_utm), 3), 200, dtype=np.uint8)

    x_min, x_max = x.min(), x.max()
    y_min, y_max = y.min(), y.max()

    if x_max - x_min < resolution or y_max - y_min < resolution:
        raise RuntimeError(
            "Point cloud extent is smaller than one pixel — cannot produce orthomosaic"
        )

    cols = max(1, int(math.ceil((x_max - x_min) / resolution)))
    rows = max(1, int(math.ceil((y_max - y_min) / resolution)))

    # Accumulate RGB in a float grid, then average
    accum = np.zeros((rows, cols, 3), dtype=np.float64)
    counts = np.zeros((rows, cols), dtype=np.uint32)

    col_idx = ((x - x_min) / resolution).astype(np.int64)
    row_idx = (rows - 1 - ((y - y_min) / resolution)).astype(np.int64)
    row_idx = np.clip(row_idx, 0, rows - 1)
    col_idx = np.clip(col_idx, 0, cols - 1)

    np.add.at(accum, (row_idx, col_idx), colors.astype(np.float64))
    np.add.at(counts, (row_idx, col_idx), 1)

    mask = counts > 0
    image = np.zeros((rows, cols, channels), dtype=np.uint8)
    for c in range(channels):
        image[:, :, c][mask] = (accum[:, :, c][mask] / counts[mask]).astype(np.uint8)

    # geotransform: (x_origin, pixel_width, 0, y_origin, 0, -pixel_height)
    geotransform = (
        float(x_min),
        resolution,
        0.0,
        float(y_max),
        0.0,
        -resolution,
    )

    epsg = _utm_epsg(str(geo.get("utm_zone", "")))
    crs_wkt = None
    if epsg is not None:
        from pyproj import CRS

        crs_wkt = CRS.from_epsg(epsg).to_wkt()

    return image, geotransform, crs_wkt


def _write_geotiff(output_path: Path, image, geotransform: tuple,
                    crs_wkt: str | None) -> Path:
    """Write a GeoTIFF file.

    Requires rasterio; raises ImportError if absent with a clear message.
    """
    try:
        import rasterio  # type: ignore[import]
    except ImportError as err:
        raise ImportError(
            "rasterio is not installed. Orthomosaic export requires rasterio. "
            "Install it with: uv add rasterio"
        ) from err

    rows, cols = image.shape[0], image.shape[1]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(
        str(output_path),
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=image.shape[2],
        dtype=image.dtype,
        crs=crs_wkt,
        transform=rasterio.transform.from_origin(
            geotransform[0], geotransform[3], geotransform[1], abs(geotransform[5])
        ),
    ) as dst:
        for b in range(image.shape[2]):
            dst.write(image[:, :, b], b + 1)

    return output_path


def start_orthomosaic_export(reconstruction_id: int, db: DBSession) -> Reconstruction:
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if rec is None:
        raise ValueError("Reconstruction not found")
    if rec.status != "complete":
        raise ValueError("Reconstruction must be complete before orthomosaic export")

    ortho_status = getattr(rec, "ortho_status", None)
    if ortho_status in {"pending", "running"}:
        raise ValueError(
            f"Orthomosaic export already running for reconstruction {reconstruction_id}"
        )

    with _ortho_jobs_lock:
        if reconstruction_id in _ortho_jobs:
            raise ValueError(
                f"Orthomosaic export already running for reconstruction {reconstruction_id}"
            )
        _ortho_jobs.add(reconstruction_id)

    rec.ortho_status = "pending"
    rec.ortho_error = None
    db.commit()
    db.refresh(rec)

    threading.Thread(target=_run_ortho_job, args=(reconstruction_id,), daemon=True).start()
    return rec


def _run_ortho_job(reconstruction_id: int) -> None:
    db = SessionLocal()
    try:
        rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
        if rec is None:
            return
        rec.ortho_status = "running"
        rec.ortho_error = None
        db.commit()

        points, geo = _load_points_utm(rec)
        image, geotransform, crs_wkt = _rasterize_to_orthomosaic(points, geo)

        output_path = _reconstruction_export_dir(rec.id) / "orthomosaic.tif"
        _write_geotiff(output_path, image, geotransform, crs_wkt)

        rec.ortho_path = str(output_path)
        rec.ortho_status = "complete"
        rec.ortho_error = None
        db.commit()
    except Exception as exc:
        rec_update = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id)
        if rec_update.first() is not None:
            rec_update.update(
                {
                    "ortho_status": "failed",
                    "ortho_error": str(exc)[:_ERROR_MSG_MAX_CHARS],
                }
            )
            db.commit()
    finally:
        db.close()
        with _ortho_jobs_lock:
            _ortho_jobs.discard(reconstruction_id)