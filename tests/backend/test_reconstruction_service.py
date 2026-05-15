from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from backend.db.models import Reconstruction, ReconstructionFrame
from backend.db.models import Session as SessionModel


def _make_session(db):
    s = SessionModel(name="Test", folder_path="/tmp/t", photo_count=0, usable_count=0)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


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
