from __future__ import annotations

import math
from pathlib import Path

NODATA = -9999.0
MIN_RESOLUTION_M = 0.02
MAX_RASTER_PIXELS = 100_000_000


class DemUnavailableError(ValueError):
    """Raised when a point cloud cannot truthfully produce a bare-earth DEM."""


def export_elevation_geotiff(
    pointcloud_path: Path,
    output_path: Path,
    *,
    product: str,
    resolution_m: float,
) -> dict:
    """Rasterize LAS/LAZ elevations into a DSM or ground-classified DEM GeoTIFF."""
    if product not in {"dsm", "dem"}:
        raise ValueError("product must be dsm or dem")
    if not math.isfinite(resolution_m) or resolution_m <= 0:
        raise ValueError("resolution_m must be a finite value greater than zero")

    try:
        import laspy
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin
    except ImportError as exc:
        raise ImportError(
            "Elevation export requires optional laspy and rasterio dependencies. "
            "Install them with: pip install '.[reconstruction]'"
        ) from exc

    cloud = laspy.read(pointcloud_path)
    crs = cloud.header.parse_crs()
    if crs is None:
        raise ValueError("Point cloud has no CRS; cannot produce a georeferenced elevation raster")

    x = np.asarray(cloud.x, dtype=np.float64)
    y = np.asarray(cloud.y, dtype=np.float64)
    z = np.asarray(cloud.z, dtype=np.float64)
    if product == "dem":
        ground = np.asarray(cloud.classification) == 2
        if not ground.any():
            raise DemUnavailableError(
                "DEM is unavailable: the point cloud has no ASPRS ground (class 2) labels; "
                "a DSM remains available."
            )
        x, y, z = x[ground], y[ground], z[ground]
    if not len(x):
        raise ValueError("Point cloud has no points for elevation export")

    x_min, x_max = float(x.min()), float(x.max())
    y_min, y_max = float(y.min()), float(y.max())
    width = max(1, int(math.floor((x_max - x_min) / resolution_m + 1e-9)) + 1)
    height = max(1, int(math.floor((y_max - y_min) / resolution_m + 1e-9)) + 1)
    if resolution_m < MIN_RESOLUTION_M:
        raise ValueError(
            f"resolution_m must be at least {MIN_RESOLUTION_M} m; got {resolution_m}"
        )
    if width * height > MAX_RASTER_PIXELS:
        raise ValueError(
            f"Requested raster is {width}x{height} = {width * height} px, which exceeds "
            f"the {MAX_RASTER_PIXELS} px limit; use a coarser resolution_m"
        )
    columns = np.clip(((x - x_min) / resolution_m).astype(np.int64), 0, width - 1)
    rows = np.clip(((y_max - y) / resolution_m).astype(np.int64), 0, height - 1)

    values = np.full((height, width), NODATA, dtype=np.float32)
    if product == "dsm":
        np.maximum.at(values, (rows, columns), z.astype(np.float32))
    else:
        values.fill(np.inf)
        np.minimum.at(values, (rows, columns), z.astype(np.float32))
        values[~np.isfinite(values)] = NODATA

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs=crs,
        transform=from_origin(x_min, y_max, resolution_m, resolution_m),
        nodata=NODATA,
        compress="deflate",
    ) as dataset:
        dataset.write(values, 1)

    return {
        "path": output_path,
        "product": product,
        "resolution_m": resolution_m,
        "nodata": NODATA,
        "crs": crs.to_string(),
        "width": width,
        "height": height,
    }
