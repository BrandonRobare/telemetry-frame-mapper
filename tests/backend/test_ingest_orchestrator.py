from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import piexif
from PIL import Image as PILImage


def _make_test_jpg(folder: Path, name: str) -> Path:
    p = folder / name
    img = PILImage.new("RGB", (100, 100), color=(128, 128, 128))
    img.save(str(p))
    return p


def test_import_endpoint_bad_folder(client):
    with patch("backend.routers.sessions.start_import") as mock_start:
        resp = client.post(
            "/sessions/import", json={"folder_path": "/nonexistent/path/xyz", "name": "bad"}
        )
    assert resp.status_code == 400  # rejected: absolute path
    mock_start.assert_not_called()


def test_import_endpoint_creates_session(client, tmp_path):
    from backend.core.config import AppConfig

    _make_test_jpg(tmp_path, "frame_001.jpg")
    _make_test_jpg(tmp_path, "frame_002.jpg")
    mock_cfg = AppConfig(imports_dir=str(tmp_path.parent))
    with patch("backend.routers.sessions.get_config", return_value=mock_cfg), patch(
        "backend.routers.sessions.start_import"
    ) as mock_start:
        resp = client.post(
            "/sessions/import",
            json={"folder_path": tmp_path.name, "name": "Test Import"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Import"
    assert "id" in data
    mock_start.assert_called_once()
    # start_import should have received session id (first arg) and the resolved folder path
    call_args = mock_start.call_args
    assert call_args.args[0] == data["id"]
    assert call_args.args[1] == tmp_path.resolve()


def test_progress_endpoint_returns_pending(client, tmp_path):
    """After import is kicked off, progress endpoint returns a known status."""
    from backend.core.config import AppConfig

    _make_test_jpg(tmp_path, "p.jpg")
    mock_cfg = AppConfig(imports_dir=str(tmp_path.parent))
    with patch("backend.routers.sessions.get_config", return_value=mock_cfg), patch(
        "backend.routers.sessions.start_import"
    ):
        session_id = client.post(
            "/sessions/import",
            json={"folder_path": tmp_path.name, "name": "prog"},
        ).json()["id"]
    resp = client.get(f"/sessions/{session_id}/progress")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("running", "done", "pending", "unknown")


# ---------------------------------------------------------------------------
# Helpers for _run unit tests
# ---------------------------------------------------------------------------

def _make_gps_jpg(
    folder: Path,
    name: str,
    lat: float = 35.0,
    lon: float = -80.0,
    alt_m: float = 60.96,
) -> Path:
    """Create a minimal JPEG with GPS EXIF at given coords."""
    p = folder / name
    img = PILImage.new("RGB", (100, 100), color=(128, 128, 128))

    def to_rational(value: float):
        d = int(abs(value))
        m = int((abs(value) - d) * 60)
        s = round(((abs(value) - d) * 60 - m) * 60 * 100)
        return ((d, 1), (m, 1), (s, 100))

    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S",
        piexif.GPSIFD.GPSLatitude: to_rational(lat),
        piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W",
        piexif.GPSIFD.GPSLongitude: to_rational(abs(lon)),
        piexif.GPSIFD.GPSAltitude: (int(abs(alt_m) * 100), 100),
        piexif.GPSIFD.GPSAltitudeRef: 0,
    }
    exif_dict = {"GPS": gps_ifd}
    exif_bytes = piexif.dump(exif_dict)
    img.save(str(p), "JPEG", exif=exif_bytes)
    return p


def _make_no_gps_jpg(folder: Path, name: str) -> Path:
    """Create a JPEG with zero/no GPS EXIF."""
    p = folder / name
    img = PILImage.new("RGB", (100, 100), color=(100, 100, 100))
    img.save(str(p), "JPEG")
    return p


def _make_zero_denom_gps_jpg(folder: Path, name: str) -> Path:
    """Create a JPEG whose GPS rationals have a zero denominator (corrupt EXIF)."""
    p = folder / name
    img = PILImage.new("RGB", (100, 100), color=(128, 128, 128))
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: b"N",
        piexif.GPSIFD.GPSLatitude: ((35, 1), (0, 0), (0, 1)),  # zero denominator in minutes
        piexif.GPSIFD.GPSLongitudeRef: b"W",
        piexif.GPSIFD.GPSLongitude: ((80, 1), (0, 0), (0, 1)),
    }
    exif_bytes = piexif.dump({"GPS": gps_ifd})
    img.save(str(p), "JPEG", exif=exif_bytes)
    return p


