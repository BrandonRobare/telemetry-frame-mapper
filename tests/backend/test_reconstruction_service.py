from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.db.models import Reconstruction, ReconstructionFrame
from backend.db.models import Session as SessionModel


def _make_session(db):
    s = SessionModel(name="Test", folder_path="/tmp/t", photo_count=0, usable_count=0)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_new_model_columns_exist(setup_test_db):
    from backend.db.database import get_db
    from backend.db.models import Image
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    s = _make_session(db)

    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=0)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    # New Reconstruction columns
    assert hasattr(rec, "training_metrics")
    assert rec.training_metrics is None
    assert hasattr(rec, "coverage_gaps_path")
    assert rec.coverage_gaps_path is None

    img = Image(session_id=s.id, filename="f.jpg", filepath="/f.jpg", usable=True)
    db.add(img)
    db.commit()
    db.refresh(img)

    frame = ReconstructionFrame(reconstruction_id=rec.id, image_id=img.id)
    db.add(frame)
    db.commit()
    db.refresh(frame)

    # New ReconstructionFrame column
    assert hasattr(frame, "colmap_error_px")
    assert frame.colmap_error_px is None

    frame.colmap_error_px = 1.23
    rec.training_metrics = '[{"iter":1000,"psnr":18.2,"ssim":0.71}]'
    rec.coverage_gaps_path = "/tmp/gaps.json"
    db.commit()
    db.refresh(frame)
    db.refresh(rec)

    assert frame.colmap_error_px == pytest.approx(1.23)
    assert '"iter"' in rec.training_metrics
    assert rec.coverage_gaps_path == "/tmp/gaps.json"


def test_reconstruction_model_fields(setup_test_db):
    from backend.db.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())

    s = _make_session(db)
    rec = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="pending",
        frames_used=10,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    assert rec.id is not None
    assert rec.status == "pending"
    assert rec.preset == "quick"
    assert rec.frames_used == 10
    assert rec.progress_pct == 0.0
    assert rec.started_at is not None
    assert rec.completed_at is None
    assert rec.error_msg is None


def test_reconstruction_frame_join(setup_test_db):
    from backend.db.database import get_db
    from backend.db.models import Image
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())

    s = _make_session(db)
    img = Image(session_id=s.id, filename="f.jpg", filepath="/f.jpg", usable=True)
    db.add(img)
    db.commit()
    db.refresh(img)

    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    rf = ReconstructionFrame(reconstruction_id=rec.id, image_id=img.id)
    db.add(rf)
    db.commit()

    db.refresh(rec)
    assert len(rec.frames) == 1
    assert rec.frames[0].image_id == img.id


def test_session_reconstructions_relationship(setup_test_db):
    from backend.db.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())

    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="full", status="pending", frames_used=5)
    db.add(rec)
    db.commit()
    db.refresh(s)

    assert len(s.reconstructions) == 1
    assert s.reconstructions[0].preset == "full"


# ---------------------------------------------------------------------------
# Workspace writer tests
# ---------------------------------------------------------------------------

def _make_mock_image(filename="frame_00001.jpg", filepath=None, lat=35.0, lon=-80.0, alt=100.0):
    img = MagicMock()
    img.filename = filename
    img.filepath = filepath or f"/tmp/{filename}"
    img.latitude = lat
    img.longitude = lon
    img.altitude_m = alt
    return img


def test_workspace_creates_images_dir():
    from backend.services.reconstruction import _write_colmap_workspace
    with tempfile.TemporaryDirectory() as tmp:
        colmap_dir = Path(tmp)
        _write_colmap_workspace(colmap_dir, [])
        assert (colmap_dir / "images").is_dir()


def test_workspace_creates_sparse_dir():
    from backend.services.reconstruction import _write_colmap_workspace
    with tempfile.TemporaryDirectory() as tmp:
        colmap_dir = Path(tmp)
        _write_colmap_workspace(colmap_dir, [])
        assert (colmap_dir / "sparse").is_dir()


