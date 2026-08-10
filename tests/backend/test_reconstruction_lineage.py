"""Tests for reconstruction parent/child lineage (issue #372)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from backend.db.models import Reconstruction
from backend.db.models import Session as SessionModel

MIGRATION = Path("backend/db/migrations/versions/0010_reconstruction_lineage.py").read_text()


def _get_db(client):
    from backend.main import app
    return app.state.test_db_session


def _make_session_with_image(db, count=1):
    from backend.db.models import Image

    s = SessionModel(
        name="Lineage Test", folder_path="/tmp/l", photo_count=count, usable_count=count
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    for i in range(count):
        img = Image(
            session_id=s.id,
            filename=f"frame_{i:05d}.jpg",
            filepath=f"/tmp/frame_{i:05d}.jpg",
            usable=True,
            latitude=35.0,
            longitude=-80.0,
            altitude_m=100.0,
        )
        db.add(img)
    db.commit()
    return s


def test_migration_0010_revises_0009_and_is_the_new_head():
    assert 'revision: str = "0010"' in MIGRATION
    assert 'down_revision: str | None = "0009"' in MIGRATION


def test_parent_reconstruction_id_column_and_relationship(client):
    db = _get_db(client)
    s = _make_session_with_image(db)

    parent = Reconstruction(session_id=s.id, preset="quick", status="complete", frames_used=1)
    db.add(parent)
    db.commit()
    db.refresh(parent)

    child = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="pending",
        frames_used=1,
        parent_reconstruction_id=parent.id,
    )
    db.add(child)
    db.commit()
    db.refresh(child)

    assert child.parent_reconstruction_id == parent.id
    assert child.parent.id == parent.id
    assert [c.id for c in parent.children] == [child.id]


def test_start_reconstruction_sets_parent_reconstruction_id(client):
    from backend.services.reconstruction import start_reconstruction

    db = _get_db(client)
    s = _make_session_with_image(db)

    parent = Reconstruction(session_id=s.id, preset="quick", status="complete", frames_used=1)
    db.add(parent)
    db.commit()
    db.refresh(parent)

    with patch("backend.services.reconstruction.enqueue") as mock_enqueue:
        rec = start_reconstruction(s.id, "quick", db, parent_reconstruction_id=parent.id)

    mock_enqueue.assert_called_once()
    assert rec.parent_reconstruction_id == parent.id


def test_start_router_forwards_and_exposes_parent_reconstruction_id(client):
    db = _get_db(client)
    s = _make_session_with_image(db)

    with patch("backend.routers.reconstruction.start_reconstruction") as mock_start:
        rec = Reconstruction(
            id=1,
            session_id=s.id,
            status="pending",
            preset="quick",
            progress_pct=0.0,
            frames_used=1,
            step="",
            parent_reconstruction_id=42,
        )
        mock_start.return_value = rec
        resp = client.post(
            "/reconstruction/start",
            json={"session_id": s.id, "preset": "quick", "parent_reconstruction_id": 42},
        )

    assert resp.status_code == 201
    assert resp.json()["parent_reconstruction_id"] == 42
    _, kwargs = mock_start.call_args
    assert kwargs["parent_reconstruction_id"] == 42


def test_get_lineage_endpoint_returns_ancestors_and_children(client):
    db = _get_db(client)
    s = _make_session_with_image(db)

    grandparent = Reconstruction(session_id=s.id, preset="quick", status="complete", frames_used=1)
    db.add(grandparent)
    db.commit()
    db.refresh(grandparent)

    parent = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="complete",
        frames_used=1,
        parent_reconstruction_id=grandparent.id,
    )
    db.add(parent)
    db.commit()
    db.refresh(parent)

    child = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="pending",
        frames_used=1,
        parent_reconstruction_id=parent.id,
    )
    db.add(child)
    db.commit()
    db.refresh(child)

    resp = client.get(f"/reconstruction/{parent.id}/lineage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["parent_reconstruction_id"] == grandparent.id
    assert data["ancestor_ids"] == [grandparent.id]
    assert data["child_ids"] == [child.id]


def test_get_lineage_not_found(client):
    resp = client.get("/reconstruction/999999/lineage")
    assert resp.status_code == 404