def _db_factory_for_test():
    """Return a factory that yields a fresh in-memory test DB session."""
    from tests.conftest import TestSessionLocal
    return TestSessionLocal


# ---------------------------------------------------------------------------
# Fix 3: accepted_extensions — PNG is picked up when configured
# ---------------------------------------------------------------------------

def test_run_accepts_png_when_configured(tmp_path, setup_test_db):
    """_run picks up .png files when accepted_extensions includes .png."""
    from backend.db.models import Image as ImageModel
    from backend.db.models import Session as SessionModel
    from backend.main import app
    from backend.services.ingest_orchestrator import _run
    from tests.conftest import TestSessionLocal

    db = app.state.test_db_session
    session = SessionModel(name="png-test", folder_path=str(tmp_path), photo_count=0,
                           usable_count=0)
    db.add(session)
    db.commit()
    db.refresh(session)

    # Create one PNG and one JPEG in the folder.
    png_path = tmp_path / "frame.png"
    PILImage.new("RGB", (100, 100), color=(0, 128, 255)).save(str(png_path), "PNG")
    _make_no_gps_jpg(tmp_path, "frame.jpg")

    ingest_cfg_with_png = {
        "accepted_extensions": [".jpg", ".jpeg", ".png"],
        "filter_zero_gps": False,
        "thumbnail_size_px": 64,
        "thumbnail_jpeg_quality": 75,
    }

    with patch("backend.core.config.get_ingest_config",
               return_value=ingest_cfg_with_png), \
         patch("backend.core.config.load_config") as mock_load_cfg:
        mock_load_cfg.return_value.processed_dir = str(tmp_path)
        mock_load_cfg.return_value.thumbnail_size_px = 64
        mock_load_cfg.return_value.fov_horizontal_deg = 83
        mock_load_cfg.return_value.fov_vertical_deg = 53
        mock_load_cfg.return_value.target_crs = "EPSG:32617"
        _run(session.id, tmp_path, TestSessionLocal)

    db.expire_all()
    images = db.query(ImageModel).filter(ImageModel.session_id == session.id).all()
    filenames = {img.filename for img in images}
    # Both PNG and JPEG must have been ingested.
    assert "frame.png" in filenames
    assert "frame.jpg" in filenames


# ---------------------------------------------------------------------------
# Fix 4/5: filter_zero_gps skips (0, 0) images; real-coord images still land
# ---------------------------------------------------------------------------

def test_run_filter_zero_gps_skips_zero_coord_image(tmp_path, setup_test_db):
    """When filter_zero_gps=True, images with (lat=0, lon=0) must not be inserted."""
    from backend.db.models import Image as ImageModel
    from backend.db.models import Session as SessionModel
    from backend.main import app
    from backend.services.ingest_orchestrator import _run
    from tests.conftest import TestSessionLocal

    db = app.state.test_db_session
    session = SessionModel(name="zero-gps-test", folder_path=str(tmp_path),
                           photo_count=0, usable_count=0)
    db.add(session)
    db.commit()
    db.refresh(session)

    # Create one (0, 0) GPS image and one valid-coord image.
    _make_gps_jpg(tmp_path, "zero.jpg", lat=0.0, lon=0.0)
    _make_gps_jpg(tmp_path, "valid.jpg", lat=35.0, lon=-80.0)

    ingest_cfg = {
        "accepted_extensions": [".jpg", ".jpeg"],
        "filter_zero_gps": True,
        "thumbnail_size_px": 64,
        "thumbnail_jpeg_quality": 75,
    }

    with patch("backend.core.config.get_ingest_config",
               return_value=ingest_cfg), \
         patch("backend.core.config.load_config") as mock_load_cfg:
        mock_load_cfg.return_value.processed_dir = str(tmp_path)
        mock_load_cfg.return_value.thumbnail_size_px = 64
        mock_load_cfg.return_value.fov_horizontal_deg = 83
        mock_load_cfg.return_value.fov_vertical_deg = 53
        mock_load_cfg.return_value.target_crs = "EPSG:32617"
        _run(session.id, tmp_path, TestSessionLocal)

    db.expire_all()
    images = db.query(ImageModel).filter(ImageModel.session_id == session.id).all()
    filenames = {img.filename for img in images}
    # (0,0) frame must be absent; valid frame must be present.
    assert "zero.jpg" not in filenames
    assert "valid.jpg" in filenames