def test_workspace_cameras_txt_pinhole_format():
    from backend.services.reconstruction import _write_colmap_workspace
    with tempfile.TemporaryDirectory() as tmp:
        colmap_dir = Path(tmp)
        img = _make_mock_image()
        Path(img.filepath).touch()
        _write_colmap_workspace(colmap_dir, [img])
        cameras_txt = colmap_dir / "cameras.txt"
        assert cameras_txt.exists()
        lines = [
            ln for ln in cameras_txt.read_text().splitlines()
            if not ln.startswith("#") and ln.strip()
        ]
        assert len(lines) == 1
        parts = lines[0].split()
        assert parts[0] == "1"
        assert parts[1] == "PINHOLE"
        assert int(parts[2]) == 4000
        assert int(parts[3]) == 3000


def test_workspace_cameras_txt_focal_length():
    from backend.services.reconstruction import _write_colmap_workspace
    with tempfile.TemporaryDirectory() as tmp:
        colmap_dir = Path(tmp)
        img = _make_mock_image()
        Path(img.filepath).touch()
        _write_colmap_workspace(colmap_dir, [img])
        line = [
            ln for ln in (colmap_dir / "cameras.txt").read_text().splitlines()
            if not ln.startswith("#") and ln.strip()
        ][0]
        parts = line.split()
        f_px = float(parts[4])
        expected = (4000 / 2) / math.tan(math.radians(83 / 2))
        assert abs(f_px - expected) < 1.0


def test_workspace_image_copied_or_linked():
    from backend.services.reconstruction import _write_colmap_workspace
    with tempfile.TemporaryDirectory() as tmp:
        colmap_dir = Path(tmp)
        src = Path(tmp) / "source.jpg"
        src.write_bytes(b"fake jpg")
        img = _make_mock_image(filename="source.jpg", filepath=str(src))
        _write_colmap_workspace(colmap_dir, [img])
        dest = colmap_dir / "images" / "source.jpg"
        assert dest.exists()


# ---------------------------------------------------------------------------
# Target area filter tests
# ---------------------------------------------------------------------------


def _make_square_geojson(min_lon, min_lat, max_lon, max_lat) -> str:
    return json.dumps({
        "type": "Polygon",
        "coordinates": [[
            [min_lon, min_lat],
            [max_lon, min_lat],
            [max_lon, max_lat],
            [min_lon, max_lat],
            [min_lon, min_lat],
        ]],
    })


def test_filter_images_inside_polygon():
    from backend.services.reconstruction import _filter_images_to_target_area
    geojson = _make_square_geojson(-80.1, 34.9, -79.9, 35.1)
    inside = _make_mock_image(lat=35.0, lon=-80.0)
    outside = _make_mock_image(lat=36.0, lon=-81.0)
    result = _filter_images_to_target_area([inside, outside], geojson)
    assert len(result) == 1
    assert result[0].latitude == 35.0


def test_filter_images_excludes_no_gps():
    from backend.services.reconstruction import _filter_images_to_target_area
    geojson = _make_square_geojson(-80.1, 34.9, -79.9, 35.1)
    img = _make_mock_image()
    img.latitude = None
    img.longitude = None
    result = _filter_images_to_target_area([img], geojson)
    assert result == []


def test_filter_images_excludes_partial_gps():
    from backend.services.reconstruction import _filter_images_to_target_area
    geojson = _make_square_geojson(-80.1, 34.9, -79.9, 35.1)
    img = _make_mock_image()
    img.latitude = 35.0
    img.longitude = None
    result = _filter_images_to_target_area([img], geojson)
    assert result == []


def test_filter_images_all_outside_returns_empty():
    from backend.services.reconstruction import _filter_images_to_target_area
    geojson = _make_square_geojson(0.0, 0.0, 1.0, 1.0)
    img = _make_mock_image(lat=35.0, lon=-80.0)
    result = _filter_images_to_target_area([img], geojson)
    assert result == []


# ---------------------------------------------------------------------------
# Thumbnail generation tests
# ---------------------------------------------------------------------------

