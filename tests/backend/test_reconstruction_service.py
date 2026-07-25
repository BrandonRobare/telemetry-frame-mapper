from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.db.models import Reconstruction, ReconstructionFrame, SessionComparison
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
    assert hasattr(rec, "pointcloud_path")
    assert rec.pointcloud_path is None
    assert hasattr(rec, "mesh_glb_path")
    assert rec.mesh_glb_path is None
    assert hasattr(rec, "mesh_obj_path")
    assert rec.mesh_obj_path is None
    assert hasattr(rec, "mesh_mtl_path")
    assert rec.mesh_mtl_path is None
    assert hasattr(rec, "mesh_status")
    assert rec.mesh_status is None
    assert hasattr(rec, "mesh_error")
    assert rec.mesh_error is None
    assert hasattr(rec, "flythrough_path")
    assert rec.flythrough_path is None
    assert hasattr(rec, "flythrough_status")
    assert rec.flythrough_status is None
    assert hasattr(rec, "flythrough_error")
    assert rec.flythrough_error is None

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
    rec.pointcloud_path = "/tmp/pointcloud.las"
    rec.mesh_glb_path = "/tmp/mesh.glb"
    rec.mesh_obj_path = "/tmp/mesh.obj"
    rec.mesh_mtl_path = "/tmp/mesh.mtl"
    rec.mesh_status = "complete"
    rec.flythrough_path = "/tmp/flythrough.mp4"
    rec.flythrough_status = "complete"
    db.commit()
    db.refresh(frame)
    db.refresh(rec)

    assert frame.colmap_error_px == pytest.approx(1.23)
    assert '"iter"' in rec.training_metrics
    assert rec.coverage_gaps_path == "/tmp/gaps.json"
    assert rec.pointcloud_path == "/tmp/pointcloud.las"
    assert rec.mesh_glb_path == "/tmp/mesh.glb"
    assert rec.mesh_obj_path == "/tmp/mesh.obj"
    assert rec.mesh_mtl_path == "/tmp/mesh.mtl"
    assert rec.mesh_status == "complete"
    assert rec.flythrough_path == "/tmp/flythrough.mp4"
    assert rec.flythrough_status == "complete"

    comparison = SessionComparison(
        session_a_id=s.id,
        session_b_id=s.id,
        reconstruction_a_id=rec.id,
        reconstruction_b_id=rec.id,
        status="pending",
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)

    assert comparison.id is not None
    assert comparison.status == "pending"
    assert comparison.diff_path is None
    assert comparison.error_msg is None


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
    assert rec.duration_s is None
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



def test_update_rec_sets_duration_when_completed_at_is_written(setup_test_db):
    from datetime import datetime, timezone

    from backend.db.database import get_db
    from backend.db.models import Reconstruction
    from backend.main import app
    from backend.services.reconstruction import _update_rec

    db = next(app.dependency_overrides[get_db]())
    s = _make_session(db)
    rec = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="running_gsplat",
        frames_used=1,
        started_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    _update_rec(
        db,
        rec.id,
        status="complete",
        completed_at=datetime(2026, 1, 1, 0, 0, 2, 250000, tzinfo=timezone.utc),
    )

    db.refresh(rec)
    assert rec.duration_s == pytest.approx(2.25)


def test_update_rec_clamps_negative_duration_to_zero(setup_test_db):
    from datetime import datetime, timezone

    from backend.db.database import get_db
    from backend.db.models import Reconstruction
    from backend.main import app
    from backend.services.reconstruction import _update_rec

    db = next(app.dependency_overrides[get_db]())
    s = _make_session(db)
    rec = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="running_colmap",
        frames_used=1,
        started_at=datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    _update_rec(
        db,
        rec.id,
        status="failed",
        completed_at=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
    )

    db.refresh(rec)
    assert rec.duration_s == 0.0

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


def test_workspace_cameras_txt_uses_imported_image_dimensions_and_profile_focal_length():
    from backend.services.reconstruction import _write_colmap_workspace
    with tempfile.TemporaryDirectory() as tmp:
        colmap_dir = Path(tmp)
        img = _make_mock_image()
        img.width = 5280
        img.height = 3956
        img.camera_make = "DJI"
        img.camera_model = "FC3582"
        img.lens_model = "24mm F1.7"
        img.focal_length_mm = 6.72
        Path(img.filepath).touch()
        _write_colmap_workspace(colmap_dir, [img])
        line = [
            ln for ln in (colmap_dir / "cameras.txt").read_text().splitlines()
            if not ln.startswith("#") and ln.strip()
        ][0]
        parts = line.split()
        assert parts[1] == "PINHOLE"
        assert int(parts[2]) == 5280
        assert int(parts[3]) == 3956
        assert float(parts[4]) == pytest.approx(5544.0, abs=0.1)


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


def _fake_colmap_popen(returncode=0, stderr=""):
    """subprocess.Popen stand-in for a COLMAP step: communicate() then returncode."""
    proc = MagicMock()
    proc.communicate.return_value = ("", stderr)
    proc.returncode = returncode
    return proc


def test_run_colmap_missing_binary_reports_install_guidance(tmp_path):
    import threading
    from unittest.mock import patch

    from backend.services.reconstruction import _run_colmap

    with patch("backend.services.reconstruction.subprocess.Popen", side_effect=FileNotFoundError):
        with pytest.raises(RuntimeError, match="COLMAP executable not found"):
            _run_colmap(tmp_path / "colmap", lambda *_args: None, threading.Event())


def _write_fake_images_txt(colmap_dir: Path, num_images: int) -> None:
    """Seed a sparse/0/images.txt in COLMAP's TXT format with N registered images."""
    sparse_dir = colmap_dir / "sparse" / "0"
    sparse_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Image list with two lines of data per image:",
        "#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME",
        "#   POINTS2D[] as (X, Y, POINT3D_ID)",
    ]
    for i in range(1, num_images + 1):
        lines.append(f"{i} 1.0 0.0 0.0 0.0 0.0 0.0 0.0 1 frame_{i:04d}.jpg")
        lines.append("100.0 200.0 -1")
    (sparse_dir / "images.txt").write_text("\n".join(lines) + "\n")


def test_run_colmap_returns_registered_image_count(tmp_path):
    """_run_colmap should return the count instead of discarding it."""
    import threading
    from unittest.mock import patch

    from backend.services.reconstruction import _run_colmap

    colmap_dir = tmp_path / "colmap"
    colmap_dir.mkdir()
    _write_fake_images_txt(colmap_dir, 3)

    with patch("backend.services.reconstruction.subprocess.Popen",
               return_value=_fake_colmap_popen()):
        result = _run_colmap(colmap_dir, lambda *_args: None, threading.Event())

    assert result == 3


def test_run_colmap_zero_registered_images_raises(tmp_path):
    """COLMAP completing but registering zero images is still a failure."""
    import threading
    from unittest.mock import patch

    from backend.services.reconstruction import _run_colmap

    colmap_dir = tmp_path / "colmap"
    colmap_dir.mkdir()
    _write_fake_images_txt(colmap_dir, 0)

    with patch("backend.services.reconstruction.subprocess.Popen",
               return_value=_fake_colmap_popen()):
        with pytest.raises(RuntimeError, match="Not enough feature matches"):
            _run_colmap(colmap_dir, lambda *_args: None, threading.Event())


