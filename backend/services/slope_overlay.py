from __future__ import annotations

import math
from pathlib import Path


def _colorize_slope(slope, valid):
    """Return an RGBA slope ramp, with invalid DSM cells fully transparent."""
    import numpy as np

    # Green (flat) → amber (15°) → red (30° and steeper).
    ramp = np.clip(slope / 30.0, 0.0, 1.0)
    lower = ramp <= 0.5
    first = (ramp * 2.0)[..., None]
    second = ((ramp - 0.5) * 2.0)[..., None]
    green = np.array([48, 126, 76], dtype=np.float64)
    amber = np.array([239, 181, 59], dtype=np.float64)
    red = np.array([201, 73, 53], dtype=np.float64)
    rgb = np.where(
        lower[..., None], green + (amber - green) * first, amber + (red - amber) * second
    )

    rgba = np.zeros((*slope.shape, 4), dtype=np.uint8)
    rgba[..., :3] = np.nan_to_num(rgb, nan=0.0).clip(0, 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 255, 0)
    return rgba


def build_slope_overlay(dsm_path: Path, output_path: Path) -> dict:
    """Create (or reuse) a transparent PNG slope overlay for an existing DSM GeoTIFF."""
    if not dsm_path.is_file():
        raise ValueError(
            "DSM is unavailable; export a DSM GeoTIFF before enabling the slope overlay"
        )

    try:
        import numpy as np
        import rasterio
        from rasterio.warp import transform_bounds
    except ImportError as exc:
        raise ImportError(
            "Slope overlay requires rasterio and numpy. Install the reconstruction dependencies."
        ) from exc

    with rasterio.open(dsm_path) as dataset:
        if dataset.count < 1 or dataset.crs is None:
            raise ValueError("DSM must have an elevation band and CRS for a slope overlay")
        west, south, east, north = transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds)
        bounds = [[south, west], [north, east]]
        if output_path.is_file() and output_path.stat().st_mtime >= dsm_path.stat().st_mtime:
            return {"path": output_path, "bounds": bounds, "cached": True}

        elevation = dataset.read(1, masked=True).filled(np.nan).astype(np.float64)
        valid = np.isfinite(elevation)
        if elevation.shape[0] < 2 or elevation.shape[1] < 2:
            raise ValueError("DSM is too small to calculate slope")
        x_resolution = abs(dataset.transform.a)
        y_resolution = abs(dataset.transform.e)
        if (
            not math.isfinite(x_resolution)
            or not math.isfinite(y_resolution)
            or not x_resolution
            or not y_resolution
        ):
            raise ValueError("DSM has invalid pixel resolution")

        # NaNs deliberately propagate to neighbours: an edge next to unknown
        # elevation is not a trustworthy slope, so it stays transparent.
        gradient_y, gradient_x = np.gradient(elevation, y_resolution, x_resolution)
        slope = np.degrees(np.arctan(np.hypot(gradient_x, gradient_y)))
        valid &= np.isfinite(slope)
        if not valid.any():
            raise ValueError("DSM has no contiguous elevation cells for a slope overlay")
        rgba = _colorize_slope(slope, valid)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(".tmp.png")
    with rasterio.open(
        temporary_path,
        "w",
        driver="PNG",
        height=rgba.shape[0],
        width=rgba.shape[1],
        count=4,
        dtype="uint8",
    ) as overlay:
        for band in range(4):
            overlay.write(rgba[:, :, band], band + 1)
    temporary_path.replace(output_path)
    return {"path": output_path, "bounds": bounds, "cached": False}