def test_generate_thumbnail_calls_gsplat_renderer(tmp_path):
    from unittest.mock import MagicMock, patch

    from backend.services.reconstruction import _generate_thumbnail

    splat = tmp_path / "splat.ply"
    splat.write_bytes(b"ply data")
    out = tmp_path / "thumb.jpg"

    mock_render = MagicMock()
    with patch.dict("sys.modules", {"gsplat": MagicMock(render_nadir=mock_render)}):
        result = _generate_thumbnail(splat, out)

    mock_render.assert_called_once_with(str(splat), str(out), width=512, height=512)
    assert result == out


def test_generate_thumbnail_creates_parent_dir(tmp_path):
    from unittest.mock import MagicMock, patch

    from backend.services.reconstruction import _generate_thumbnail

    splat = tmp_path / "splat.ply"
    splat.write_bytes(b"ply data")
    out = tmp_path / "nested" / "dir" / "thumb.jpg"

    mock_render = MagicMock()
    with patch.dict("sys.modules", {"gsplat": MagicMock(render_nadir=mock_render)}):
        _generate_thumbnail(splat, out)

    assert out.parent.is_dir()


def test_generate_thumbnail_no_gsplat_is_silent(tmp_path):
    from unittest.mock import patch

    from backend.services.reconstruction import _generate_thumbnail

    splat = tmp_path / "splat.ply"
    splat.write_bytes(b"ply data")
    out = tmp_path / "thumb.jpg"

    with patch.dict("sys.modules", {"gsplat": None}):
        result = _generate_thumbnail(splat, out)

    assert result is None


# ---------------------------------------------------------------------------
# Integration test: _run_pipeline calls _generate_thumbnail
# ---------------------------------------------------------------------------

def test_run_pipeline_calls_generate_thumbnail(setup_test_db):
    import tempfile
    from unittest.mock import MagicMock, patch

    from backend.db.database import get_db
    from backend.db.models import Image as ImageModel
    from backend.main import app
    from backend.services.reconstruction import _run_pipeline
    from tests.conftest import TestSessionLocal

    db = next(app.dependency_overrides[get_db]())
    s = _make_session(db)
    img = ImageModel(session_id=s.id, filename="f.jpg", filepath="/tmp/f.jpg", usable=True,
                     latitude=35.0, longitude=-80.0, altitude_m=100.0)
    db.add(img)
    db.commit()
    db.refresh(img)

    with tempfile.TemporaryDirectory() as tmp:
        colmap_dir = Path(tmp) / "colmap"
        colmap_dir.mkdir()

        mock_workspace = MagicMock()
        mock_colmap = MagicMock()
        mock_gsplat = MagicMock(return_value={"gaussian_count": 100, "psnr": 25.0, "ssim": 0.9})
        mock_lod = MagicMock(return_value=(Path(tmp) / "p.ply", Path(tmp) / "m.ply"))
        mock_thumb = MagicMock(return_value=None)

        with patch("backend.services.reconstruction._write_colmap_workspace", mock_workspace), \
             patch("backend.services.reconstruction._run_colmap", mock_colmap), \
             patch("backend.services.reconstruction._run_gsplat", mock_gsplat), \
             patch("backend.services.reconstruction._generate_lod", mock_lod), \
             patch("backend.services.reconstruction._generate_thumbnail", mock_thumb), \
             patch("backend.services.reconstruction.SessionLocal", TestSessionLocal), \
             patch("backend.services.reconstruction.get_config") as mock_cfg:

            mock_cfg.return_value.data_dir = tmp
            mock_cfg.return_value.exports_dir = tmp
            mock_cfg.return_value.processed_dir = tmp

            import threading
            cancel = threading.Event()
            _run_pipeline(999, "quick", colmap_dir, [img.id], cancel)

        mock_thumb.assert_called_once()

        # After _run_pipeline completes, check DB state
        from backend.db.models import Reconstruction as ReconModel
        rec_check = db.query(ReconModel).filter(ReconModel.session_id == s.id).first()
        if rec_check:
            assert rec_check.thumb_path is None


# ---------------------------------------------------------------------------
# _store_reprojection_errors tests
# ---------------------------------------------------------------------------

