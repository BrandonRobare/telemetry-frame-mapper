from __future__ import annotations

import os
import threading
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from backend.core.config import get_config
from backend.db.database import SessionLocal
from backend.db.models import Reconstruction

_ERROR_MSG_MAX_CHARS = 5000
_ortho_jobs: set[int] = set()
_ortho_jobs_lock = threading.Lock()

# Matches elevation_export.MAX_RASTER_PIXELS. Bounds the accumulator so an
# unusually wide point cloud coarsens the output instead of exhausting memory.
MAX_RASTER_PIXELS = 100_000_000
# Percentile clip applied to each axis before deriving the raster extent.
EXTENT_PERCENTILE = 0.5


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
    """Return (Nx6 float64 UTM points + RGB, geo dict).

    Falls back to Nx3 only when the source carries no colour, which
    ``_rasterize_to_orthomosaic`` renders as flat grey.
    """

    import numpy as np

    from backend.services.reconstruction import (
        _load_las_positions_and_colors,
        _load_ply_positions_and_colors,
        _pick_best_submodel,
        _read_colmap_points3d,
        _world_points_to_utm,
    )

    geo = _load_geo_transform_for_reconstruction(rec)

    # Prefer dense point cloud, then splat, then COLMAP sparse
    if rec.pointcloud_path and Path(rec.pointcloud_path).exists():
        points, rgb = _load_las_positions_and_colors(Path(rec.pointcloud_path))
    elif rec.splat_path and Path(rec.splat_path).exists():
        points, rgb = _load_ply_positions_and_colors(Path(rec.splat_path))
        points = _world_points_to_utm(points, geo)
    elif rec.colmap_dir:
        colmap_dir = Path(rec.colmap_dir)
        points, rgb = _read_colmap_points3d(
            _pick_best_submodel(colmap_dir / "sparse") / "points3D.txt"
        )
        points = _world_points_to_utm(points, geo)
    else:
        raise RuntimeError(f"Reconstruction {rec.id} has no point source for orthomosaic")

    # Appended after the UTM transform, which multiplies by a 3x3 rotation and
    # would reject a 6-column array.
    if rgb is not None:
        points = np.column_stack([points, rgb])

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

    # Splat training leaves a scatter of low-opacity floaters far outside the
    # surveyed area. Taking the raw min/max lets a handful of them define the
    # raster extent, which both explodes the pixel count and renders the actual
    # subject as a speck in a mostly-empty image. Clip to the bulk of the cloud.
    bounds = [EXTENT_PERCENTILE, 100 - EXTENT_PERCENTILE]
    x_min, x_max = (float(v) for v in np.percentile(x, bounds))
    y_min, y_max = (float(v) for v in np.percentile(y, bounds))

    if x_max - x_min < resolution or y_max - y_min < resolution:
        raise RuntimeError(
            "Point cloud extent is smaller than one pixel — cannot produce orthomosaic"
        )

    # Coarsen rather than fail: this runs as a background job with no
    # user-supplied resolution, so "retry at a coarser resolution" would be a
    # dead end. Without this an ordinary survey could ask for a 26k x 35k grid
    # and abort with "Unable to allocate 20.6 GiB".
    span_x, span_y = x_max - x_min, y_max - y_min
    requested_px = math.ceil(span_x / resolution) * math.ceil(span_y / resolution)
    if requested_px > MAX_RASTER_PIXELS:
        # Aim slightly under the cap: each axis is rounded up independently
        # afterwards, so landing exactly on the budget would overshoot it.
        budget = MAX_RASTER_PIXELS * 0.99
        resolution *= math.sqrt(requested_px / budget)

    cols = max(1, int(math.ceil(span_x / resolution)))
    rows = max(1, int(math.ceil(span_y / resolution)))

    # float32 halves the accumulator versus float64. Colour sums stay exact up to
    # ~65k points per pixel (255 * N within float32's 24-bit mantissa); beyond
    # that the averaged 8-bit output rounds by at most a unit or two.
    accum = np.zeros((rows, cols, 3), dtype=np.float32)
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
    # Write beside the target and rename on success: an interrupted write must
    # not destroy the last good export (#628).
    temporary_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")

    try:
        with rasterio.open(
            str(temporary_path),
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
        os.replace(temporary_path, output_path)
    except BaseException:
        # Covers the rename too: on Windows it fails while a download holds the
        # target open (#653), which must not leave a stray half-export behind.
        temporary_path.unlink(missing_ok=True)
        raise

    return output_path


def reset_dangling_ortho_status() -> int:
    """Fail orthomosaic exports left live by a previous process (startup only).

    ``ortho_status`` is committed before the write and only ever cleared by the
    worker thread, which dies with its process.  A ``pending``/``running`` row
    surviving a restart is therefore dead, and the "already running" guard in
    ``start_orthomosaic_export`` would reject every retry forever (#628).
    Returns the number of rows reaped.
    """
    db = SessionLocal()
    try:
        reaped = (
            db.query(Reconstruction)
            .filter(Reconstruction.ortho_status.in_(["pending", "running"]))
            .update(
                {
                    "ortho_status": "failed",
                    "ortho_error": (
                        "Server restart — orthomosaic export was orphaned by a "
                        "previous shutdown"
                    ),
                },
                synchronize_session=False,
            )
        )
        db.commit()
        return reaped
    finally:
        db.close()


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