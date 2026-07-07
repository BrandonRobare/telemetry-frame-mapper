from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.db.models import Image, SessionFrameSelection
from backend.db.models import Session as SessionModel
from backend.services.session_merge import (
    SessionMergeError,
    merge_session_workspace,
    validate_sessions_for_merge,
)


def _make_session(db, name="Test", count=3, *, gps=True):
    s = SessionModel(name=name, folder_path="/tmp/t", photo_count=count, usable_count=count)
    db.add(s)
    db.commit()
    db.refresh(s)
    for i in range(count):
        lat = 35.0 + i * 0.001 if gps else None
        lon = -80.0 if gps else None
        img = Image(
            session_id=s.id,
            filename=f"frame_{i:05d}.jpg",
            filepath=f"/tmp/frame_{i:05d}.jpg",
            usable=True,
            latitude=lat,
            longitude=lon,
            altitude_m=100.0,
        )
        db.add(img)
    db.commit()
    return s


def test_validate_sessions_all_valid(setup_test_db):
    from backend.db.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())

    s1 = _make_session(db, "Session 1", count=3)
    s2 = _make_session(db, "Session 2", count=3)

    # Should not raise
    validate_sessions_for_merge([s1.id, s2.id], db)


def test_validate_sessions_missing(setup_test_db):
    from backend.db.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())

    s1 = _make_session(db, "Session 1", count=3)

    with pytest.raises(SessionMergeError, match="Sessions not found"):
        validate_sessions_for_merge([s1.id, 99999], db)


def test_validate_sessions_no_images(setup_test_db):
    from backend.db.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())

    s1 = _make_session(db, "Session 1", count=3)
    s2 = _make_session(db, "Session 2", count=0)

    with pytest.raises(SessionMergeError, match="has no usable images"):
        validate_sessions_for_merge([s1.id, s2.id], db)


def test_validate_sessions_no_gps(setup_test_db):
    from backend.db.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())

    s1 = _make_session(db, "Session 1", count=3, gps=False)
    s2 = _make_session(db, "Session 2", count=3, gps=False)

    with pytest.raises(SessionMergeError, match="GPS-tagged images"):
        validate_sessions_for_merge([s1.id, s2.id], db)


def test_validate_sessions_far_apart(setup_test_db):
    from backend.db.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())

    s1 = _make_session(db, "Session 1", count=3)  # lat ~35.0
    # Make session 2's images far away (>10km)
    db.add(Image(
        session_id=2,
        filename="far.jpg",
        filepath="/tmp/far.jpg",
        usable=True,
        latitude=35.2,   # ~22 km away
        longitude=-80.1,
        altitude_m=100.0,
    ))
    s2 = SessionModel(name="Session 2", folder_path="/tmp/f", photo_count=1, usable_count=1)
    db.add(s2)
    db.commit()
    db.refresh(s2)
    # Also add a first image for the session to have GPS data
    db.add(Image(
        session_id=s2.id,
        filename="frame_00000.jpg",
        filepath="/tmp/frame_00000.jpg",
        usable=True,
        latitude=35.2,
        longitude=-80.1,
        altitude_m=100.0,
    ))
    db.commit()

    with pytest.raises(SessionMergeError, match="No geographic overlap"):
        validate_sessions_for_merge([s1.id, s2.id], db)


def test_validate_sessions_with_frame_selection(setup_test_db):
    from backend.db.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())

    s1 = _make_session(db, "Session 1", count=5)
    s2 = _make_session(db, "Session 2", count=5)

    # Set frame selection: only first image for s1
    s1_image = db.query(Image).filter(Image.session_id == s1.id).first()
    db.add(SessionFrameSelection(session_id=s1.id, image_id=s1_image.id))
    db.commit()

    # Should validate OK — frame selection filters but >0 images remain
    validate_sessions_for_merge([s1.id, s2.id], db)


def test_merge_session_workspace_creates_manifest(setup_test_db, tmp_path):
    from backend.db.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())

    s1 = _make_session(db, "Session 1", count=2)
    s2 = _make_session(db, "Session 2", count=3)

    from backend.core.config import get_config
    cfg = get_config()
    real_data_dir = cfg.data_dir

    import backend.core.config as config_module
    test_data_dir = str(tmp_path / "data")
    config_module.get_config().data_dir = test_data_dir

    try:
        merged_images, colmap_dir = merge_session_workspace([s1.id, s2.id], db)

        assert len(merged_images) == 5
        assert colmap_dir.parts[-1] == f"merged_{min(s1.id, s2.id)}_{max(s1.id, s2.id)}"

        # Check manifest file
        workspace_id = f"{min(s1.id, s2.id)}_{max(s1.id, s2.id)}"
        manifest_path = Path(test_data_dir) / "colmap" / f"merged_{workspace_id}_manifest.json"
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text())
        assert manifest["source_session_ids"] == sorted([s1.id, s2.id])
        assert manifest["image_count"] == 5
        assert len(manifest["images"]) == 5
    finally:
        config_module.get_config().data_dir = real_data_dir


def test_merge_session_workspace_no_images(setup_test_db):
    from backend.db.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())

    s1 = _make_session(db, "Session 1", count=0)

    with pytest.raises(SessionMergeError, match="No usable images found"):
        merge_session_workspace([s1.id], db)


def test_merge_session_workspace_respects_frame_selection(setup_test_db, tmp_path):
    from backend.db.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())

    s1 = _make_session(db, "Session 1", count=5)
    s2 = _make_session(db, "Session 2", count=3)

    # Select only first 2 images from s1
    s1_images = db.query(Image).filter(Image.session_id == s1.id).order_by(Image.id).limit(2).all()
    for img in s1_images:
        db.add(SessionFrameSelection(session_id=s1.id, image_id=img.id))
    db.commit()

    from backend.core import config as config_module
    test_data_dir = str(tmp_path / "data")
    real_data_dir = config_module.get_config().data_dir
    config_module.get_config().data_dir = test_data_dir

    try:
        merged_images, colmap_dir = merge_session_workspace([s1.id, s2.id], db)
        # s1 contributes 2 (filtered), s2 contributes 3 = 5 total
        assert len(merged_images) == 5

        # Verify the manifest records the correct image count
        workspace_id = f"{min(s1.id, s2.id)}_{max(s1.id, s2.id)}"
        manifest_path = Path(test_data_dir) / "colmap" / f"merged_{workspace_id}_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["image_count"] == 5
        assert all(img["session_id"] in [s1.id, s2.id] for img in manifest["images"])
    finally:
        config_module.get_config().data_dir = real_data_dir