def test_run_filter_zero_gps_false_keeps_zero_coord_image(tmp_path, setup_test_db):
    """When filter_zero_gps=False, even (0,0) GPS images must be inserted."""
    from backend.db.models import Image as ImageModel
    from backend.db.models import Session as SessionModel
    from backend.main import app
    from backend.services.ingest_orchestrator import _run
    from tests.conftest import TestSessionLocal

    db = app.state.test_db_session
    session = SessionModel(name="zero-gps-disabled", folder_path=str(tmp_path),
                           photo_count=0, usable_count=0)
    db.add(session)
    db.commit()
    db.refresh(session)

    _make_gps_jpg(tmp_path, "zero.jpg", lat=0.0, lon=0.0)

    ingest_cfg = {
        "accepted_extensions": [".jpg", ".jpeg"],
        "filter_zero_gps": False,
        "thumbnail_size_px": 64,
        "thumbnail_jpeg_quality": 75,
    }

    with patch("backend.core.config.get_ingest_config",
               return_value=ingest_cfg), \
         patch("backend.core.config.load_config") as mock_load_cfg:
        mock_load_cfg.return_value.processed_dir = str(tmp_path)
        mock_load_cfg.return_value.thumbnail_size_px = 64
        mock_load_cfg.return_value.fov_horizontal_deg = 83
        mock_load_cfg.return_value.fov_vertical_deg = 53
        mock_load_cfg.return_value.target_crs = "EPSG:32617"
        _run(session.id, tmp_path, TestSessionLocal)

    db.expire_all()
    images = db.query(ImageModel).filter(ImageModel.session_id == session.id).all()
    filenames = {img.filename for img in images}
    assert "zero.jpg" in filenames


def test_run_filter_zero_gps_keeps_no_gps_images(tmp_path, setup_test_db):
    """filter_zero_gps must NOT skip images that have no GPS at all (lat/lon = None)."""
    from backend.db.models import Image as ImageModel
    from backend.db.models import Session as SessionModel
    from backend.main import app
    from backend.services.ingest_orchestrator import _run
    from tests.conftest import TestSessionLocal

    db = app.state.test_db_session
    session = SessionModel(name="no-gps-preserved", folder_path=str(tmp_path),
                           photo_count=0, usable_count=0)
    db.add(session)
    db.commit()
    db.refresh(session)

    # Image with no GPS EXIF at all (lat/lon will be None after extract_exif).
    _make_no_gps_jpg(tmp_path, "nogps.jpg")

    ingest_cfg = {
        "accepted_extensions": [".jpg", ".jpeg"],
        "filter_zero_gps": True,
        "thumbnail_size_px": 64,
        "thumbnail_jpeg_quality": 75,
    }

    with patch("backend.core.config.get_ingest_config",
               return_value=ingest_cfg), \
         patch("backend.core.config.load_config") as mock_load_cfg:
        mock_load_cfg.return_value.processed_dir = str(tmp_path)
        mock_load_cfg.return_value.thumbnail_size_px = 64
        mock_load_cfg.return_value.fov_horizontal_deg = 83
        mock_load_cfg.return_value.fov_vertical_deg = 53
        mock_load_cfg.return_value.target_crs = "EPSG:32617"
        _run(session.id, tmp_path, TestSessionLocal)

    db.expire_all()
    images = db.query(ImageModel).filter(ImageModel.session_id == session.id).all()
    filenames = {img.filename for img in images}
    # No-GPS images must still be imported (filter only drops confirmed 0,0 coords).
    assert "nogps.jpg" in filenames


