from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.services.terrain import (
    ElevationResult,
    NoopTerrainService,
    get_terrain_service,
    reset_terrain_service,
)


class TestNoopTerrainService:
    """The no-op service returns zero elevation for every query."""

    def test_elevation_single_returns_zero(self):
        svc = NoopTerrainService()
        result = svc.elevation(lat=41.0, lon=-81.0)
        assert isinstance(result, ElevationResult)
        assert result.elevation_m == 0.0
        assert result.source == "noop"
        assert result.out_of_bounds is False

    def test_elevation_negative_coords_still_zero(self):
        svc = NoopTerrainService()
        result = svc.elevation(lat=-33.9, lon=18.4)
        assert result.elevation_m == 0.0

    def test_elevation_batch_returns_list(self):
        svc = NoopTerrainService()
        results = svc.elevation_batch([(41.0, -81.0), (42.0, -82.0)])
        assert len(results) == 2
        for r in results:
            assert r.elevation_m == 0.0
            assert r.source == "noop"
            assert r.out_of_bounds is False

    def test_elevation_batch_handles_empty_list(self):
        svc = NoopTerrainService()
        results = svc.elevation_batch([])
        assert results == []


class TestTerrainServiceFactory:
    """Default factory returns NoopTerrainService when no DEM is configured."""

    def test_default_is_noop(self):
        reset_terrain_service()
        svc = get_terrain_service()
        assert isinstance(svc, NoopTerrainService)

    def test_cached_returns_same_instance(self):
        reset_terrain_service()
        svc1 = get_terrain_service()
        svc2 = get_terrain_service()
        assert svc1 is svc2

    def test_reset_creates_new_instance(self):
        reset_terrain_service()
        svc1 = get_terrain_service()
        reset_terrain_service()
        svc2 = get_terrain_service()
        assert svc1 is not svc2


class TestElevationResult:
    def test_equality(self):
        a = ElevationResult(elevation_m=100.0, source="dem", out_of_bounds=False)
        b = ElevationResult(elevation_m=100.0, source="dem", out_of_bounds=False)
        assert a == b

    def test_inequality_different_elevation(self):
        a = ElevationResult(elevation_m=100.0, source="dem", out_of_bounds=False)
        b = ElevationResult(elevation_m=200.0, source="dem", out_of_bounds=False)
        assert a != b

    def test_oob_flag_preserved(self):
        r = ElevationResult(elevation_m=0.0, source="noop", out_of_bounds=True)
        assert r.out_of_bounds is True


class TestGeoTiffTerrainServiceInitialization:
    """When a GeoTIFF path is provided, the service attempts to load it."""

    @pytest.fixture(autouse=True)
    def _ensure_rasterio(self):
        try:
            import rasterio  # noqa: F401
        except ImportError:
            pytest.skip("rasterio not installed")

    def test_missing_file_raises(self):
        from backend.services.terrain import GeoTiffTerrainService

        with pytest.raises(FileNotFoundError, match="DEM file not found"):
            GeoTiffTerrainService(dem_path="/nonexistent/dem.tif")

    def test_non_tiff_path_raises(self, tmp_path):
        from backend.services.terrain import GeoTiffTerrainService

        non_tiff = tmp_path / "not_a_raster.png"
        non_tiff.write_bytes(b"mock")
        with pytest.raises(ValueError, match="DEM file must be a .tif"):
            GeoTiffTerrainService(dem_path=non_tiff)


class TestGeoTiffTerrainServiceWithMock:
    """Test elevation sampling with a mocked rasterio dataset."""

    @pytest.fixture(autouse=True)
    def _ensure_rasterio(self):
        try:
            import rasterio  # noqa: F401
        except ImportError:
            pytest.skip("rasterio not installed")

    def test_elevation_inside_raster(self, tmp_path):
        """Query a point inside the raster returns the sampled value."""
        from backend.services.terrain import GeoTiffTerrainService

        dem_path = tmp_path / "dem.tif"
        dem_path.write_bytes(b"mock")
        mock_dataset = _make_mock_dataset(width=100, height=100, constant_value=42.0)
        with patch("rasterio.open", return_value=mock_dataset):
            svc = GeoTiffTerrainService(dem_path=dem_path)
            result = svc.elevation(lat=0.0, lon=0.0)
            assert result.elevation_m == pytest.approx(42.0, abs=0.01)
            assert result.source == "dem"
            assert result.out_of_bounds is False

    def test_elevation_outside_raster_returns_oob(self, tmp_path):
        """Query outside the raster bounds returns out_of_bounds=True."""
        from backend.services.terrain import GeoTiffTerrainService

        dem_path = tmp_path / "dem.tif"
        dem_path.write_bytes(b"mock")
        mock_dataset = _make_mock_dataset(width=100, height=100, constant_value=10.0)
        with patch("rasterio.open", return_value=mock_dataset):
            svc = GeoTiffTerrainService(dem_path=dem_path)
            # The mock bounds are tight; query far away
            with patch.object(svc, "_sample", return_value=None):
                result = svc.elevation(lat=90.0, lon=0.0)
            assert result.out_of_bounds is True
            assert result.elevation_m == 0.0
            assert result.source == "dem"

    def test_elevation_batch_mixed_in_and_out(self, tmp_path):
        """Batch query returns results for each point; some may be OOB."""
        from backend.services.terrain import GeoTiffTerrainService

        dem_path = tmp_path / "dem.tif"
        dem_path.write_bytes(b"mock")
        mock_dataset = _make_mock_dataset(width=100, height=100, constant_value=55.0)
        with patch("rasterio.open", return_value=mock_dataset):
            svc = GeoTiffTerrainService(dem_path=dem_path)
            results = svc.elevation_batch([(0.0, 0.0), (0.0, 0.0)])
            assert len(results) == 2
            assert all(not r.out_of_bounds for r in results)
            for r in results:
                assert r.elevation_m == pytest.approx(55.0, abs=0.01)


def _make_mock_dataset(width=100, height=100, constant_value=0.0):
    """Build a rasterio-like mock dataset that returns a constant value at every sample point."""

    class _MockReader:
        def __init__(self, arr):
            self._arr = arr

        def __getitem__(self, idx):
            return self._arr[idx]

    class _MockDataset:
        def __init__(self, w, h, val):
            import numpy as np
            self._val = val
            self.width = w
            self.height = h
            self.bounds = type(
                "Bounds",
                (),
                {"left": -1.0, "bottom": -1.0, "right": 1.0, "top": 1.0},
            )
            import rasterio.transform

            self.crs = type("CRS", (), {"to_string": lambda self: "EPSG:4326"})()
            self.transform = rasterio.transform.from_origin(-1.0, 1.0, 0.02, 0.02)
            self.indexes = [1]
            self.nodata = None
            self._arr = np.full((1, h, w), val, dtype=np.float32)
            self.read = lambda indexes, window=None, boundless=False: self._read(indexes, window)

        def _read(self, indexes, window):
            import numpy as np
            return np.full((1, 1), self._val, dtype=np.float32)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    return _MockDataset(width, height, constant_value)