def test_store_reprojection_errors_writes_mean(setup_test_db, tmp_path):
    from backend.db.database import get_db
    from backend.db.models import Image, Reconstruction, ReconstructionFrame
    from backend.db.models import Session as SessionModel
    from backend.main import app
    from backend.services.reconstruction import _store_reprojection_errors

    db = next(app.dependency_overrides[get_db]())
    s = SessionModel(name="T", folder_path="/tmp/t", photo_count=0, usable_count=0)
    db.add(s)
    db.commit()
    db.refresh(s)

    img1 = Image(session_id=s.id, filename="frame_00001.jpg", filepath="/f1.jpg", usable=True)
    img2 = Image(session_id=s.id, filename="frame_00002.jpg", filepath="/f2.jpg", usable=True)
    db.add_all([img1, img2])
    db.commit()
    db.refresh(img1)
    db.refresh(img2)

    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=2)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    db.add_all([
        ReconstructionFrame(reconstruction_id=rec.id, image_id=img1.id),
        ReconstructionFrame(reconstruction_id=rec.id, image_id=img2.id),
    ])
    db.commit()

    # Build synthetic COLMAP TXT files
    sparse = tmp_path / "sparse" / "0"
    sparse.mkdir(parents=True)

    # points3D.txt: 3 points with known errors
    (sparse / "points3D.txt").write_text(
        "# comment\n"
        "1 0.1 0.2 0.3 255 0 0 0.5 1 0 2 1\n"   # error=0.5
        "2 0.4 0.5 0.6 0 255 0 1.5 1 1 2 0\n"   # error=1.5
        "3 0.7 0.8 0.9 0 0 255 2.0 2 0\n"        # error=2.0
    )

    # images.txt: img1 sees points 1+2, img2 sees point 3 only
    (sparse / "images.txt").write_text(
        "# comment\n"
        "1 1 0 0 0 0 0 0 1 frame_00001.jpg\n"
        "100.0 200.0 1 150.0 250.0 2\n"
        "2 1 0 0 0 0 0 0 1 frame_00002.jpg\n"
        "100.0 200.0 3 150.0 250.0 -1\n"
    )

    _store_reprojection_errors(db, rec.id, tmp_path)

    db.expire_all()
    f1 = db.query(ReconstructionFrame).filter(
        ReconstructionFrame.reconstruction_id == rec.id,
        ReconstructionFrame.image_id == img1.id,
    ).first()
    f2 = db.query(ReconstructionFrame).filter(
        ReconstructionFrame.reconstruction_id == rec.id,
        ReconstructionFrame.image_id == img2.id,
    ).first()

    # img1 mean = (0.5 + 1.5) / 2 = 1.0
    assert f1.colmap_error_px == pytest.approx(1.0)
    # img2 mean = 2.0
    assert f2.colmap_error_px == pytest.approx(2.0)


def test_store_reprojection_errors_missing_dir_is_noop(setup_test_db, tmp_path):
    from backend.db.database import get_db
    from backend.main import app
    from backend.services.reconstruction import _store_reprojection_errors

    db = next(app.dependency_overrides[get_db]())
    # Should not raise even if sparse/0/ is absent
    _store_reprojection_errors(db, 9999, tmp_path)


# ---------------------------------------------------------------------------
# _parse_checkpoint_metrics tests
# ---------------------------------------------------------------------------

def test_parse_checkpoint_metrics_extracts_all_checkpoints():
    from backend.services.reconstruction import _parse_checkpoint_metrics

    output = (
        "some noise\n"
        "[iter 1000] PSNR: 18.2 SSIM: 0.710\n"
        "more noise\n"
        "[iter 2000] PSNR: 21.5 SSIM: 0.800\n"
        "[iter 7000] PSNR: 24.8 SSIM: 0.870\n"
    )
    metrics = _parse_checkpoint_metrics(output)

    assert len(metrics) == 3
    assert metrics[0] == {"iter": 1000, "psnr": pytest.approx(18.2), "ssim": pytest.approx(0.71)}
    assert metrics[2]["iter"] == 7000
    assert metrics[2]["psnr"] == pytest.approx(24.8)


