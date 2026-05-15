from __future__ import annotations

from unittest.mock import patch

from backend.db.models import Image, Reconstruction
from backend.db.models import Session as SessionModel


def _make_session_with_images(db, count=3):
    s = SessionModel(name="Recon Test", folder_path="/tmp/r", photo_count=count, usable_count=count)
    db.add(s)
    db.commit()
    db.refresh(s)
    for i in range(count):
        img = Image(
            session_id=s.id,
            filename=f"frame_{i:05d}.jpg",
            filepath=f"/tmp/frame_{i:05d}.jpg",
            usable=True,
            latitude=35.0 + i * 0.001,
            longitude=-80.0,
            altitude_m=100.0,
        )
        db.add(img)
    db.commit()
    return s


def _get_db(client):
    from backend.db.database import get_db
    from backend.main import app
    return next(app.dependency_overrides[get_db]())


def test_start_reconstruction(client):
    db = _get_db(client)
    s = _make_session_with_images(db)

    with patch("backend.routers.reconstruction.start_reconstruction") as mock_start:
        rec = Reconstruction(
            id=1, session_id=s.id, status="pending", preset="quick",
            progress_pct=0.0, frames_used=3, step="",
        )
        mock_start.return_value = rec
        resp = client.post("/reconstruction/start", json={"session_id": s.id, "preset": "quick"})

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["preset"] == "quick"


def test_start_reconstruction_invalid_preset(client):
    resp = client.post("/reconstruction/start", json={"session_id": 1, "preset": "turbo"})
    assert resp.status_code == 422


def test_start_reconstruction_already_running(client):
    db = _get_db(client)
    s = _make_session_with_images(db)

    with patch("backend.routers.reconstruction.start_reconstruction") as mock_start:
        mock_start.side_effect = ValueError("already in progress")
        resp = client.post("/reconstruction/start", json={"session_id": s.id, "preset": "quick"})

    assert resp.status_code == 409


def test_get_reconstruction_status(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_colmap",
        progress_pct=42.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running_colmap"
    assert data["progress_pct"] == 42.0


def test_get_reconstruction_status_not_found(client):
    resp = client.get("/reconstruction/999999/status")
    assert resp.status_code == 404


def test_cancel_reconstruction(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_colmap",
        progress_pct=20.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    with patch("backend.routers.reconstruction.cancel_reconstruction") as mock_cancel:
        resp = client.delete(f"/reconstruction/{rec.id}")
    assert resp.status_code == 200
    mock_cancel.assert_called_once_with(rec.id)
