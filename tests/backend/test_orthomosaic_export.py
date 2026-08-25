import json
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

import backend.services.orthomosaic_export as ortho
from backend.db.models import Reconstruction
from backend.db.models import Session as SessionModel


def _db(client):
    from backend.main import app

    return app.state.test_db_session


def _make_rec(db, session, *, status="complete", splat_path=None, pointcloud_path=None,
              colmap_dir=None, geo_transform=None):
    rec = Reconstruction(
        session_id=session.id,
        status=status,
        frames_used=5,
        splat_path=splat_path,
        pointcloud_path=pointcloud_path,
        colmap_dir=colmap_dir,
        geo_transform=geo_transform,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


class TestOrthoExportRoute:

    def test_404_for_missing_reconstruction(self, client):
        resp = client.post("/export/reconstructions/9999/orthomosaic")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_422_no_point_source(self, client, tmp_path):
        db = _db(client)
        session = SessionModel(name="S", folder_path=str(tmp_path))
        db.add(session)
        db.commit()
        db.refresh(session)
        rec = _make_rec(db, session, geo_transform=json.dumps({
            "scale": 1.0, "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "translation": [0, 0, 0], "utm_zone": "32N", "utm_origin": [500000, 5000000],
        }))
        resp = client.post(f"/export/reconstructions/{rec.id}/orthomosaic")
        assert resp.status_code == 422

    def test_404_missing_reconstruction_share_endpoint(self, client):
        resp = client.post("/export/reconstructions/9999/orthomosaic")
        assert resp.status_code == 404

    def test_202_starts_export_with_splat(self, client, monkeypatch, tmp_path):
        db = _db(client)
        session = SessionModel(name="S", folder_path=str(tmp_path))
        db.add(session)
        db.commit()
        db.refresh(session)

        splat = tmp_path / "splat.ply"
        _write_tiny_ply(splat, 10)

        rec = _make_rec(db, session, splat_path=str(splat),
                        geo_transform=json.dumps({
                            "scale": 1.0, "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                            "translation": [0, 0, 0], "utm_zone": "32N",
                            "utm_origin": [500000, 5000000],
                        }))

        with mock.patch.object(ortho, "_run_ortho_job"):
            resp = client.post(f"/export/reconstructions/{rec.id}/orthomosaic")
            assert resp.status_code == 202
            body = resp.json()
            assert body["ortho_status"] == "pending"
            assert body.get("ortho_error") is None

    def test_422_rejects_non_complete(self, client, tmp_path):
        db = _db(client)
        session = SessionModel(name="S", folder_path=str(tmp_path))
        db.add(session)
        db.commit()
        db.refresh(session)
        rec = _make_rec(db, session, status="running_gsplat")
        resp = client.post(f"/export/reconstructions/{rec.id}/orthomosaic")
        assert resp.status_code == 422


class TestOrthoStatusEndpoint:

    def test_ortho_status_returns_null_fields_when_no_export_run(self, client, tmp_path):
        db = _db(client)
        session = SessionModel(name="S", folder_path=str(tmp_path))
        db.add(session)
        db.commit()
        db.refresh(session)
        rec = _make_rec(db, session)
        resp = client.get(f"/reconstruction/{rec.id}/ortho/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == rec.id
        assert body["ortho_status"] is None
        assert body["ortho_error"] is None
        assert body["ortho_path"] is None


class TestOrthoRasterization:

    def test_rasterize_produces_geotransform_and_crs(self):
        np.random.seed(42)
        x = 500000 + np.random.uniform(0, 10, 100)
        y = 5000000 + np.random.uniform(0, 10, 100)
        z = np.random.uniform(100, 110, 100)
        r = np.random.randint(0, 255, 100, dtype=np.uint8)
        g = np.random.randint(0, 255, 100, dtype=np.uint8)
        b = np.random.randint(0, 255, 100, dtype=np.uint8)
        points = np.column_stack([x, y, z, r, g, b]).astype(np.float64)

        geo = {
            "scale": 1.0, "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "translation": [0, 0, 0], "utm_zone": "32N", "utm_origin": [500000, 5000000],
        }
        image, gt, crs_wkt = ortho._rasterize_to_orthomosaic(points, geo, resolution=0.2)
        assert image.ndim == 3
        assert image.shape[2] == 3
        assert image.shape[0] >= 1
        assert image.shape[1] >= 1
        assert len(gt) == 6
        assert gt[1] == 0.2
        assert gt[5] == -0.2
        assert crs_wkt is not None
        assert "WGS" in crs_wkt or "ETRS" in crs_wkt or "32632" in crs_wkt

    def test_rasterize_no_colors_uses_default_gray(self):
        # Spread points over > 1 pixel in both dimensions
        x = np.array([500000, 500002, 500001, 500003], dtype=np.float64)
        y = np.array([5000000, 5000000, 5000001, 5000001], dtype=np.float64)
        z = np.array([100, 100, 100, 100], dtype=np.float64)
        points = np.column_stack([x, y, z])

        geo = {
            "scale": 1.0, "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "translation": [0, 0, 0], "utm_zone": "32N", "utm_origin": [500000, 5000000],
        }
        image, gt, crs_wkt = ortho._rasterize_to_orthomosaic(points, geo, resolution=0.5)
        assert image.shape[2] == 3
        # Every populated pixel is the grey fallback; empty pixels stay black.
        populated = image[image.any(axis=2)]
        assert len(populated) > 0
        assert np.all(populated == 200)

    def test_rasterize_raises_on_too_small_extent(self):
        points = np.array([[500000.0, 5000000.0, 100.0]], dtype=np.float64)
        geo = {
            "scale": 1.0, "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "translation": [0, 0, 0], "utm_zone": "32N", "utm_origin": [500000, 5000000],
        }
        with pytest.raises(RuntimeError, match="smaller than one pixel"):
            ortho._rasterize_to_orthomosaic(points, geo, resolution=0.1)


class TestOrthoJob:

    def test_run_ortho_job_sets_complete_status(self, client, tmp_path):
        """Simulate the full run by mocking SessionLocal to use the test session."""

        db = _db(client)
        session = SessionModel(name="S", folder_path=str(tmp_path))
        db.add(session)
        db.commit()
        db.refresh(session)

        splat = tmp_path / "splat.ply"
        _write_tiny_ply(splat, 30)

        rec = _make_rec(db, session, splat_path=str(splat),
                        geo_transform=json.dumps({
                            "scale": 1.0, "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                            "translation": [0, 0, 0], "utm_zone": "32N",
                            "utm_origin": [500000, 5000000],
                        }))
        rec_id = rec.id

        with (mock.patch.object(ortho, "_write_geotiff") as mock_write,
              mock.patch.object(ortho, "SessionLocal") as mock_session_factory):
            mock_session_factory.return_value = db
            ortho._run_ortho_job(rec_id)

        rec2 = db.query(Reconstruction).get(rec_id)
        assert rec2.ortho_status == "complete"
        assert rec2.ortho_path is not None
        assert "orthomosaic.tif" in rec2.ortho_path
        assert mock_write.called

    def test_run_ortho_job_sets_failed_on_import_error(self, client, tmp_path):
        db = _db(client)
        session = SessionModel(name="S", folder_path=str(tmp_path))
        db.add(session)
        db.commit()
        db.refresh(session)

        splat = tmp_path / "splat.ply"
        _write_tiny_ply(splat, 30)

        rec = _make_rec(db, session, splat_path=str(splat),
                        geo_transform=json.dumps({
                            "scale": 1.0, "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                            "translation": [0, 0, 0], "utm_zone": "32N",
                            "utm_origin": [500000, 5000000],
                        }))
        rec_id = rec.id

        with (mock.patch.object(ortho, "_write_geotiff",
                                side_effect=ImportError("no rasterio")),
              mock.patch.object(ortho, "SessionLocal") as mock_session_factory):
            mock_session_factory.return_value = db
            ortho._run_ortho_job(rec_id)

        rec2 = db.query(Reconstruction).get(rec_id)
        assert rec2.ortho_status == "failed"
        assert "no rasterio" in (rec2.ortho_error or "")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_tiny_ply(path, n_points: int) -> None:
    import numpy as np

    np.random.seed(1)
    path.parent.mkdir(parents=True, exist_ok=True)
    x = 500000 + np.random.uniform(0, 5, n_points)
    y = 5000000 + np.random.uniform(0, 5, n_points)
    z = np.random.uniform(100, 105, n_points)
    r = np.random.randint(0, 255, n_points, dtype=np.uint8)
    g = np.random.randint(0, 255, n_points, dtype=np.uint8)
    b = np.random.randint(0, 255, n_points, dtype=np.uint8)
    nx = np.random.randn(n_points).astype(np.float32)
    ny = np.random.randn(n_points).astype(np.float32)
    nz = np.random.randn(n_points).astype(np.float32)

    with open(path, "w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {n_points}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        f.write("property float nx\nproperty float ny\nproperty float nz\n")
        f.write("end_header\n")
        for i in range(n_points):
            f.write(f"{x[i]:.6f} {y[i]:.6f} {z[i]:.6f} {r[i]} {g[i]} {b[i]} "
                     f"{nx[i]:.6f} {ny[i]:.6f} {nz[i]:.6f}\n")

class TestColourSurvivesTheLoader:
    """#627: every point source discarded RGB, so every orthomosaic was flat grey.

    These go through the real ``_load_points_utm`` rather than hand-building an
    Nx6 array, which is why the pre-existing rasterisation tests missed it.
    """

    GEO = {
        "scale": 1.0, "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "translation": [0, 0, 0], "utm_zone": "32N", "utm_origin": [500000, 5000000],
    }

    def _rec(self, client, tmp_path, **kwargs):
        db = _db(client)
        session = SessionModel(name="S", folder_path=str(tmp_path))
        db.add(session)
        db.commit()
        db.refresh(session)
        return _make_rec(db, session, geo_transform=json.dumps(self.GEO), **kwargs)

    def _assert_multicoloured(self, points):
        assert points.shape[1] == 6, "loader dropped RGB — raster falls back to grey"
        image, _gt, _crs = ortho._rasterize_to_orthomosaic(points, self.GEO, resolution=0.5)
        populated = image[image.any(axis=2)]
        assert len(populated) > 0
        distinct = np.unique(populated, axis=0)
        assert len(distinct) > 1, f"orthomosaic is a flat mask: {distinct}"
        assert not np.all(populated == 200), "every pixel is the grey fallback"

    def test_splat_colour_reaches_the_raster(self, client, tmp_path):
        splat = tmp_path / "splat.ply"
        _write_tiny_ply(splat, 200)
        rec = self._rec(client, tmp_path, splat_path=str(splat))

        points, _geo = ortho._load_points_utm(rec)
        self._assert_multicoloured(points)

    def test_colmap_colour_reaches_the_raster(self, client, tmp_path):
        sparse = tmp_path / "colmap" / "sparse" / "0"
        sparse.mkdir(parents=True)
        rng = np.random.default_rng(7)
        lines = ["# POINT3D_ID X Y Z R G B ERROR TRACK[]"]
        for i in range(200):
            x, y = rng.uniform(0, 5), rng.uniform(0, 5)
            r, g, b = rng.integers(0, 256, 3)
            lines.append(f"{i} {x:.6f} {y:.6f} {rng.uniform(0, 2):.6f} {r} {g} {b} 0.5")
        (sparse / "points3D.txt").write_text("\n".join(lines) + "\n")
        rec = self._rec(client, tmp_path, colmap_dir=str(tmp_path / "colmap"))

        points, _geo = ortho._load_points_utm(rec)
        self._assert_multicoloured(points)

    def test_las_colour_reaches_the_raster(self, client, tmp_path):
        pytest.importorskip("laspy")
        import laspy

        rng = np.random.default_rng(3)
        header = laspy.LasHeader(point_format=3, version="1.4")
        header.scales = np.array([0.001, 0.001, 0.001])
        header.offsets = np.array([500000.0, 5000000.0, 0.0])
        cloud = laspy.LasData(header)
        cloud.x = 500000 + rng.uniform(0, 5, 200)
        cloud.y = 5000000 + rng.uniform(0, 5, 200)
        cloud.z = rng.uniform(0, 2, 200)
        # 16-bit, the way our own LAS export writes it (8-bit scaled by 257).
        for channel in ("red", "green", "blue"):
            setattr(cloud, channel, rng.integers(0, 256, 200).astype(np.uint16) * 257)
        path = tmp_path / "cloud.las"
        cloud.write(path)
        rec = self._rec(client, tmp_path, pointcloud_path=str(path))

        points, _geo = ortho._load_points_utm(rec)
        self._assert_multicoloured(points)

    def test_las_without_colour_still_falls_back_to_grey(self, client, tmp_path):
        pytest.importorskip("laspy")
        import laspy

        # Point format 0 has no colour dimensions at all.
        header = laspy.LasHeader(point_format=0, version="1.2")
        header.scales = np.array([0.001, 0.001, 0.001])
        header.offsets = np.array([500000.0, 5000000.0, 0.0])
        cloud = laspy.LasData(header)
        cloud.x = [500000.0, 500002.0, 500001.0, 500003.0]
        cloud.y = [5000000.0, 5000000.0, 5000001.0, 5000001.0]
        cloud.z = [1.0, 1.0, 1.0, 1.0]
        path = tmp_path / "nocolour.las"
        cloud.write(path)
        rec = self._rec(client, tmp_path, pointcloud_path=str(path))

        points, _geo = ortho._load_points_utm(rec)
        assert points.shape[1] == 3
        image, _gt, _crs = ortho._rasterize_to_orthomosaic(points, self.GEO, resolution=0.5)
        populated = image[image.any(axis=2)]
        assert len(populated) > 0
        assert np.all(populated == 200)

    def test_las_with_unpopulated_colour_block_falls_back_to_grey(self, client, tmp_path):
        """Format 3 allocates RGB even when the producer never writes it."""
        pytest.importorskip("laspy")
        import laspy

        header = laspy.LasHeader(point_format=3, version="1.4")
        header.scales = np.array([0.001, 0.001, 0.001])
        header.offsets = np.array([500000.0, 5000000.0, 0.0])
        cloud = laspy.LasData(header)
        cloud.x = [500000.0, 500002.0, 500001.0, 500003.0]
        cloud.y = [5000000.0, 5000000.0, 5000001.0, 5000001.0]
        cloud.z = [1.0, 1.0, 1.0, 1.0]
        path = tmp_path / "zerocolour.las"
        cloud.write(path)
        rec = self._rec(client, tmp_path, pointcloud_path=str(path))

        points, _geo = ortho._load_points_utm(rec)
        assert points.shape[1] == 3

    def test_change_detection_loader_still_gets_xyz_only(self, client, tmp_path):
        """_load_las_positions' other caller voxelises Nx3; Nx6 would corrupt it."""
        pytest.importorskip("laspy")
        import laspy

        from backend.services.reconstruction import (
            _load_reconstruction_points_utm,
            _voxelize_points,
        )

        header = laspy.LasHeader(point_format=3, version="1.4")
        header.scales = np.array([0.001, 0.001, 0.001])
        header.offsets = np.array([500000.0, 5000000.0, 0.0])
        cloud = laspy.LasData(header)
        cloud.x = [500000.0, 500002.0]
        cloud.y = [5000000.0, 5000000.0]
        cloud.z = [1.0, 1.0]
        cloud.red, cloud.green, cloud.blue = [100, 200], [110, 210], [120, 220]
        path = tmp_path / "coloured.las"
        cloud.write(path)
        rec = self._rec(client, tmp_path, pointcloud_path=str(path))

        points, _geo = _load_reconstruction_points_utm(rec)
        assert points.shape[1] == 3
        assert all(len(voxel) == 3 for voxel in _voxelize_points(points, 0.5))


class TestRasterBudget:
    """The raster must stay bounded regardless of point-cloud extent.

    A completed 73-frame reconstruction asked for a 26246x35183 grid and died
    with "Unable to allocate 20.6 GiB". #499 added exactly this guard to the
    elevation export and the orthomosaic path was missed.
    """

    def _cloud(self, np, n=4000, spread=40.0, outliers=0):
        rng = np.random.default_rng(0)
        pts = np.zeros((n + outliers, 6))
        pts[:n, 0] = rng.uniform(500000, 500000 + spread, n)
        pts[:n, 1] = rng.uniform(4550000, 4550000 + spread, n)
        pts[:n, 3:6] = 128
        if outliers:
            # A few floaters kilometres away, as splat training produces.
            pts[n:, 0] = rng.uniform(500000 - 3000, 500000 + 3000, outliers)
            pts[n:, 1] = rng.uniform(4550000 - 3000, 4550000 + 3000, outliers)
            pts[n:, 3:6] = 128
        return pts

    def test_wide_cloud_coarsens_instead_of_exhausting_memory(self):
        np = pytest.importorskip("numpy")
        from backend.services import orthomosaic_export as oe

        # 8 km across at 0.1 m would be 80000^2 = 6.4e9 px.
        pts = self._cloud(np, n=20000, spread=8000.0)
        image, _gt, _crs = oe._rasterize_to_orthomosaic(pts, {"utm_zone": "17N"}, resolution=0.1)

        rows, cols = image.shape[:2]
        assert rows * cols <= oe.MAX_RASTER_PIXELS, f"{rows}x{cols} exceeds the budget"
        assert rows > 0 and cols > 0

    def test_outliers_do_not_define_the_extent(self):
        np = pytest.importorskip("numpy")
        from backend.services import orthomosaic_export as oe

        tight = self._cloud(np, n=4000, spread=40.0)
        with_floaters = self._cloud(np, n=4000, spread=40.0, outliers=20)

        a, _, _ = oe._rasterize_to_orthomosaic(tight, {"utm_zone": "17N"}, resolution=0.1)
        b, _, _ = oe._rasterize_to_orthomosaic(with_floaters, {"utm_zone": "17N"}, resolution=0.1)

        # Without percentile clipping the floaters stretch the raster ~150x per axis.
        assert b.shape[0] < a.shape[0] * 3
        assert b.shape[1] < a.shape[1] * 3


class TestAtomicGeoTiffWrite:
    """#628: the writer opened the final path directly, so a crash mid-write
    destroyed the last good export."""

    _GEOTRANSFORM = (0.0, 1.0, 0.0, 10.0, 0.0, -1.0)

    @staticmethod
    def _install_fake_rasterio(monkeypatch, *, fail: bool):
        import sys
        import types

        class _Dataset:
            def __init__(self, path):
                self.path = Path(path)

            def __enter__(self):
                self.path.write_bytes(b"PARTIAL")
                return self

            def __exit__(self, *exc):
                return False

            def write(self, band, index):
                if fail:
                    raise OSError("no space left on device")
                self.path.write_bytes(b"NEW RASTER")

        module = types.ModuleType("rasterio")
        module.open = lambda path, mode, **kwargs: _Dataset(path)
        module.transform = types.SimpleNamespace(from_origin=lambda *args: object())
        monkeypatch.setitem(sys.modules, "rasterio", module)

    def _image(self):
        return np.zeros((2, 2, 3), dtype=np.uint8)

    def test_failed_write_leaves_previous_raster_intact(self, monkeypatch, tmp_path):
        output = tmp_path / "orthomosaic.tif"
        output.write_bytes(b"GOOD RASTER")
        self._install_fake_rasterio(monkeypatch, fail=True)

        with pytest.raises(OSError):
            ortho._write_geotiff(output, self._image(), self._GEOTRANSFORM, None)

        assert output.read_bytes() == b"GOOD RASTER"
        assert list(tmp_path.glob("*tmp*")) == []

    def test_successful_write_replaces_the_previous_raster(self, monkeypatch, tmp_path):
        output = tmp_path / "orthomosaic.tif"
        output.write_bytes(b"GOOD RASTER")
        self._install_fake_rasterio(monkeypatch, fail=False)

        assert ortho._write_geotiff(output, self._image(), self._GEOTRANSFORM, None) == output
        assert output.read_bytes() == b"NEW RASTER"
        assert list(tmp_path.glob("*tmp*")) == []


class TestDanglingOrthoStatusReaper:
    """#628: ``ortho_status`` was committed as running and never reset, so a
    crash wedged the reconstruction at 422 forever."""

    def test_dangling_running_is_reaped_and_export_retryable(self, client, tmp_path):
        db = _db(client)
        session = SessionModel(name="S", folder_path=str(tmp_path))
        db.add(session)
        db.commit()
        db.refresh(session)

        splat = tmp_path / "splat.ply"
        _write_tiny_ply(splat, 10)
        rec = _make_rec(db, session, splat_path=str(splat))
        rec.ortho_status = "running"
        db.commit()
        rec_id = rec.id

        # Wedged: every retry is rejected while the stale status stands.
        assert client.post(f"/export/reconstructions/{rec_id}/orthomosaic").status_code == 422

        with mock.patch.object(ortho, "SessionLocal", return_value=db):
            assert ortho.reset_dangling_ortho_status() == 1

        reaped = db.query(Reconstruction).get(rec_id)
        assert reaped.ortho_status == "failed"
        assert "restart" in (reaped.ortho_error or "").lower()

        with mock.patch.object(ortho, "_run_ortho_job"):
            resp = client.post(f"/export/reconstructions/{rec_id}/orthomosaic")
        assert resp.status_code == 202
        assert resp.json()["ortho_status"] == "pending"

    def test_pending_is_reaped_and_terminal_rows_are_untouched(self, client, tmp_path):
        db = _db(client)
        session = SessionModel(name="S", folder_path=str(tmp_path))
        db.add(session)
        db.commit()
        db.refresh(session)

        pending = _make_rec(db, session)
        pending.ortho_status = "pending"
        done = _make_rec(db, session)
        done.ortho_status = "complete"
        db.commit()
        pending_id, done_id = pending.id, done.id

        with mock.patch.object(ortho, "SessionLocal", return_value=db):
            assert ortho.reset_dangling_ortho_status() == 1

        assert db.query(Reconstruction).get(pending_id).ortho_status == "failed"
        assert db.query(Reconstruction).get(done_id).ortho_status == "complete"