def test_run_creates_footprint_when_longitude_is_zero(tmp_path, setup_test_db):
    from backend.db.models import Footprint
    from backend.db.models import Image as ImageModel
    from backend.db.models import Session as SessionModel
    from backend.main import app
    from backend.services.ingest_orchestrator import _run
    from tests.conftest import TestSessionLocal

    db = app.state.test_db_session
    session = SessionModel(name="zero-lon-footprint", folder_path=str(tmp_path),
                           photo_count=0, usable_count=0)
    db.add(session)
    db.commit()
    db.refresh(session)

    _make_gps_jpg(tmp_path, "zero_lon.jpg", lat=35.0, lon=0.0, alt_m=60.96)

    ingest_cfg = {
        "accepted_extensions": [".jpg", ".jpeg"],
        "filter_zero_gps": False,
        "thumbnail_size_px": 64,
        "thumbnail_jpeg_quality": 75,
    }

    with patch("backend.core.config.get_ingest_config", return_value=ingest_cfg), \
         patch("backend.core.config.load_config") as mock_load_cfg:
        mock_load_cfg.return_value.processed_dir = str(tmp_path)
        mock_load_cfg.return_value.thumbnail_size_px = 64
        mock_load_cfg.return_value.fov_horizontal_deg = 83
        mock_load_cfg.return_value.fov_vertical_deg = 53
        mock_load_cfg.return_value.target_crs = "EPSG:32631"
        _run(session.id, tmp_path, TestSessionLocal)

    db.expire_all()
    img = db.query(ImageModel).filter(ImageModel.session_id == session.id).one()
    footprint = db.query(Footprint).filter(Footprint.image_id == img.id).one_or_none()
    assert img.longitude == 0.0
    assert footprint is not None
    assert footprint.ground_width_m > 0


def test_run_creates_footprint_when_altitude_is_zero(tmp_path, setup_test_db):
    from backend.db.models import Footprint
    from backend.db.models import Image as ImageModel
    from backend.db.models import Session as SessionModel
    from backend.main import app
    from backend.services.ingest_orchestrator import _run
    from tests.conftest import TestSessionLocal

    db = app.state.test_db_session
    session = SessionModel(name="zero-alt-footprint", folder_path=str(tmp_path),
                           photo_count=0, usable_count=0)
    db.add(session)
    db.commit()
    db.refresh(session)

    _make_gps_jpg(tmp_path, "zero_alt.jpg", lat=35.0, lon=-80.0, alt_m=0.0)

    ingest_cfg = {
        "accepted_extensions": [".jpg", ".jpeg"],
        "filter_zero_gps": False,
        "thumbnail_size_px": 64,
        "thumbnail_jpeg_quality": 75,
    }

    with patch("backend.core.config.get_ingest_config", return_value=ingest_cfg), \
         patch("backend.core.config.load_config") as mock_load_cfg:
        mock_load_cfg.return_value.processed_dir = str(tmp_path)
        mock_load_cfg.return_value.thumbnail_size_px = 64
        mock_load_cfg.return_value.fov_horizontal_deg = 83
        mock_load_cfg.return_value.fov_vertical_deg = 53
        mock_load_cfg.return_value.target_crs = "EPSG:32617"
        _run(session.id, tmp_path, TestSessionLocal)

    db.expire_all()
    img = db.query(ImageModel).filter(ImageModel.session_id == session.id).one()
    footprint = db.query(Footprint).filter(Footprint.image_id == img.id).one_or_none()
    assert img.altitude_m == 0.0
    assert footprint is not None
    # With the 1 m AGL clamp in compute_footprint, zero barometric altitude
    # still produces a small (non-degenerate) footprint.
    assert footprint.ground_width_m > 0


# ---------------------------------------------------------------------------
# Issue #506: one corrupt image must not fail a whole batch
# ---------------------------------------------------------------------------