def test_parse_checkpoint_metrics_empty_output_returns_empty():
    from backend.services.reconstruction import _parse_checkpoint_metrics

    assert _parse_checkpoint_metrics("") == []
    assert _parse_checkpoint_metrics("nothing here") == []


def test_compute_coverage_gaps_classifies_levels(tmp_path):
    import json

    import numpy as np

    from backend.services.reconstruction import _compute_coverage_gaps

    # 10 dense voxels (100 pts each) + 1 sparse voxel (3 pts far away)
    # median = 100, ratio for sparse = 3/100 = 3% < 5% → very_sparse
    n_dense_voxels = 10
    pts_per_dense = 100
    n_sparse = 3

    positions = []
    for v in range(n_dense_voxels):
        # Each dense voxel: 100 pts at (v*2, 0, 0) — 2 m apart → distinct voxels at voxel_size_m=1.0
        cluster = np.full((pts_per_dense, 3), [float(v * 2), 0.0, 0.0], dtype=np.float32)
        positions.append(cluster)
    # Sparse voxel far away
    positions.append(np.full((n_sparse, 3), [100.0, 100.0, 100.0], dtype=np.float32))

    all_positions = np.vstack(positions)
    n_total = len(all_positions)

    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {n_total}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "end_header\n"
    ).encode("ascii")

    ply_path = tmp_path / "test.ply"
    ply_path.write_bytes(header + all_positions.tobytes())

    output_path = tmp_path / "gaps.json"
    cells = _compute_coverage_gaps(ply_path, output_path, voxel_size_m=1.0)

    assert output_path.exists()
    loaded = json.loads(output_path.read_text())
    assert loaded == cells

    # Sparse voxel (3 pts vs median 100) → ratio = 3% < 5% → very_sparse
    sparse_cells = [c for c in cells if c["level"] == "very_sparse"]
    assert len(sparse_cells) == 1
    assert sparse_cells[0]["x"] == pytest.approx(100.0, abs=1.1)

    # Dense voxels (100 pts vs median 100 → 100% → excluded as normal density)
    excluded_cells = [c for c in cells if abs(c["x"]) < 20.0]
    assert len(excluded_cells) == 0


def test_compute_coverage_gaps_empty_ply_returns_empty(tmp_path):
    from backend.services.reconstruction import _compute_coverage_gaps

    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        "element vertex 0\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "end_header\n"
    ).encode("ascii")
    ply_path = tmp_path / "empty.ply"
    ply_path.write_bytes(header)

    cells = _compute_coverage_gaps(ply_path, tmp_path / "gaps.json")
    assert cells == []


def test_store_reprojection_errors_rejected_frame_stays_null(setup_test_db, tmp_path):
    from backend.db.database import get_db
    from backend.db.models import Image, Reconstruction, ReconstructionFrame
    from backend.db.models import Session as SessionModel
    from backend.main import app
    from backend.services.reconstruction import _store_reprojection_errors

    db = next(app.dependency_overrides[get_db]())
    s = SessionModel(name="T2", folder_path="/tmp/t2", photo_count=0, usable_count=0)
    db.add(s)
    db.commit()
    db.refresh(s)
    img = Image(session_id=s.id, filename="rejected.jpg", filepath="/r.jpg", usable=True)
    db.add(img)
    db.commit()
    db.refresh(img)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    db.add(ReconstructionFrame(reconstruction_id=rec.id, image_id=img.id))
    db.commit()

    sparse = tmp_path / "sparse" / "0"
    sparse.mkdir(parents=True)
    (sparse / "points3D.txt").write_text("# empty\n")
    # Image has only unmatched keypoints (all -1)
    (sparse / "images.txt").write_text(
        "1 1 0 0 0 0 0 0 1 rejected.jpg\n"
        "100.0 200.0 -1\n"
    )

    _store_reprojection_errors(db, rec.id, tmp_path)

    db.expire_all()
    frame = db.query(ReconstructionFrame).filter(
        ReconstructionFrame.reconstruction_id == rec.id,
        ReconstructionFrame.image_id == img.id,
    ).first()
    assert frame.colmap_error_px is None
