from __future__ import annotations

from datetime import datetime, timedelta

from backend.db.models import Footprint, Image
from backend.db.models import Session as SessionModel
from backend.services.preflight_quality import build_preflight_quality_report


def _make_session(db):
    session = SessionModel(
        name="Preflight", folder_path="/tmp/preflight", photo_count=0, usable_count=0
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
        filepath=f"/tmp/frame_{index:04d}.jpg",
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


def test_preflight_report_flags_missing_gps_duplicate_timestamps_and_gaps(client):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    _add_image(db, session.id, 0, timestamp=t0, latitude=35.0, sharpness=20.0, flag="blurry")
    _add_image(db, session.id, 1, timestamp=t0, latitude=35.001)
    _add_image(db, session.id, 2, timestamp=t0 + timedelta(seconds=1), latitude=None, flag="no_gps")
    _add_image(
        db, session.id, 3, timestamp=t0 + timedelta(seconds=20), brightness=245.0, flag="bright"
    )
    _add_image(db, session.id, 4, timestamp=None, latitude=35.004)

    report = build_preflight_quality_report(session.id, db)

    assert report["total_frames"] == 5
    assert report["usable_frames"] == 5
    assert report["gps"]["missing"] == 1
    assert report["timestamps"]["missing"] == 1
    assert report["timestamps"]["duplicate_groups"] == 1
    assert report["timestamps"]["gap_count"] == 1
    assert report["quality"]["blur_count"] == 1
    assert report["quality"]["bright_count"] == 1
    assert report["safe_to_reconstruct"] in {"caution", "no"}
    assert report["recommended_action"]

    resp = client.get(f"/reconstruction/preflight/{session.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["score"] == report["score"]
    assert data["quality"]["brightness_histogram"]


def test_preflight_report_estimates_overlap_from_footprints(client):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    images = [
        _add_image(db, session.id, index, timestamp=t0 + timedelta(seconds=index))
        for index in range(3)
    ]
    polygons = [
        "POLYGON((0 0, 2 0, 2 2, 0 2, 0 0))",
        "POLYGON((1 0, 3 0, 3 2, 1 2, 1 0))",
        "POLYGON((2 0, 4 0, 4 2, 2 2, 2 0))",
    ]
    for image, polygon in zip(images, polygons, strict=True):
        db.add(Footprint(image_id=image.id, geom_wkt=polygon))
    db.commit()

    report = build_preflight_quality_report(session.id, db)

    assert report["coverage"]["footprint_count"] == 3
    assert report["coverage"]["estimated_overlap_pct"] == 33.3
    assert not any("Low estimated overlap" in warning for warning in report["warnings"])


def test_preflight_report_404_for_missing_session(client):
    resp = client.get("/reconstruction/preflight/999999")
    assert resp.status_code == 404


def test_preflight_report_flags_frozen_gps_coordinates(client):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    for index in range(12):
        _add_image(
            db,
            session.id,
            index,
            timestamp=t0 + timedelta(seconds=index),
            latitude=35.0,
            longitude=-80.0,
        )

    report = build_preflight_quality_report(session.id, db)

    assert report["gps_lock"]["longest_frozen_run"] == 12
    assert any("frozen" in warning for warning in report["warnings"])
    assert any("frozen" in warning for warning in report["gps_lock"]["warnings"])


def test_preflight_report_flags_implausible_gps_jump(client):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    for index in range(4):
        _add_image(
            db,
            session.id,
            index,
            timestamp=t0 + timedelta(seconds=index),
            latitude=35.0 + index * 0.0001,
            longitude=-80.0,
        )
    # ~1.1 km jump one second after the previous frame (~1113 m/s).
    _add_image(
        db,
        session.id,
        4,
        timestamp=t0 + timedelta(seconds=4),
        latitude=35.0 + 3 * 0.0001 + 0.01,
        longitude=-80.0,
    )

    report = build_preflight_quality_report(session.id, db)

    assert report["gps_lock"]["jump_count"] == 1
    assert any("jump" in warning for warning in report["warnings"])


def test_preflight_report_clean_track_has_no_gps_lock_warnings(client):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    for index in range(12):
        _add_image(
            db,
            session.id,
            index,
            timestamp=t0 + timedelta(seconds=index),
            latitude=35.0 + index * 0.0001,
            longitude=-80.0,
        )

    report = build_preflight_quality_report(session.id, db)

    assert report["gps_lock"]["warnings"] == []
    assert report["gps_lock"]["jump_count"] == 0
    assert report["gps_lock"]["longest_frozen_run"] < 10