def test_run_zero_denominator_gps_image_lands_without_gps(tmp_path, setup_test_db):
    """A zero-denominator-GPS image must import (without GPS), not kill the batch."""
    from backend.db.models import Image as ImageModel
    from backend.db.models import Session as SessionModel
    from backend.main import app
    from backend.services.ingest_orchestrator import _run, get_progress
    from tests.conftest import TestSessionLocal

    db = app.state.test_db_session
    session = SessionModel(name="zero-denom-gps", folder_path=str(tmp_path),
                           photo_count=0, usable_count=0)
    db.add(session)
    db.commit()
    db.refresh(session)

    _make_zero_denom_gps_jpg(tmp_path, "corrupt.jpg")
    _make_gps_jpg(tmp_path, "valid.jpg", lat=35.0, lon=-80.0)

    ingest_cfg = {
        "accepted_extensions": [".jpg", ".jpeg"],
        "filter_zero_gps": True,
        "thumbnail_size_px": 64,
        "thumbnail_jpeg_quality": 75,
    }

    with patch("backend.core.config.get_ingest_config", return_value=ingest_cfg), \
         patch("backend.core.config.load_config") as mock_load_cfg:
        mock_load_cfg.return_value.processed_dir = str(tmp_path)
        mock_load_cfg.return_value.thumbnail_size_px = 64
        mock_load_cfg.return_value.fov_horizontal_deg = 83
        mock_load_cfg.return_value.fov_vertical_deg = 53
        mock_load_cfg.return_value.target_crs = "EPSG:32617"
        _run(session.id, tmp_path, TestSessionLocal)

    db.expire_all()
    images = {img.filename: img for img in
              db.query(ImageModel).filter(ImageModel.session_id == session.id).all()}
    # Batch completes; corrupt image lands with no GPS; valid image keeps its GPS.
    assert get_progress(session.id)["status"] == "done"
    assert "corrupt.jpg" in images
    assert images["corrupt.jpg"].latitude is None
    assert images["corrupt.jpg"].longitude is None
    assert "valid.jpg" in images
    assert images["valid.jpg"].latitude is not None
    # Progress surfaces the skipped counter (0 here: the image landed, wasn't skipped).
    assert get_progress(session.id)["skipped"] == 0


def test_run_extract_failure_skips_image_not_batch(tmp_path, setup_test_db):
    """If extract_exif raises for one image, that image is skipped, batch survives."""
    from backend.db.models import Image as ImageModel
    from backend.db.models import Session as SessionModel
    from backend.db.models import SessionLogEntry
    from backend.main import app
    from backend.services import ingest_orchestrator
    from backend.services.ingest_orchestrator import _run, get_progress
    from tests.conftest import TestSessionLocal

    db = app.state.test_db_session
    session = SessionModel(name="extract-raises", folder_path=str(tmp_path),
                           photo_count=0, usable_count=0)
    db.add(session)
    db.commit()
    db.refresh(session)

    _make_gps_jpg(tmp_path, "boom.jpg", lat=35.0, lon=-80.0)
    _make_gps_jpg(tmp_path, "ok.jpg", lat=36.0, lon=-81.0)

    real_extract = ingest_orchestrator.extract_exif

    def flaky_extract(path):
        if path.endswith("boom.jpg"):
            raise RuntimeError("simulated decode failure")
        return real_extract(path)

    ingest_cfg = {
        "accepted_extensions": [".jpg", ".jpeg"],
        "filter_zero_gps": False,
        "thumbnail_size_px": 64,
        "thumbnail_jpeg_quality": 75,
    }

    with patch("backend.core.config.get_ingest_config", return_value=ingest_cfg), \
         patch.object(ingest_orchestrator, "extract_exif", side_effect=flaky_extract), \
         patch("backend.core.config.load_config") as mock_load_cfg:
        mock_load_cfg.return_value.processed_dir = str(tmp_path)
        mock_load_cfg.return_value.thumbnail_size_px = 64
        mock_load_cfg.return_value.fov_horizontal_deg = 83
        mock_load_cfg.return_value.fov_vertical_deg = 53
        mock_load_cfg.return_value.target_crs = "EPSG:32617"
        _run(session.id, tmp_path, TestSessionLocal)

    db.expire_all()
    filenames = {img.filename for img in
                 db.query(ImageModel).filter(ImageModel.session_id == session.id).all()}
    # Batch completes; failing image skipped, good image imported.
    assert get_progress(session.id)["status"] == "done"
    assert get_progress(session.id)["skipped"] == 1
    assert "boom.jpg" not in filenames
    assert "ok.jpg" in filenames
    # Skip is logged with the filename.
    skip_logs = db.query(SessionLogEntry).filter(
        SessionLogEntry.session_id == session.id,
        SessionLogEntry.event_type == "image_skipped",
    ).all()
    assert any("boom.jpg" in (log.message or "") for log in skip_logs)