def test_run_colmap_supports_guided_matcher(tmp_path):
    """Guided matcher presets should enable COLMAP guided matching."""
    import threading
    from unittest.mock import patch

    from backend.services.reconstruction import _run_colmap

    colmap_dir = tmp_path / "colmap"
    colmap_dir.mkdir()
    _write_fake_images_txt(colmap_dir, 1)

    cfg = {
        "camera_model": "PINHOLE",
        "matcher": "exhaustive_guided",
        "sift_max_features": 8192,
        "colmap_threads": 8,
    }
    with patch("backend.services.reconstruction.get_reconstruction_config", return_value=cfg), \
         patch("backend.services.reconstruction.subprocess.Popen",
               return_value=_fake_colmap_popen()) as run:
        _run_colmap(colmap_dir, lambda *_args: None, threading.Event())

    matcher_cmd = run.call_args_list[1].args[0]
    assert matcher_cmd[1] == "exhaustive_matcher"
    assert "--SiftMatching.guided_matching=1" in matcher_cmd
    feature_cmd = run.call_args_list[0].args[0]
    assert feature_cmd[feature_cmd.index("--ImageReader.single_camera") + 1] == "1"


def test_run_colmap_can_opt_into_per_camera_estimates(tmp_path):
    """Disabling shared intrinsics lets COLMAP emit multiple camera estimates."""
    import threading
    from unittest.mock import patch

    from backend.services.reconstruction import _run_colmap

    colmap_dir = tmp_path / "colmap"
    colmap_dir.mkdir()
    _write_fake_images_txt(colmap_dir, 1)
    cfg = {
        "camera_model": "PINHOLE",
        "single_camera": False,
        "matcher": "exhaustive",
        "sift_max_features": 8192,
        "colmap_threads": 8,
    }
    with patch("backend.services.reconstruction.get_reconstruction_config", return_value=cfg), \
         patch("backend.services.reconstruction.subprocess.Popen",
               return_value=_fake_colmap_popen()) as run:
        _run_colmap(colmap_dir, lambda *_args: None, threading.Event())

    feature_cmd = run.call_args_list[0].args[0]
    assert feature_cmd[feature_cmd.index("--ImageReader.single_camera") + 1] == "0"


def test_run_colmap_progress_callback_sequence_rebalanced(tmp_path):
    """COLMAP now owns 0-40% of overall progress (was 0-95%) so the much longer
    gsplat training phase gets a proportional share of the progress bar."""
    import threading
    from unittest.mock import MagicMock, patch

    from backend.services.reconstruction import _run_colmap

    colmap_dir = tmp_path / "colmap"
    sparse_dir = colmap_dir / "sparse" / "0"
    sparse_dir.mkdir(parents=True)
    images_txt = sparse_dir / "images.txt"
    images_txt.write_text(
        "# comment\n"
        "1 0 0 0 1 0 0 0 1 source.jpg\n"
        "1.0 2.0 -1\n"
    )

    progress_cb = MagicMock()
    with patch("backend.services.reconstruction.subprocess.Popen",
               return_value=_fake_colmap_popen()):
        _run_colmap(colmap_dir, progress_cb, threading.Event())

    assert progress_cb.call_args_list == [
        (("feature extraction", 8.0), {}),
        (("feature matching", 20.0), {}),
        (("bundle adjustment", 38.0), {}),
        (("model conversion", 40.0), {}),
        (("colmap complete", 40.0), {}),
    ]


def test_cancel_during_colmap_terminates_subprocess_and_marks_cancelled(setup_test_db):
    """Cancelling mid-COLMAP kills the real subprocess within seconds and the
    reconstruction ends up 'cancelled', not 'failed'."""
    import sys
    import threading
    import time
    from unittest.mock import MagicMock, patch

    from backend.db.database import get_db
    from backend.main import app
    from backend.services import reconstruction as recon
    from backend.services.reconstruction import (
        _kill_running_subprocess,
        _running_subprocess,
    )
    from backend.services.reconstruction import _run_pipeline_legacy as _run_pipeline
    from tests.conftest import TestSessionLocal

    db = next(app.dependency_overrides[get_db]())
    with tempfile.TemporaryDirectory() as tmp:
        rec, img, colmap_dir = _pipeline_fixture(db, tmp)
        cancel = threading.Event()

        real_popen = recon.subprocess.Popen

        def fake_popen(_cmd, **kwargs):
            # Ignore the COLMAP command; launch a real, killable long sleep.
            return real_popen(
                [sys.executable, "-c", "import time; time.sleep(60)"], **kwargs
            )

        with patch("backend.services.reconstruction._write_colmap_workspace", MagicMock()), \
             patch("backend.services.reconstruction.subprocess.Popen", side_effect=fake_popen), \
             patch("backend.services.reconstruction.SessionLocal", TestSessionLocal), \
             patch("backend.services.reconstruction.get_config") as mock_cfg:
            mock_cfg.return_value.data_dir = tmp
            mock_cfg.return_value.exports_dir = tmp
            mock_cfg.return_value.processed_dir = tmp

            t = threading.Thread(
                target=_run_pipeline, args=(rec.id, "quick", colmap_dir, [img.id], cancel)
            )
            t.start()

            # Wait until the COLMAP subprocess is actually running.
            deadline = time.monotonic() + 5
            while rec.id not in _running_subprocess and time.monotonic() < deadline:
                time.sleep(0.02)
            proc = _running_subprocess.get(rec.id)
            assert proc is not None, "COLMAP subprocess was never registered"

            # Mirror cancel_reconstruction: set the cancel event, then kill.
            cancel.set()
            _kill_running_subprocess(rec.id)

            t.join(timeout=10)
            assert not t.is_alive(), "pipeline thread did not exit after cancel"
            assert proc.poll() is not None, "COLMAP subprocess was not terminated"

    db.refresh(rec)
    assert rec.status == "cancelled"
    assert rec.step == "cancelled"


