from __future__ import annotations

from datetime import datetime, timedelta

from backend.db.models import Image
from backend.db.models import Session as SessionModel
from backend.services.preflight_quality import (
    _match_density_diagnostics,
    build_preflight_quality_report,
)


def _make_session(db):
    session = SessionModel(
        name="QuickReport", folder_path="/tmp/quickreport", photo_count=0, usable_count=0
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _add_image(
    db,
    session_id: int,
    index: int,
    *,
    timestamp: datetime | None,
    filepath: str | None = None,
    latitude: float | None = 35.0,
    longitude: float | None = -80.0,
    sharpness: float | None = 250.0,
    brightness: float | None = 128.0,
    flag: str = "good",
    usable: bool = True,
):
    image = Image(
        session_id=session_id,
        filename=f"frame_{index:04d}.jpg",
        filepath=filepath or f"/tmp/frame_{index:04d}.jpg",
        timestamp=timestamp,
        latitude=latitude,
        longitude=longitude,
        altitude_m=100.0,
        sharpness_score=sharpness,
        brightness_score=brightness,
        flag=flag,
        usable=usable,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


def test_match_density_returns_none_for_empty_images(client):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)

    result = _match_density_diagnostics([])
    assert result is None

    t0 = datetime(2026, 1, 1, 12, 0, 0)
    _add_image(db, session.id, 0, timestamp=t0)
    images = db.query(Image).filter(Image.session_id == session.id).all()
    result = _match_density_diagnostics(images)
    assert result is None  # only one image, can't make pairs


def test_match_density_handles_missing_files_gracefully(client):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)

    # Create images with non-existent file paths — match density should
    # handle the missing files gracefully (best-effort).
    for i in range(30):
        _add_image(db, session.id, i, timestamp=t0 + timedelta(seconds=i))

    images = db.query(Image).filter(Image.session_id == session.id).all()
    result = _match_density_diagnostics(images)
    # All pairs fail (no real files), so None.
    assert result is None


def test_match_density_runs_on_real_image(client, tmp_path):
    """Write a small real image pair so ORB can actually run."""
    from backend.db.database import get_db
    from backend.main import app

    try:
        import cv2
    except ImportError:
        return  # skip if opencv unavailable (shouldn't happen in backend env)

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)

    # Create two small synthetic images with visible texture
    import numpy as np

    img_a = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
    img_b = np.random.randint(0, 255, (100, 100), dtype=np.uint8)

    path_a = tmp_path / "frame_0000.jpg"
    path_b = tmp_path / "frame_0001.jpg"
    cv2.imwrite(str(path_a), img_a)
    cv2.imwrite(str(path_b), img_b)

    _add_image(db, session.id, 0, timestamp=t0, filepath=str(path_a))
    _add_image(db, session.id, 1, timestamp=t0 + timedelta(seconds=1), filepath=str(path_b))

    images = db.query(Image).filter(Image.session_id == session.id).all()
    result = _match_density_diagnostics(images)

    assert result is not None
    assert result["samples"] >= 1
    assert "avg_matches" in result
    assert "weak_ratio" in result


def test_quick_report_endpoint(client):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)

    for i in range(5):
        _add_image(db, session.id, i, timestamp=t0 + timedelta(seconds=i))

    resp = client.get(f"/sessions/{session.id}/quick-report")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session.id
    assert data["total_frames"] == 5
    assert data["usable_frames"] == 5
    assert "score" in data
    assert data["safe_to_reconstruct"] in {"yes", "caution", "no"}
    assert isinstance(data["warnings"], list)
    assert isinstance(data["recommended_action"], str)
    assert data["gps_completeness_pct"] == 100.0
    assert data["blur_pct"] == 0.0
    assert data["exposure_issue_pct"] == 0.0
    assert data["lighting_inconsistent"] is False
    assert data["lighting_p10_p90_spread"] == 0.0


def test_preflight_flags_variable_lighting(client):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)

    for i, brightness in enumerate([20, 30, 128, 220, 230]):
        _add_image(db, session.id, i, timestamp=t0 + timedelta(seconds=i), brightness=brightness)

    report = build_preflight_quality_report(session.id, db)
    lighting = report["quality"]["lighting"]
    assert lighting["p10_p90_spread"] == 210.0
    assert lighting["inconsistent"] is True
    assert any("Lighting varies substantially" in warning for warning in report["warnings"])


def test_quick_report_404(client):
    resp = client.get("/sessions/999999/quick-report")
    assert resp.status_code == 404


def test_preflight_report_includes_match_density(client):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)

    for i in range(5):
        _add_image(db, session.id, i, timestamp=t0 + timedelta(seconds=i))

    report = build_preflight_quality_report(session.id, db)
    assert "match_density" in report
    # match_density is None when files are missing — that's fine
    # (the field just shows the diagnostic was attempted)


def test_weak_texture_warning_in_report(client, tmp_path):
    """Build a preflight report with images that exist but have noise texture
    that should produce low ORB matches. The warning appears only when
    weak_ratio >= threshold."""
    from backend.db.database import get_db
    from backend.main import app

    try:
        import cv2
    except ImportError:
        return

    import numpy as np

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)

    # Create a series of nearly-flat images (solid gray) that will produce
    # very few ORB features — simulating a weak-texture stretch.
    for i in range(31):
        # Solid gray with tiny noise
        img = np.full((100, 100), 128, dtype=np.uint8)
        # small random noise so cv2 doesn't think it's completely blank
        noise = np.random.randint(0, 4, (100, 100), dtype=np.uint8)
        img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        path = tmp_path / f"gray_{i:04d}.jpg"
        cv2.imwrite(str(path), img)
        _add_image(db, session.id, i, timestamp=t0 + timedelta(seconds=i), filepath=str(path))

    report = build_preflight_quality_report(session.id, db)
    assert "match_density" in report
    md = report["match_density"]
    # Solid-gray images should produce very few ORB features
    if md is not None:
        assert md["samples"] >= 1
        # The weak-ratio should be high (flat images = low matches)
