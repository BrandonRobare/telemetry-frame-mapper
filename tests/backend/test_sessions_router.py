from __future__ import annotations

from unittest.mock import patch

from backend.db.models import Image, Reconstruction
from backend.db.models import Session as SessionModel


def _make_session(client, name="Test Session"):
    from backend.db.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())
    s = SessionModel(name=name, folder_path="/tmp/test", photo_count=0, usable_count=0)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_list_sessions_empty(client):
    resp = client.get("/sessions/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_session_not_found(client):
    resp = client.get("/sessions/999999")
    assert resp.status_code == 404


def test_get_session_found(client):
    s = _make_session(client)
    resp = client.get(f"/sessions/{s.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == s.id
    assert data["name"] == s.name


def test_delete_session(client):
    s = _make_session(client, name="ToDelete")
    resp = client.delete(f"/sessions/{s.id}")
    assert resp.status_code == 200
    assert client.get(f"/sessions/{s.id}").status_code == 404


def test_delete_session_not_found(client):
    resp = client.delete("/sessions/999999")
    assert resp.status_code == 404


def test_delete_session_removes_thumbnails_and_reconstruction_artifacts(client, tmp_path):
    from backend.db.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())

    exports_dir = tmp_path / "exports"
    processed_dir = tmp_path / "processed"
    data_dir = tmp_path / "data"
    s = SessionModel(name="WithArtifacts", folder_path="/tmp/test", photo_count=1, usable_count=1)
    db.add(s)
    db.commit()
    db.refresh(s)

    image_thumb = processed_dir / str(s.id) / "thumbs" / "frame.jpg"
    image_thumb.parent.mkdir(parents=True)
    image_thumb.write_bytes(b"thumb")
    colmap_dir = data_dir / "colmap" / str(s.id)
    colmap_dir.mkdir(parents=True)

    db.add(Image(
        session_id=s.id,
        filename="frame.jpg",
        filepath="/tmp/test/frame.jpg",
        thumb_path=str(image_thumb),
    ))
    db.commit()

    rec = Reconstruction(
        session_id=s.id, status="complete", preset="quick",
        progress_pct=100.0, frames_used=1, colmap_dir=str(colmap_dir),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    rec_id = rec.id
    export_dir = exports_dir / str(rec.id)
    export_dir.mkdir(parents=True)
    splat = export_dir / "splat.ply"
    splat.write_bytes(b"splat")
    rec.splat_path = str(splat)
    db.commit()

    cfg = type("Cfg", (), {
        "processed_dir": str(processed_dir),
        "exports_dir": str(exports_dir),
        "data_dir": str(data_dir),
    })()
    with patch("backend.routers.sessions.get_config", return_value=cfg), \
         patch("backend.routers.sessions.cancel_reconstruction") as mock_cancel:
        resp = client.delete(f"/sessions/{s.id}")

    assert resp.status_code == 200
    mock_cancel.assert_called_once_with(rec_id)
    assert not image_thumb.exists()
    assert not export_dir.exists()
    assert not colmap_dir.exists()
    assert client.get(f"/sessions/{s.id}").status_code == 404


# ---- tags + notes (issue #369) ----


def test_get_session_includes_empty_tags_and_notes(client):
    s = _make_session(client)
    resp = client.get(f"/sessions/{s.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tags"] == []
    assert data["notes"] is None


def test_list_sessions_includes_tags_and_notes(client):
    _make_session(client, name="Tagged")
    resp = client.get("/sessions/")
    assert resp.status_code == 200
    for row in resp.json():
        assert "tags" in row
        assert "notes" in row


def test_patch_session_notes(client):
    s = _make_session(client)
    resp = client.patch(f"/sessions/{s.id}", json={"notes": "Windy day, gimbal drift on lane 3"})
    assert resp.status_code == 200
    assert resp.json()["notes"] == "Windy day, gimbal drift on lane 3"
    # persists across reads
    assert client.get(f"/sessions/{s.id}").json()["notes"] == "Windy day, gimbal drift on lane 3"


def test_patch_session_tags(client):
    s = _make_session(client)
    resp = client.patch(f"/sessions/{s.id}", json={"tags": ["roof", "solar", "north-field"]})
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["roof", "solar", "north-field"]
    assert client.get(f"/sessions/{s.id}").json()["tags"] == ["roof", "solar", "north-field"]


def test_patch_session_tags_normalized(client):
    s = _make_session(client)
    resp = client.patch(f"/sessions/{s.id}", json={"tags": ["  roof ", "", "roof", "solar", "  "]})
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["roof", "solar"]


def test_patch_session_tag_too_long_rejected(client):
    s = _make_session(client)
    resp = client.patch(f"/sessions/{s.id}", json={"tags": ["x" * 41]})
    assert resp.status_code == 422


def test_patch_session_partial_update_preserves_other_field(client):
    s = _make_session(client)
    client.patch(f"/sessions/{s.id}", json={"tags": ["roof"]})
    resp = client.patch(f"/sessions/{s.id}", json={"notes": "note only"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["tags"] == ["roof"]
    assert data["notes"] == "note only"


def test_patch_session_clear_tags_and_notes(client):
    s = _make_session(client)
    client.patch(f"/sessions/{s.id}", json={"tags": ["roof"], "notes": "x"})
    resp = client.patch(f"/sessions/{s.id}", json={"tags": [], "notes": None})
    assert resp.status_code == 200
    data = resp.json()
    assert data["tags"] == []
    # None in the body means "no change" for notes (PATCH semantics); clearing uses ""
    assert data["notes"] == "x"
    resp = client.patch(f"/sessions/{s.id}", json={"notes": ""})
    assert resp.json()["notes"] is None


def test_patch_session_not_found(client):
    resp = client.patch("/sessions/999999", json={"tags": ["roof"]})
    assert resp.status_code == 404


def test_project_sessions_include_tags_and_notes(client):
    from backend.db.database import get_db
    from backend.db.models import Project
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())
    p = Project(name="TagProj")
    db.add(p)
    db.commit()
    db.refresh(p)
    s = SessionModel(
        name="in-project", folder_path="/tmp/test", project_id=p.id,
        photo_count=0, usable_count=0,
    )
    db.add(s)
    db.commit()
    resp = client.get(f"/projects/{p.id}/sessions")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["tags"] == []
    assert rows[0]["notes"] is None