def test_build_reconstruction_diagnostics_reports_unregistered_frames(setup_test_db, tmp_path):
    from backend.db.database import get_db
    from backend.db.models import Image
    from backend.main import app
    from backend.services.reconstruction import build_reconstruction_diagnostics

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    images = []
    for idx in range(3):
        img = Image(
            session_id=session.id,
            filename=f"frame_{idx:04d}.jpg",
            filepath=f"/tmp/frame_{idx:04d}.jpg",
            usable=True,
            latitude=35.0 + idx * 0.001,
            longitude=-80.0,
            altitude_m=100.0,
        )
        db.add(img)
        images.append(img)
    db.commit()
    for img in images:
        db.refresh(img)

    colmap_dir = tmp_path / "colmap"
    sparse_dir = colmap_dir / "sparse" / "0"
    sparse_dir.mkdir(parents=True)
    (sparse_dir / "images.txt").write_text(
        "# comments\n"
        "1 1 0 0 0 0 0 0 1 frame_0000.jpg\n"
        "10 20 -1\n"
        "2 1 0 0 0 0 0 0 1 frame_0002.jpg\n"
        "10 20 -1\n"
    )

    rec = Reconstruction(
        session_id=session.id,
        preset="quick",
        status="complete",
        frames_used=3,
        frames_registered=2,
        colmap_dir=str(colmap_dir),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    for idx, img in enumerate(images):
        db.add(
            ReconstructionFrame(
                reconstruction_id=rec.id,
                image_id=img.id,
                colmap_error_px=0.5 + idx,
            )
        )
    db.commit()

    diagnostics = build_reconstruction_diagnostics(db, rec)

    assert diagnostics["summary"]["frames_used"] == 3
    assert diagnostics["summary"]["registered_count"] == 2
    assert diagnostics["summary"]["unregistered_count"] == 1
    assert diagnostics["unregistered_images"][0]["filename"] == "frame_0001.jpg"
    assert diagnostics["unregistered_images"][0]["colmap_error_px"] == pytest.approx(1.5)
    assert diagnostics["map_heatmap"] == [
        {
            "id": images[1].id,
            "filename": "frame_0001.jpg",
            "latitude": pytest.approx(35.001),
            "longitude": -80.0,
            "weight": 1,
        }
    ]
    assert {suggestion["code"] for suggestion in diagnostics["suggestions"]} >= {
        "retry_guided",
        "higher_overlap",
    }


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

def test_generate_thumbnail_delegates_to_trainer(tmp_path):
    from unittest.mock import MagicMock, patch

    from backend.services.reconstruction import _generate_thumbnail

    splat = tmp_path / "splat.ply"
    splat.write_bytes(b"ply data")
    out = tmp_path / "thumb.jpg"

    mock_render = MagicMock(return_value=out)
    with patch("backend.services.reconstruction.splat_trainer.render_thumbnail", mock_render):
        result = _generate_thumbnail(splat, out)

    mock_render.assert_called_once_with(splat, out, width=512, height=512, quality=85)
    assert result == out


def test_generate_thumbnail_creates_parent_dir(tmp_path):
    from unittest.mock import MagicMock, patch

    from backend.services.reconstruction import _generate_thumbnail

    splat = tmp_path / "splat.ply"
    splat.write_bytes(b"ply data")
    out = tmp_path / "nested" / "dir" / "thumb.jpg"

    mock_render = MagicMock(return_value=out)
    with patch("backend.services.reconstruction.splat_trainer.render_thumbnail", mock_render):
        _generate_thumbnail(splat, out)

    assert out.parent.is_dir()


def test_generate_thumbnail_no_gpu_stack_is_silent(tmp_path):
    import sys
    from unittest.mock import patch

    from backend.services.reconstruction import _generate_thumbnail

    splat = tmp_path / "splat.ply"
    splat.write_bytes(b"ply data")
    out = tmp_path / "thumb.jpg"

    # Blocking the GPU stack (None entries make import raise) proves the real
    # trainer render_thumbnail degrades to None without raising — regardless of
    # whether torch is installed on the machine running the suite.
    with patch.dict(sys.modules, {"torch": None, "gsplat": None}):
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
    from backend.services.reconstruction import _run_pipeline_legacy as _run_pipeline
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
        mock_colmap = MagicMock(return_value=1)
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
# Pipeline training-branch tests (T4 wiring contracts)
# ---------------------------------------------------------------------------

def _pipeline_fixture(db, tmp):
    """Create a session + usable image + reconstruction row for pipeline tests."""
    from backend.db.models import Image as ImageModel

    s = _make_session(db)
    img = ImageModel(session_id=s.id, filename="f.jpg", filepath="/tmp/f.jpg", usable=True,
                     latitude=35.0, longitude=-80.0, altitude_m=100.0)
    db.add(img)
    db.commit()
    db.refresh(img)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    colmap_dir = Path(tmp) / "colmap"
    colmap_dir.mkdir()
    return rec, img, colmap_dir


def _run_pipeline_with_gsplat(db, tmp, rec, img, colmap_dir, gsplat_mock, colmap_mock=None):
    """Run _run_pipeline with COLMAP mocked out and a given _run_gsplat stand-in."""
    import threading
    from unittest.mock import MagicMock, patch

    from backend.services.reconstruction import _run_pipeline_legacy as _run_pipeline
    from tests.conftest import TestSessionLocal

    if colmap_mock is None:
        colmap_mock = MagicMock(return_value=1)

    with patch("backend.services.reconstruction._write_colmap_workspace", MagicMock()), \
         patch("backend.services.reconstruction._run_colmap", colmap_mock), \
         patch("backend.services.reconstruction._run_gsplat", gsplat_mock), \
         patch("backend.services.reconstruction.SessionLocal", TestSessionLocal), \
         patch("backend.services.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.data_dir = tmp
        mock_cfg.return_value.exports_dir = tmp
        mock_cfg.return_value.processed_dir = tmp
        _run_pipeline(rec.id, "quick", colmap_dir, [img.id], threading.Event())
    db.refresh(rec)


def test_run_pipeline_gsplat_missing_completes_colmap_only(setup_test_db):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    with tempfile.TemporaryDirectory() as tmp:
        rec, img, colmap_dir = _pipeline_fixture(db, tmp)
        guidance = MagicMock(side_effect=RuntimeError(
            "Gaussian-splat training dependencies (torch + gsplat) are not installed — "
            "see docs/SETUP.md for the GPU install. "
            "The reconstruction will complete with COLMAP sparse cloud only."
        ))
        _run_pipeline_with_gsplat(db, tmp, rec, img, colmap_dir, guidance)

    assert rec.status == "complete"
    assert rec.step == "colmap_only"
    assert rec.progress_pct == 100.0


def test_run_pipeline_cancel_before_colmap_marks_cancelled(setup_test_db):
    import threading
    from unittest.mock import MagicMock, patch

    from backend.db.database import get_db
    from backend.main import app
    from backend.services.reconstruction import _run_pipeline_legacy as _run_pipeline
    from tests.conftest import TestSessionLocal

    db = next(app.dependency_overrides[get_db]())
    with tempfile.TemporaryDirectory() as tmp:
        rec, img, colmap_dir = _pipeline_fixture(db, tmp)
        cancel = threading.Event()
        cancel.set()
        with patch("backend.services.reconstruction._write_colmap_workspace", MagicMock()), \
             patch("backend.services.reconstruction._run_colmap") as colmap_mock, \
             patch("backend.services.reconstruction.SessionLocal", TestSessionLocal), \
             patch("backend.services.reconstruction.get_config") as mock_cfg:
            mock_cfg.return_value.data_dir = tmp
            mock_cfg.return_value.exports_dir = tmp
            mock_cfg.return_value.processed_dir = tmp
            _run_pipeline(rec.id, "quick", colmap_dir, [img.id], cancel)
        db.refresh(rec)

    assert rec.status == "cancelled"
    assert rec.step == "cancelled"
    assert rec.error_msg == "Cancelled by user"
    colmap_mock.assert_not_called()


def test_run_pipeline_cancel_after_colmap_marks_cancelled(setup_test_db):
    import threading
    from unittest.mock import MagicMock, patch

    from backend.db.database import get_db
    from backend.main import app
    from backend.services.reconstruction import _run_pipeline_legacy as _run_pipeline
    from tests.conftest import TestSessionLocal

    db = next(app.dependency_overrides[get_db]())
    with tempfile.TemporaryDirectory() as tmp:
        rec, img, colmap_dir = _pipeline_fixture(db, tmp)
        cancel = threading.Event()

        def colmap_then_cancel(*_args, **_kwargs):
            cancel.set()
            return 1

        colmap_mock = MagicMock(side_effect=colmap_then_cancel)
        with patch("backend.services.reconstruction._write_colmap_workspace", MagicMock()), \
             patch("backend.services.reconstruction._run_colmap", colmap_mock), \
             patch("backend.services.reconstruction._run_gsplat") as gsplat_mock, \
             patch("backend.services.reconstruction.SessionLocal", TestSessionLocal), \
             patch("backend.services.reconstruction.get_config") as mock_cfg:
            mock_cfg.return_value.data_dir = tmp
            mock_cfg.return_value.exports_dir = tmp
            mock_cfg.return_value.processed_dir = tmp
            _run_pipeline(rec.id, "quick", colmap_dir, [img.id], cancel)
        db.refresh(rec)

    assert rec.status == "cancelled"
    assert rec.step == "cancelled"
    assert rec.error_msg == "Cancelled by user"
    gsplat_mock.assert_not_called()


def test_run_pipeline_cancel_during_training_marks_cancelled(setup_test_db):
    from backend.db.database import get_db
    from backend.main import app
    from backend.services.splat_trainer import ReconstructionCancelled

    db = next(app.dependency_overrides[get_db]())
    with tempfile.TemporaryDirectory() as tmp:
        rec, img, colmap_dir = _pipeline_fixture(db, tmp)
        cancelled = MagicMock(side_effect=ReconstructionCancelled("Cancelled by user"))
        _run_pipeline_with_gsplat(db, tmp, rec, img, colmap_dir, cancelled)

    assert rec.status == "cancelled"
    assert rec.error_msg == "Cancelled by user"
    assert rec.step == "cancelled"


def test_run_pipeline_cancel_during_training_persists_checkpoint_path(setup_test_db):
    from backend.db.database import get_db
    from backend.main import app
    from backend.services.splat_trainer import ReconstructionCancelled

    db = next(app.dependency_overrides[get_db]())
    with tempfile.TemporaryDirectory() as tmp:
        rec, img, colmap_dir = _pipeline_fixture(db, tmp)

        def cancel_after_checkpoint(_colmap_dir, output_path, _preset_cfg, _progress_cb, _cancel):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"checkpoint ply")
            output_path.with_suffix(output_path.suffix + ".checkpoint.json").write_text(
                '{"reason":"cancelled_by_user","completed_iterations":12}',
                encoding="utf-8",
            )
            raise ReconstructionCancelled("Cancelled by user")

        _run_pipeline_with_gsplat(db, tmp, rec, img, colmap_dir, cancel_after_checkpoint)

        assert rec.status == "cancelled"
        assert rec.step == "cancelled_checkpoint"
        assert rec.splat_path.endswith("splat.ply")
        assert Path(rec.splat_path).exists()
        assert "checkpoint saved" in rec.error_msg


def test_run_pipeline_oom_maps_to_preset_hint(setup_test_db):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    with tempfile.TemporaryDirectory() as tmp:
        rec, img, colmap_dir = _pipeline_fixture(db, tmp)
        oom = MagicMock(side_effect=RuntimeError("CUDA out of memory: tried to allocate 2 GiB"))
        _run_pipeline_with_gsplat(db, tmp, rec, img, colmap_dir, oom)

    assert rec.status == "failed"
    assert "switch to 'quick' preset" in rec.error_msg


def test_run_pipeline_persists_frames_registered_from_colmap(setup_test_db):
    """The count _run_colmap returns should land on the reconstruction record."""
    from unittest.mock import MagicMock

    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    with tempfile.TemporaryDirectory() as tmp:
        rec, img, colmap_dir = _pipeline_fixture(db, tmp)
        gsplat_missing = MagicMock(side_effect=RuntimeError(
            "Gaussian-splat training dependencies (torch + gsplat) are not installed — "
            "see docs/SETUP.md for the GPU install. "
            "The reconstruction will complete with COLMAP sparse cloud only."
        ))
        colmap_mock = MagicMock(return_value=3)
        _run_pipeline_with_gsplat(db, tmp, rec, img, colmap_dir, gsplat_missing, colmap_mock)

    assert rec.frames_registered == 3


def test_run_pipeline_trainer_result_persisted_and_lod_generated(setup_test_db):
    """Mocked-trainer orchestration: a real PLY flows through the real _generate_lod."""
    import threading
    from unittest.mock import MagicMock, patch

    import numpy as np

    from backend.db.database import get_db
    from backend.main import app
    from backend.services import ply_io
    from backend.services.reconstruction import _run_pipeline_legacy as _run_pipeline
    from tests.conftest import TestSessionLocal

    db = next(app.dependency_overrides[get_db]())
    metrics = [
        {"iter": 250, "psnr": 21.0, "ssim": 0.80},
        {"iter": 1000, "psnr": 25.5, "ssim": 0.91},
    ]

    def fake_train(colmap_dir, output_path, config, progress_cb, cancel):
        assert config.iterations == 1000  # quick preset flowed through from_preset
        cloud = ply_io.GaussianCloud(
            means=np.arange(12, dtype=np.float32).reshape(4, 3),
            sh0=np.zeros((4, 3), dtype=np.float32),
            shN=np.zeros((4, 0, 3), dtype=np.float32),
            opacities=np.array([0.4, -0.2, 1.3, 0.0], dtype=np.float32),
            scales=np.zeros((4, 3), dtype=np.float32),
            quats=np.tile(np.array([1, 0, 0, 0], dtype=np.float32), (4, 1)),
        )
        ply_io.write_3dgs_ply(output_path, cloud)
        return {"gaussian_count": 4, "psnr": 25.5, "ssim": 0.91, "training_metrics": metrics}

    with tempfile.TemporaryDirectory() as tmp:
        rec, img, colmap_dir = _pipeline_fixture(db, tmp)
        with patch("backend.services.reconstruction._write_colmap_workspace", MagicMock()), \
             patch("backend.services.reconstruction._run_colmap", MagicMock(return_value=4)), \
             patch("backend.services.splat_trainer.train_splats", fake_train), \
             patch("backend.services.reconstruction.SessionLocal", TestSessionLocal), \
             patch("backend.services.reconstruction.get_config") as mock_cfg:
            mock_cfg.return_value.data_dir = tmp
            mock_cfg.return_value.exports_dir = tmp
            mock_cfg.return_value.processed_dir = tmp
            _run_pipeline(rec.id, "quick", colmap_dir, [img.id], threading.Event())

        db.refresh(rec)
        assert rec.status == "complete"
        assert rec.step == "done"
        assert rec.gaussian_count == 4
        assert rec.psnr == 25.5
        assert rec.ssim == 0.91
        assert json.loads(rec.training_metrics) == metrics

        # The real _generate_lod ran ply_io.prune_by_opacity on the real PLY.
        splat_path = Path(tmp) / str(rec.id) / "splat.ply"
        assert splat_path.exists()
        preview = ply_io.read_3dgs_ply(Path(rec.splat_preview_path))
        medium = ply_io.read_3dgs_ply(Path(rec.splat_medium_path))
        assert preview.means.shape[0] == 1  # max(1, int(4 * 0.10))
        assert medium.means.shape[0] == 2  # int(4 * 0.50)


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


def test_compute_coverage_gaps_classifies_levels(tmp_path, monkeypatch):
    import json
    from unittest.mock import MagicMock

    import numpy as np

    from backend.services.reconstruction import _compute_coverage_gaps

    monkeypatch.setattr(
        "backend.services.reconstruction.get_config",
        lambda: MagicMock(exports_dir=str(tmp_path), data_dir=str(tmp_path / "data")),
    )

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

    cells, output_path = _compute_coverage_gaps(ply_path, 42, voxel_size_m=1.0)

    assert output_path == tmp_path.resolve() / "coverage_gaps_42.json"
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


def test_compute_coverage_gaps_empty_ply_returns_empty(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from backend.services.reconstruction import _compute_coverage_gaps

    monkeypatch.setattr(
        "backend.services.reconstruction.get_config",
        lambda: MagicMock(exports_dir=str(tmp_path), data_dir=str(tmp_path / "data")),
    )

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

    cells, _ = _compute_coverage_gaps(ply_path, 99)
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


def test_export_point_cloud_uses_nearest_gaussian_color(tmp_path):
    from unittest.mock import patch

    from backend.services.reconstruction import _export_point_cloud

    colmap_dir = tmp_path / "colmap"
    sparse = colmap_dir / "sparse" / "0"
    sparse.mkdir(parents=True)
    (sparse / "points3D.txt").write_text(
        "1 0 0 0 1 2 3 0.5\n"
        "2 10 0 0 4 5 6 0.5\n"
    )

    ply_path = tmp_path / "splat.ply"
    ply_path.write_text(
        "ply\n"
        "format ascii 1.0\n"
        "element vertex 2\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
        "0.1 0 0 10 20 30\n"
        "9.9 0 0 200 210 220\n"
    )

    written = {}

    class FakeHeader:
        def __init__(self, point_format, version):
            self.point_format = point_format
            self.version = version
            self.scales = None
            self.offsets = None
            self.crs = None

        def add_crs(self, crs):
            self.crs = crs

    class FakeLasData:
        def __init__(self, header):
            self.header = header

        def write(self, path):
            written["path"] = Path(path)
            written["x"] = self.x.copy()
            written["red"] = self.red.copy()
            written["green"] = self.green.copy()
            written["blue"] = self.blue.copy()
            Path(path).write_bytes(b"las")

    fake_laspy = SimpleNamespace(LasHeader=FakeHeader, LasData=FakeLasData)

    with patch.dict("sys.modules", {"laspy": fake_laspy}), \
         patch("backend.services.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.exports_dir = str(tmp_path)
        output = _export_point_cloud(colmap_dir, ply_path, tmp_path / "pointcloud.las")

    assert output == tmp_path / "pointcloud.las"
    assert written["path"] == output
    assert output.read_bytes() == b"las"
    assert list(written["x"]) == [0.0, 10.0]
    assert list(written["red"]) == [10 * 257, 200 * 257]
    assert list(written["green"]) == [20 * 257, 210 * 257]
    assert list(written["blue"]) == [30 * 257, 220 * 257]



def test_export_point_cloud_transfers_semantic_labels_to_las_classification(tmp_path):
    from unittest.mock import patch

    import numpy as np

    from backend.services.reconstruction import _export_point_cloud
    from backend.services.semantic_labels import write_sidecar

    colmap_dir = tmp_path / "colmap"
    sparse = colmap_dir / "sparse" / "0"
    sparse.mkdir(parents=True)
    (sparse / "points3D.txt").write_text(
        "1 0 0 0 1 2 3 0.5\n"
        "2 10 0 0 4 5 6 0.5\n"
        "3 20 0 0 7 8 9 0.5\n"
    )

    ply_path = tmp_path / "splat.ply"
    ply_path.write_text(
        "ply\n"
        "format ascii 1.0\n"
        "element vertex 3\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
        "0.1 0 0 10 20 30\n"
        "9.9 0 0 200 210 220\n"
        "19.9 0 0 100 110 120\n"
    )
    write_sidecar(
        tmp_path,
        labels=np.array([0, 1, 4], dtype=np.uint8),
        confidence=np.ones(3, dtype=np.float16),
        labels_medium=np.array([0, 1, 4], dtype=np.uint8),
        labels_preview=np.array([0, 1, 4], dtype=np.uint8),
    )

    written = {}

    class FakeHeader:
        def __init__(self, point_format, version):
            self.point_format = point_format
            self.version = version
            self.scales = None
            self.offsets = None

        def add_crs(self, _crs):
            pass

    class FakeLasData:
        def __init__(self, header):
            self.header = header

        def write(self, path):
            written["classification"] = self.classification.copy()
            Path(path).write_bytes(b"las")

    fake_laspy = SimpleNamespace(LasHeader=FakeHeader, LasData=FakeLasData)

    with patch.dict("sys.modules", {"laspy": fake_laspy}), \
         patch("backend.services.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.exports_dir = str(tmp_path)
        _export_point_cloud(colmap_dir, ply_path, tmp_path / "pointcloud.las")

    assert list(written["classification"]) == [2, 5, 9]


def test_export_point_cloud_without_semantic_sidecar_leaves_classification_unset(tmp_path):
    from unittest.mock import patch

    from backend.services.reconstruction import _export_point_cloud

    colmap_dir = tmp_path / "colmap"
    sparse = colmap_dir / "sparse" / "0"
    sparse.mkdir(parents=True)
    (sparse / "points3D.txt").write_text("1 0 0 0 1 2 3 0.5\n")

    ply_path = tmp_path / "splat.ply"
    ply_path.write_text(
        "ply\n"
        "format ascii 1.0\n"
        "element vertex 1\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
        "0 0 0 10 20 30\n"
    )

    written = {}

    class FakeHeader:
        def __init__(self, point_format, version):
            self.point_format = point_format
            self.version = version
            self.scales = None
            self.offsets = None

        def add_crs(self, _crs):
            pass

    class FakeLasData:
        def __init__(self, header):
            self.header = header

        def write(self, path):
            written["has_classification"] = hasattr(self, "classification")
            Path(path).write_bytes(b"las")

    fake_laspy = SimpleNamespace(LasHeader=FakeHeader, LasData=FakeLasData)

    with patch.dict("sys.modules", {"laspy": fake_laspy}), \
         patch("backend.services.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.exports_dir = str(tmp_path)
        _export_point_cloud(colmap_dir, ply_path, tmp_path / "pointcloud.las")

    assert written["has_classification"] is False


def test_export_point_cloud_treats_stale_v1_sidecar_as_absent(tmp_path):
    """A pre-fix (missing schema_version) sidecar holds wrong labels — the export
    must be unclassified rather than misclassified, same as no sidecar (#498)."""
    import json
    from unittest.mock import patch

    import numpy as np

    from backend.services.reconstruction import _export_point_cloud
    from backend.services.semantic_labels import write_sidecar

    colmap_dir = tmp_path / "colmap"
    sparse = colmap_dir / "sparse" / "0"
    sparse.mkdir(parents=True)
    (sparse / "points3D.txt").write_text("1 0 0 0 1 2 3 0.5\n")

    ply_path = tmp_path / "splat.ply"
    ply_path.write_text(
        "ply\n"
        "format ascii 1.0\n"
        "element vertex 1\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
        "0 0 0 10 20 30\n"
    )

    # Write a valid (v2) sidecar, then downgrade its meta to a pre-versioning
    # sidecar with a matching gaussian_count — the only thing making it stale is
    # the missing schema_version.
    write_sidecar(
        tmp_path,
        labels=np.array([4], dtype=np.uint8),  # water -> ASPRS 9 if it were used
        confidence=np.ones(1, dtype=np.float16),
        labels_medium=np.array([4], dtype=np.uint8),
        labels_preview=np.array([4], dtype=np.uint8),
    )
    sidecar = tmp_path / "semantic_labels.npz"
    stored = dict(np.load(sidecar, allow_pickle=False))
    meta = json.loads(str(stored.pop("meta")))
    meta.pop("schema_version", None)
    np.savez(sidecar, meta=json.dumps(meta), **stored)

    written = {}

    class FakeHeader:
        def __init__(self, point_format, version):
            self.point_format = point_format
            self.version = version
            self.scales = None
            self.offsets = None

        def add_crs(self, _crs):
            pass

    class FakeLasData:
        def __init__(self, header):
            self.header = header

        def write(self, path):
            written["has_classification"] = hasattr(self, "classification")
            Path(path).write_bytes(b"las")

    fake_laspy = SimpleNamespace(LasHeader=FakeHeader, LasData=FakeLasData)

    with patch.dict("sys.modules", {"laspy": fake_laspy}), \
         patch("backend.services.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.exports_dir = str(tmp_path)
        _export_point_cloud(colmap_dir, ply_path, tmp_path / "pointcloud.las")

    assert written["has_classification"] is False


def test_safe_export_path_rejects_sibling_prefix(tmp_path):
    from backend.services.reconstruction import _safe_export_path

    exports_dir = tmp_path / "exports"
    sibling = tmp_path / "exports2" / "pointcloud.las"

    with pytest.raises(ValueError, match="outside exports directory"):
        _safe_export_path(sibling, exports_dir)


def test_run_sugar_missing_dependency_reports_optional_install(tmp_path):
    from unittest.mock import patch

    from backend.services.reconstruction import _run_sugar

    with patch.dict("sys.modules", {"sugar_scene": None, "sugar": None}):
        with pytest.raises(RuntimeError, match="SuGaR is not installed") as exc_info:
            _run_sugar(tmp_path / "colmap", tmp_path / "splat.ply", tmp_path / "exports")

    assert "github.com/Anttwo/SuGaR" in str(exc_info.value)


def test_export_mesh_assets_writes_georef_sidecar(tmp_path):
    from unittest.mock import patch

    from backend.services.reconstruction import _export_mesh_assets

    colmap_dir = tmp_path / "colmap"
    colmap_dir.mkdir()
    splat_path = tmp_path / "splat.ply"
    splat_path.write_bytes(b"ply")
    glb_path = tmp_path / "exports" / "7" / "mesh.glb"
    obj_path = tmp_path / "exports" / "7" / "mesh.obj"

    def fake_sugar(_colmap_dir, _splat_path, output_dir):
        glb_path.parent.mkdir(parents=True, exist_ok=True)
        glb_path.write_bytes(b"glb")
        obj_path.write_text("obj", encoding="utf-8")
        return {"glb": glb_path, "obj": obj_path}

    rec = SimpleNamespace(
        id=7,
        session_id=3,
        status="complete",
        colmap_dir=str(colmap_dir),
        splat_path=str(splat_path),
        geo_transform=json.dumps({
            "scale": 1.0,
            "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "translation": [0, 0, 0],
            "utm_zone": "17N",
            "utm_origin": [500000, 3900000],
        }),
    )

    with patch("backend.services.reconstruction.get_config") as mock_cfg, \
         patch("backend.services.reconstruction._run_sugar", side_effect=fake_sugar):
        mock_cfg.return_value.exports_dir = str(tmp_path / "exports")
        outputs = _export_mesh_assets(rec)

    georef_path = tmp_path / "exports" / "7" / "mesh_georef.json"
    georef = json.loads(georef_path.read_text(encoding="utf-8"))
    assert outputs["glb"] == glb_path
    assert outputs["obj"] == obj_path
    assert georef["reconstruction_id"] == 7
    assert georef["geo_transform"]["utm_zone"] == "17N"


def test_mesh_job_success_updates_status(setup_test_db, tmp_path):
    from unittest.mock import patch

    from backend.db.database import get_db
    from backend.main import app
    from backend.services.reconstruction import _run_mesh_export_job_legacy as _run_mesh_export_job
    from tests.conftest import TestSessionLocal

    db = next(app.dependency_overrides[get_db]())
    s = _make_session(db)
    rec = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="complete",
        frames_used=1,
        mesh_status="pending",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    glb = tmp_path / "mesh.glb"
    glb.write_bytes(b"glb")

    with patch("backend.services.reconstruction.SessionLocal", TestSessionLocal), \
         patch("backend.services.job_queue._make_session", TestSessionLocal), \
         patch(
             "backend.services.reconstruction._export_mesh_assets",
             return_value={"glb": glb, "obj": None, "mtl": None, "georef": tmp_path / "geo.json"},
         ):
        _run_mesh_export_job(rec.id)

    db.expire_all()
    db.refresh(rec)
    assert rec.mesh_status == "complete"
    assert rec.mesh_glb_path == str(glb)
    assert rec.mesh_error is None


def test_mesh_job_failure_updates_error(setup_test_db):
    from unittest.mock import patch

    from backend.db.database import get_db
    from backend.main import app
    from backend.services.reconstruction import _run_mesh_export_job_legacy as _run_mesh_export_job
    from tests.conftest import TestSessionLocal

    db = next(app.dependency_overrides[get_db]())
    s = _make_session(db)
    rec = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="complete",
        frames_used=1,
        mesh_status="pending",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    with patch("backend.services.reconstruction.SessionLocal", TestSessionLocal), \
         patch(
             "backend.services.reconstruction._export_mesh_assets",
             side_effect=RuntimeError("SuGaR is not installed"),
         ):
        _run_mesh_export_job(rec.id)

    db.expire_all()
    db.refresh(rec)
    assert rec.mesh_status == "failed"
    assert "SuGaR" in rec.mesh_error


def test_mesh_job_failure_keeps_long_error_unclipped(setup_test_db):
    from unittest.mock import patch

    from backend.db.database import get_db
    from backend.main import app
    from backend.services.reconstruction import _run_mesh_export_job_legacy as _run_mesh_export_job
    from tests.conftest import TestSessionLocal

    db = next(app.dependency_overrides[get_db]())
    s = _make_session(db)
    rec = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="complete",
        frames_used=1,
        mesh_status="pending",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    long_message = "x" * 600

    with patch("backend.services.reconstruction.SessionLocal", TestSessionLocal), \
         patch(
             "backend.services.reconstruction._export_mesh_assets",
             side_effect=RuntimeError(long_message),
         ):
        _run_mesh_export_job(rec.id)

    db.expire_all()
    db.refresh(rec)
    assert rec.mesh_status == "failed"
    assert rec.mesh_error == long_message
    assert len(rec.mesh_error) == 600


def test_mesh_job_failure_caps_very_long_error(setup_test_db):
    from unittest.mock import patch

    from backend.db.database import get_db
    from backend.main import app
    from backend.services.reconstruction import _ERROR_MSG_MAX_CHARS
    from backend.services.reconstruction import _run_mesh_export_job_legacy as _run_mesh_export_job
    from tests.conftest import TestSessionLocal

    db = next(app.dependency_overrides[get_db]())
    s = _make_session(db)
    rec = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="complete",
        frames_used=1,
        mesh_status="pending",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    very_long_message = "y" * 6000

    with patch("backend.services.reconstruction.SessionLocal", TestSessionLocal), \
         patch(
             "backend.services.reconstruction._export_mesh_assets",
             side_effect=RuntimeError(very_long_message),
         ):
        _run_mesh_export_job(rec.id)

    db.expire_all()
    db.refresh(rec)
    assert rec.mesh_status == "failed"
    assert len(rec.mesh_error) == _ERROR_MSG_MAX_CHARS
    assert rec.mesh_error == very_long_message[:_ERROR_MSG_MAX_CHARS]


def test_validate_keyframes_rejects_single_frame():
    from backend.services.reconstruction import _validate_keyframes

    with pytest.raises(RuntimeError, match="At least two keyframes"):
        _validate_keyframes([{"position": [0, 0, 0]}])


def test_run_video_renderer_missing_dependency_reports_browser_fallback(tmp_path):
    from unittest.mock import patch

    from backend.services.reconstruction import _run_video_renderer

    with patch.dict("sys.modules", {"gsplat": None}):
        with pytest.raises(RuntimeError, match="Use browser recording"):
            _run_video_renderer(
                tmp_path / "splat.ply",
                tmp_path / "flythrough.mp4",
                [
                    {"position": [0, 0, 3], "target": [0, 0, 0], "duration_s": 1},
                    {"position": [3, 0, 0], "target": [0, 0, 0], "duration_s": 1},
                ],
            )


def test_flythrough_job_success_updates_status(setup_test_db, tmp_path):
    from unittest.mock import patch

    from backend.db.database import get_db
    from backend.main import app
    from backend.services.reconstruction import _run_flythrough_job_legacy as _run_flythrough_job
    from tests.conftest import TestSessionLocal

    db = next(app.dependency_overrides[get_db]())
    s = _make_session(db)
    splat = tmp_path / "splat.ply"
    splat.write_bytes(b"ply")
    rec = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="complete",
        frames_used=1,
        splat_path=str(splat),
        flythrough_status="pending",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    def fake_render(_splat_path, output_path, _keyframes, **_kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"mp4")
        return output_path

    with patch("backend.services.reconstruction.SessionLocal", TestSessionLocal), \
         patch("backend.services.job_queue._make_session", TestSessionLocal), \
         patch("backend.services.reconstruction.get_config") as mock_cfg, \
         patch("backend.services.reconstruction._run_video_renderer", side_effect=fake_render):
        mock_cfg.return_value.exports_dir = str(tmp_path / "exports")
        _run_flythrough_job(
            rec.id,
            [
                {"position": [0, 0, 3], "target": [0, 0, 0], "duration_s": 1},
                {"position": [3, 0, 0], "target": [0, 0, 0], "duration_s": 1},
            ],
            30,
            640,
            480,
        )

    db.expire_all()
    db.refresh(rec)
    assert rec.flythrough_status == "complete"
    assert rec.flythrough_path.endswith("flythrough.mp4")
    assert Path(rec.flythrough_path).read_bytes() == b"mp4"


def _write_ascii_ply(path: Path, rows: list[tuple[float, float, float]]) -> None:
    body = "\n".join(f"{x} {y} {z}" for x, y, z in rows)
    path.write_text(
        "ply\n"
        "format ascii 1.0\n"
        f"element vertex {len(rows)}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "end_header\n"
        f"{body}\n",
        encoding="utf-8",
    )


def test_compute_voxel_diff_rejects_path_outside_exports(tmp_path, monkeypatch):
    """_compute_voxel_diff must refuse output_path outside exports_dir (CWE-22)."""
    from unittest.mock import MagicMock

    from backend.services.reconstruction import _compute_voxel_diff

    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    monkeypatch.setattr(
        "backend.services.reconstruction.get_config",
        lambda: MagicMock(exports_dir=str(exports_dir)),
    )

    evil_path = exports_dir / ".." / "secret" / "diff.json"
    rec_a = MagicMock()
    rec_b = MagicMock()

    with pytest.raises(ValueError, match="outside exports directory"):
        _compute_voxel_diff(rec_a, rec_b, evil_path)


def test_compute_voxel_diff_writes_new_and_removed_cells(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from backend.services.reconstruction import _compute_voxel_diff

    monkeypatch.setattr(
        "backend.services.reconstruction.get_config",
        lambda: MagicMock(exports_dir=str(tmp_path), data_dir=str(tmp_path / "data")),
    )

    a_ply = tmp_path / "a.ply"
    b_ply = tmp_path / "b.ply"
    _write_ascii_ply(a_ply, [(0, 0, 0), (1, 0, 0)])
    _write_ascii_ply(b_ply, [(1, 0, 0), (2, 0, 0)])
    geo = json.dumps({
        "scale": 1.0,
        "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "translation": [0, 0, 0],
        "utm_zone": "17N",
        "utm_origin": [500000, 3900000],
    })
    rec_a = SimpleNamespace(
        id=1,
        session_id=10,
        pointcloud_path=None,
        splat_path=str(a_ply),
        colmap_dir=None,
        geo_transform=geo,
    )
    rec_b = SimpleNamespace(
        id=2,
        session_id=11,
        pointcloud_path=None,
        splat_path=str(b_ply),
        colmap_dir=None,
        geo_transform=geo,
    )

    diff_path = tmp_path / "diff.json"
    diff = _compute_voxel_diff(rec_a, rec_b, diff_path, voxel_size_m=1.0)

    assert diff_path.exists()
    assert diff["summary"]["new_count"] == 1
    assert diff["summary"]["removed_count"] == 1
    assert diff["new"][0]["type"] == "new"
    assert diff["removed"][0]["type"] == "removed"


def test_diff_to_geojson_exports_features():
    from backend.services.reconstruction import diff_to_geojson

    diff = {
        "utm_zone": "17N",
        "summary": {"new_count": 1, "removed_count": 1},
        "comparison": {"reconstruction_a_id": 1, "reconstruction_b_id": 2},
        "new": [{"x": 500000.0, "y": 3900000.0, "z": 0.0, "size": 1.0}],
        "removed": [{"x": 500001.0, "y": 3900000.0, "z": 0.0, "size": 1.0}],
    }

    geojson = diff_to_geojson(diff)

    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 2
    assert geojson["features"][0]["properties"]["type"] == "new"
    lon, lat, _alt = geojson["features"][0]["geometry"]["coordinates"]
    assert -90 < lon < -70
    assert 30 < lat < 40


# ---------------------------------------------------------------------------
# Fix 1: camera_model cameras.txt param count
# ---------------------------------------------------------------------------

def test_write_colmap_workspace_pinhole_writes_4_params():
    """PINHOLE camera model must produce exactly 4 trailing params: fx fy cx cy."""
    from unittest.mock import patch

    from backend.services.reconstruction import _write_colmap_workspace

    with tempfile.TemporaryDirectory() as tmp:
        colmap_dir = Path(tmp)
        with patch("backend.services.reconstruction.get_reconstruction_config",
                   return_value={"camera_model": "PINHOLE", "sift_max_features": 8192,
                                 "matcher": "exhaustive", "colmap_threads": 8,
                                 "presets": {}}):
            _write_colmap_workspace(colmap_dir, [])

        cameras_txt = colmap_dir / "cameras.txt"
        data_lines = [
            ln for ln in cameras_txt.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
        assert len(data_lines) == 1
        parts = data_lines[0].split()
        # Format: CAMERA_ID MODEL WIDTH HEIGHT PARAMS...
        assert parts[1] == "PINHOLE"
        # 4 params after width/height
        assert len(parts) == 8, f"Expected 8 tokens, got: {parts}"


def test_write_colmap_workspace_simple_pinhole_writes_3_params():
    """SIMPLE_PINHOLE camera model must produce exactly 3 trailing params: f cx cy."""
    from unittest.mock import patch

    from backend.services.reconstruction import _write_colmap_workspace

    with tempfile.TemporaryDirectory() as tmp:
        colmap_dir = Path(tmp)
        with patch("backend.services.reconstruction.get_reconstruction_config",
                   return_value={"camera_model": "SIMPLE_PINHOLE", "sift_max_features": 8192,
                                 "matcher": "exhaustive", "colmap_threads": 8,
                                 "presets": {}}):
            _write_colmap_workspace(colmap_dir, [])

        cameras_txt = colmap_dir / "cameras.txt"
        data_lines = [
            ln for ln in cameras_txt.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
        assert len(data_lines) == 1
        parts = data_lines[0].split()
        assert parts[1] == "SIMPLE_PINHOLE"
        # 3 params after width/height
        assert len(parts) == 7, f"Expected 7 tokens, got: {parts}"


# ---------------------------------------------------------------------------
# Fix 2: render config is consumed by _generate_lod and _generate_thumbnail
# ---------------------------------------------------------------------------

def test_generate_lod_uses_configured_ratios(tmp_path):
    """A patched lod_preview_ratio reaches prune_by_opacity."""
    from unittest.mock import call, patch

    from backend.services.reconstruction import _generate_lod

    splat = tmp_path / "splat.ply"
    splat.write_bytes(b"ply data")

    mock_prune = MagicMock()
    with patch("backend.services.reconstruction.get_render_config",
               return_value={"lod_preview_ratio": 0.05, "lod_medium_ratio": 0.30}), \
         patch("backend.services.reconstruction.ply_io.prune_by_opacity", mock_prune):
        preview, medium = _generate_lod(splat)

    assert mock_prune.call_count == 2
    calls = mock_prune.call_args_list
    # First call: preview with 0.05
    assert calls[0] == call(splat, preview, keep_ratio=0.05)
    # Second call: medium with 0.30
    assert calls[1] == call(splat, medium, keep_ratio=0.30)


def test_generate_thumbnail_uses_configured_size_and_quality(tmp_path):
    """_generate_thumbnail reads thumbnail_size_px and thumbnail_quality from render config."""
    from unittest.mock import patch

    from backend.services.reconstruction import _generate_thumbnail

    splat = tmp_path / "splat.ply"
    splat.write_bytes(b"ply data")
    out = tmp_path / "thumb.jpg"

    mock_render = MagicMock(return_value=out)
    with patch("backend.services.reconstruction.get_render_config",
               return_value={"thumbnail_size_px": 256, "thumbnail_quality": 70}), \
         patch("backend.services.reconstruction.splat_trainer.render_thumbnail", mock_render):
        result = _generate_thumbnail(splat, out)

    mock_render.assert_called_once_with(splat, out, width=256, height=256, quality=70)
    assert result == out


def test_new_model_columns_include_semantic_fields(setup_test_db):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="complete", frames_used=0)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    assert rec.semantic_status is None
    assert rec.semantic_error is None
    assert rec.semantic_labels_path is None
    rec.semantic_status = "complete"
    rec.semantic_labels_path = "/tmp/semantic_labels.npz"
    db.commit()
    db.refresh(rec)
    assert rec.semantic_status == "complete"
    assert rec.semantic_labels_path == "/tmp/semantic_labels.npz"


def test_semantic_job_success_updates_status_and_invalidates_las(setup_test_db, tmp_path):
    from unittest.mock import patch

    from backend.db.database import get_db
    from backend.main import app
    from backend.services.reconstruction import _run_semantic_job
    from tests.conftest import TestSessionLocal

    db = next(app.dependency_overrides[get_db]())
    s = _make_session(db)
    splat = tmp_path / "splat.ply"
    splat.write_bytes(b"ply")
    cached_las = tmp_path / "pointcloud.las"
    cached_las.write_bytes(b"las")
    rec = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="complete",
        frames_used=1,
        splat_path=str(splat),
        pointcloud_path=str(cached_las),
        semantic_status="pending",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    labels = tmp_path / "semantic_labels.npz"

    def fake_compute(_rec, **_kwargs):
        labels.write_bytes(b"npz")
        _kwargs["log_cb"]("Semantic labels: processed view 1/1")
        return labels

    with patch("backend.services.reconstruction.SessionLocal", TestSessionLocal), \
         patch("backend.services.reconstruction.compute_semantic_labels", side_effect=fake_compute):
        _run_semantic_job(rec.id)

    db.expire_all()
    db.refresh(rec)
    assert rec.semantic_status == "complete"
    assert rec.semantic_labels_path == str(labels)
    assert rec.pointcloud_path is None
    assert not cached_las.exists()


def test_semantic_overlay_bytes_frames_preview_payload(tmp_path, monkeypatch):
    import struct

    import numpy as np

    from backend.services.ply_io import GaussianCloud, write_3dgs_ply
    from backend.services.reconstruction import semantic_overlay_bytes
    from backend.services.semantic_labels import write_sidecar

    cloud = GaussianCloud(
        means=np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=np.float32),
        sh0=np.zeros((3, 3), dtype=np.float32),
        shN=np.zeros((3, 0, 3), dtype=np.float32),
        opacities=np.array([0.1, 0.9, 0.5], dtype=np.float32),
        scales=np.zeros((3, 3), dtype=np.float32),
        quats=np.tile(np.array([1, 0, 0, 0], dtype=np.float32), (3, 1)),
    )
    splat = write_3dgs_ply(tmp_path / "splat.ply", cloud)
    write_sidecar(
        tmp_path,
        labels=np.array([0, 1, 2], dtype=np.uint8),
        confidence=np.ones(3, dtype=np.float16),
        labels_medium=np.array([1, 2], dtype=np.uint8),
        labels_preview=np.array([1], dtype=np.uint8),
    )
    monkeypatch.setattr(
        "backend.services.reconstruction.get_render_config",
        lambda: {"lod_preview_ratio": 0.34, "lod_medium_ratio": 0.67},
    )
    rec = SimpleNamespace(
        splat_path=str(splat),
        semantic_labels_path=str(tmp_path / "semantic_labels.npz"),
    )
    payload = semantic_overlay_bytes(rec, lod="preview")
    count = struct.unpack("<I", payload[:4])[0]
    assert count == 1
    assert payload[-1] == 1


def test_write_colmap_workspace_confines_image_filename_to_workspace(tmp_path, monkeypatch):
    """Image.filename must never be joined onto the workspace dir unsanitised.

    ingest.py derives it with os.path.basename, but a restored session bundle carries
    the archive manifest's value verbatim. On Windows os.symlink raises without
    Developer Mode, so the shutil.copy2 fallback would write attacker-controlled
    bytes to an arbitrary path — e.g. overwriting config.yaml to disable the PIN lock.
    """
    from backend.services import reconstruction as recon

    source = tmp_path / "source.jpg"
    source.write_bytes(b"image bytes")
    outside = tmp_path / "config.yaml"
    outside.write_text("pin_lock:\n  enabled: true\n")

    colmap_dir = tmp_path / "workspace" / "deep" / "nested"

    class _Img:
        filepath = str(source)
        filename = "../../../config.yaml"
        camera_make = None
        camera_model_exif = None
        focal_length_mm = None
        width_px = None
        height_px = None

    # Force the copy2 fallback, which is what actually escapes on Windows.
    monkeypatch.setattr(recon.os, "symlink", lambda *a, **k: (_ for _ in ()).throw(OSError()))

    recon._write_colmap_workspace(colmap_dir, [_Img()])

    assert outside.read_text().startswith("pin_lock:"), "workspace write escaped and clobbered it"
    assert (colmap_dir / "images" / "config.yaml").read_bytes() == b"image bytes"
