from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ElevationResult:
    """Result of a single elevation query."""

    elevation_m: float
    source: str  # "dem" | "noop"
    out_of_bounds: bool = False


class TerrainService:
    """Abstract terrain elevation service interface."""

    def elevation(self, lat: float, lon: float) -> ElevationResult:
        raise NotImplementedError

    def elevation_batch(
        self, points: Sequence[tuple[float, float]]
    ) -> list[ElevationResult]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# No-op implementation (default when no DEM is configured)
# ---------------------------------------------------------------------------


class NoopTerrainService(TerrainService):
    """Returns zero elevation for every query — used when no DEM is available."""

    def elevation(self, lat: float, lon: float) -> ElevationResult:
        return ElevationResult(elevation_m=0.0, source="noop")

    def elevation_batch(
        self, points: Sequence[tuple[float, float]]
    ) -> list[ElevationResult]:
        return [self.elevation(lat, lon) for lat, lon in points]


# ---------------------------------------------------------------------------
# GeoTIFF-backed implementation (requires rasterio)
# ---------------------------------------------------------------------------

_RASTERIO_AVAILABLE = False
try:
    import rasterio
    import rasterio.transform
    import rasterio.warp

    _RASTERIO_AVAILABLE = True
except ImportError:
    rasterio = None  # type: ignore[assignment]


class GeoTiffTerrainService(TerrainService):
    """Samples elevation from a single-band GeoTIFF DEM via rasterio.

    Points outside the raster bounds return ``out_of_bounds=True`` with
    ``elevation_m=0.0``.
    """

    def __init__(self, dem_path: str | Path) -> None:
        if not _RASTERIO_AVAILABLE:
            raise ImportError(
                "rasterio is required for GeoTIFF terrain support. "
                "Install it with: pip install rasterio"
            )
        dem_path = Path(dem_path)
        if not dem_path.exists():
            raise FileNotFoundError(f"DEM file not found: {dem_path}")
        if dem_path.suffix.lower() not in (".tif", ".tiff"):
            raise ValueError(f"DEM file must be a .tif or .tiff, got: {dem_path}")

        self._dem_path = dem_path
        self._dataset: rasterio.DatasetReader | None = None  # type: ignore[valid-type]

    @property
    def dataset(self) -> rasterio.DatasetReader:  # type: ignore[name-defined]
        if self._dataset is None:
            self._dataset = rasterio.open(str(self._dem_path))
        return self._dataset

    def elevation(self, lat: float, lon: float) -> ElevationResult:
        value = self._sample(lat, lon)
        if value is None:
            return ElevationResult(elevation_m=0.0, source="dem", out_of_bounds=True)
        return ElevationResult(
            elevation_m=float(value), source="dem", out_of_bounds=False
        )

    def elevation_batch(
        self, points: Sequence[tuple[float, float]]
    ) -> list[ElevationResult]:
        return [self.elevation(lat, lon) for lat, lon in points]

    def _sample(self, lat: float, lon: float) -> float | None:
        """Return the raster value at (lat, lon) in the DEM's CRS, or None if OOB."""
        try:
            ds = self.dataset

            # Convert WGS84 → raster CRS if needed
            if ds.crs and ds.crs.to_string() != "EPSG:4326":
                xs, ys = rasterio.warp.transform(
                    "EPSG:4326", ds.crs, [lon], [lat]
                )
                px, py = xs[0], ys[0]
            else:
                px, py = lon, lat

            row, col = rasterio.transform.rowcol(ds.transform, px, py)
            if not (0 <= row < ds.height and 0 <= col < ds.width):
                return None

            window = rasterio.windows.Window(col, row, 1, 1)
            data = ds.read(1, window=window, boundless=False)
            # data shape: (1, 1) -> scalar
            val = data[0, 0]
            if ds.nodata is not None and val == ds.nodata:
                return None
            return float(val)
        except Exception:
            logger.debug("DEM sample failed for (%.6f, %.6f)", lat, lon, exc_info=True)
            return None

    def close(self) -> None:
        if self._dataset is not None:
            self._dataset.close()
            self._dataset = None


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_terrain_service: TerrainService | None = None
_configured_dem_path: str | None = None


def _create_terrain_service() -> TerrainService:
    """Create the appropriate terrain service based on configuration."""
    dem_path = _resolve_dem_path()
    if dem_path is not None:
        try:
            return GeoTiffTerrainService(dem_path=dem_path)
        except Exception as exc:
            logger.warning(
                "Failed to load DEM at %s: %s. Falling back to no-op terrain.",
                dem_path,
                exc,
            )
    return NoopTerrainService()


def _resolve_dem_path() -> str | None:
    """Read DEM path from config.yaml, or the TERRAIN_DEM_PATH env var."""
    import os

    env_path = os.environ.get("TERRAIN_DEM_PATH")
    if env_path:
        return env_path
    return _configured_dem_path


def configure_dem_path(path: str | None) -> None:
    """Set the DEM path and reset the cached terrain service.

    Call early, before any terrain queries.  Pass ``None`` to revert to no-op.
    """
    global _configured_dem_path
    _configured_dem_path = path
    reset_terrain_service()


def get_terrain_service() -> TerrainService:
    """Return the cached terrain service, creating it if necessary."""
    global _terrain_service
    if _terrain_service is None:
        _terrain_service = _create_terrain_service()
    return _terrain_service


def reset_terrain_service() -> None:
    """Clear the cached terrain service so the next call re-creates it."""
    global _terrain_service
    if _terrain_service is not None:
        try:
            _terrain_service.close()  # type: ignore[union-attr]
        except AttributeError:
            pass
        _terrain_service = None
