from __future__ import annotations

import logging
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from PIL import Image as PILImage

from backend.db.models import (
    AutoImportRecord,
    Defect,
    DefectImage,
    Image,
    Reconstruction,
    SessionComparison,
    SessionLogEntry,
)
from backend.db.models import Session as SessionModel
from backend.routers.sessions import _ensure_session_search_schema


def _make_session(client, name="Test Session"):
    from backend.main import app
    db = app.state.test_db_session
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


def test_session_folder_import_processes_nested_images(client, tmp_path):
    """Server-side session imports use the same recursive ingest service as uploads."""
    from backend.db.models import Image
    from backend.main import app
    from backend.services.ingest_orchestrator import _run
    from tests.conftest import TestSessionLocal

    imports_dir = tmp_path / "imports"
    nested = imports_dir / "card" / "DCIM" / "100MEDIA"
    nested.mkdir(parents=True)
    PILImage.new("RGB", (100, 100)).save(nested / "DJI_0001.jpg")
    cfg = type("Cfg", (), {"imports_dir": str(imports_dir)})()
    ingest_cfg = {
        "accepted_extensions": [".jpg"],
        "filter_zero_gps": False,
        "thumbnail_size_px": 64,
    }

    with patch("backend.routers.sessions.get_config", return_value=cfg), patch(
        "backend.core.config.get_ingest_config", return_value=ingest_cfg
    ), patch("backend.core.config.load_config") as mock_load_cfg, patch(
        "backend.routers.sessions.start_import",
        side_effect=lambda session_id, folder, _db_factory: _run(
            session_id, folder, TestSessionLocal
        ),
    ):
        mock_load_cfg.return_value.processed_dir = str(tmp_path / "processed")
        mock_load_cfg.return_value.thumbnail_size_px = 64
        mock_load_cfg.return_value.fov_horizontal_deg = 83
        mock_load_cfg.return_value.fov_vertical_deg = 53
        mock_load_cfg.return_value.target_crs = "EPSG:32617"
        response = client.post(
            "/sessions/import", json={"folder_path": "card", "name": "Nested card"}
        )

    assert response.status_code == 200
    db = app.state.test_db_session
    assert db.query(Image).filter(Image.session_id == response.json()["id"]).count() == 1


def test_delete_session(client):
    s = _make_session(client, name="ToDelete")
    resp = client.delete(f"/sessions/{s.id}")
    assert resp.status_code == 200
    assert client.get(f"/sessions/{s.id}").status_code == 404


def test_delete_session_not_found(client):
    resp = client.delete("/sessions/999999")
    assert resp.status_code == 404


def test_delete_session_removes_thumbnails_and_reconstruction_artifacts(client, tmp_path):
    from backend.main import app
    db = app.state.test_db_session

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


# ---- foreign-key-safe deletes (issue #945) ----


def _storage(tmp_path):
    return type("Cfg", (), {
        "processed_dir": str(tmp_path / "processed"),
        "exports_dir": str(tmp_path / "exports"),
        "data_dir": str(tmp_path / "data"),
    })()


def _session_with_thumb(db, tmp_path, name):
    s = SessionModel(name=name, folder_path="/tmp/test", photo_count=1, usable_count=1)
    db.add(s)
    db.commit()
    thumb = tmp_path / "processed" / str(s.id) / "thumbs" / "frame.jpg"
    thumb.parent.mkdir(parents=True)
    thumb.write_bytes(b"thumb")
    image = Image(
        session_id=s.id, filename="frame.jpg", filepath="/tmp/test/frame.jpg",
        thumb_path=str(thumb),
    )
    db.add(image)
    db.commit()
    return s, image, thumb


def _complete_reconstruction(db, tmp_path, session_id):
    rec = Reconstruction(session_id=session_id, status="complete", preset="quick")
    db.add(rec)
    db.commit()
    splat = tmp_path / "exports" / str(rec.id) / "splat.ply"
    splat.parent.mkdir(parents=True)
    splat.write_bytes(b"splat")
    rec.splat_path = str(splat)
    db.commit()
    return rec, splat


def test_deleting_an_auto_imported_session_detaches_its_import_claim(client, tmp_path):
    from backend.main import app
    db = app.state.test_db_session
    s, _image, thumb = _session_with_thumb(db, tmp_path, "Watch folder import")
    session_id = s.id
    db.add(AutoImportRecord(fingerprint="card-1", source_path="/media/card", session_id=s.id))
    db.commit()

    with patch("backend.routers.sessions.get_config", return_value=_storage(tmp_path)):
        response = client.delete(f"/sessions/{session_id}")

    assert response.status_code == 200
    assert not thumb.exists()
    db.expire_all()
    assert db.get(SessionModel, session_id) is None
    # The claim outlives the session so the watcher does not import the folder again.
    claim = db.query(AutoImportRecord).one()
    assert (claim.fingerprint, claim.session_id) == ("card-1", None)


def test_deleting_a_compared_session_returns_409_and_keeps_everything(client, tmp_path):
    from backend.main import app
    db = app.state.test_db_session
    s, _image, thumb = _session_with_thumb(db, tmp_path, "Compared")
    other = _make_session(client, name="Other side")
    rec, splat = _complete_reconstruction(db, tmp_path, s.id)
    other_rec, _ = _complete_reconstruction(db, tmp_path, other.id)
    comparison = SessionComparison(
        session_a_id=s.id, session_b_id=other.id,
        reconstruction_a_id=rec.id, reconstruction_b_id=other_rec.id,
    )
    db.add(comparison)
    db.commit()

    with patch("backend.routers.sessions.get_config", return_value=_storage(tmp_path)), \
         patch("backend.routers.sessions.cancel_reconstruction") as cancel:
        response = client.delete(f"/sessions/{s.id}")

    assert response.status_code == 409
    body = response.json()
    assert f"comparison {comparison.id}" in body["detail"]
    assert body["blocking_references"] == [{
        "type": "comparison", "id": comparison.id,
        "session_a_id": s.id, "session_b_id": other.id,
        "reconstruction_a_id": rec.id, "reconstruction_b_id": other_rec.id,
    }]
    cancel.assert_not_called()
    assert thumb.exists()
    assert splat.exists()
    db.expire_all()
    assert db.get(SessionModel, s.id) is not None
    assert db.get(SessionComparison, comparison.id) is not None


def test_session_delete_keeps_files_when_the_database_refuses_it(client, tmp_path):
    """A foreign key the pre-checks do not cover must still leave the files in place."""
    from backend.main import app
    db = app.state.test_db_session
    s, image, thumb = _session_with_thumb(db, tmp_path, "Linked from elsewhere")
    rec, splat = _complete_reconstruction(db, tmp_path, s.id)
    other = _make_session(client, name="Holds the defect")
    defect = Defect(session_id=other.id, category="crack")
    db.add(defect)
    db.commit()
    db.add(DefectImage(defect_id=defect.id, image_id=image.id))
    db.commit()

    with patch("backend.routers.sessions.get_config", return_value=_storage(tmp_path)), \
         patch("backend.routers.sessions.cancel_reconstruction"):
        response = client.delete(f"/sessions/{s.id}")

    assert response.status_code == 409
    assert "nothing was deleted" in response.json()["detail"]
    assert thumb.exists()
    assert splat.exists()
    db.expire_all()
    assert db.get(SessionModel, s.id) is not None
    assert db.get(Reconstruction, rec.id) is not None


def test_session_delete_removes_files_only_after_the_commit(client, tmp_path):
    from backend.main import app
    from backend.services.artifact_cleanup import remove_artifacts
    from tests.conftest import TestSessionLocal
    db = app.state.test_db_session
    s, _image, thumb = _session_with_thumb(db, tmp_path, "Ordered delete")
    session_id = s.id
    seen: list[bool] = []

    def cleanup(paths, cfg):
        with TestSessionLocal() as other:
            seen.append(other.get(SessionModel, session_id) is None)
        return remove_artifacts(paths, cfg)

    with patch("backend.routers.sessions.get_config", return_value=_storage(tmp_path)), \
         patch("backend.routers.sessions.remove_artifacts", side_effect=cleanup):
        response = client.delete(f"/sessions/{session_id}")

    assert response.status_code == 200
    assert seen == [True]
    assert not thumb.exists()


def test_session_delete_succeeds_when_file_cleanup_fails_after_the_commit(
    client, tmp_path, caplog
):
    from backend.main import app
    db = app.state.test_db_session
    s, _image, thumb = _session_with_thumb(db, tmp_path, "Stubborn files")
    session_id = s.id

    with patch("backend.routers.sessions.get_config", return_value=_storage(tmp_path)), \
         patch("backend.services.artifact_cleanup.shutil.rmtree", side_effect=OSError("busy")), \
         caplog.at_level(logging.WARNING, logger="backend.services.artifact_cleanup"):
        response = client.delete(f"/sessions/{session_id}")

    assert response.status_code == 200
    db.expire_all()
    assert db.get(SessionModel, session_id) is None
    assert thumb.parent.exists()
    assert "busy" in caplog.text


def test_bulk_delete_reports_a_compared_session_and_deletes_the_rest(client, tmp_path):
    from backend.main import app
    db = app.state.test_db_session
    compared, _image, compared_thumb = _session_with_thumb(db, tmp_path, "Compared")
    free, _image, free_thumb = _session_with_thumb(db, tmp_path, "Free")
    rec_a, _ = _complete_reconstruction(db, tmp_path, compared.id)
    rec_b, _ = _complete_reconstruction(db, tmp_path, compared.id)
    comparison = SessionComparison(
        session_a_id=compared.id, session_b_id=compared.id,
        reconstruction_a_id=rec_a.id, reconstruction_b_id=rec_b.id,
    )
    db.add(comparison)
    db.commit()

    with patch("backend.routers.sessions.get_config", return_value=_storage(tmp_path)), \
         patch("backend.routers.sessions.cancel_reconstruction"):
        response = client.post(
            "/sessions/bulk",
            json={
                "session_ids": [compared.id, free.id],
                "operation": "delete",
                "confirm": "DELETE",
            },
        )

    assert response.status_code == 200
    blocked, deleted = response.json()["outcomes"]
    assert blocked["ok"] is False
    assert f"comparison {comparison.id}" in blocked["error"]
    assert deleted["ok"] is True
    assert compared_thumb.exists()
    assert not free_thumb.exists()


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


# ---- bulk operations (issue #391) ----


def test_bulk_assign_project_and_update_tags(client):
    project = client.post("/projects/", json={"name": "Bulk Site"}).json()
    first = _make_session(client, name="First")
    second = _make_session(client, name="Second")
    client.patch(f"/sessions/{first.id}", json={"tags": ["roof"]})

    assigned = client.post(
        "/sessions/bulk",
        json={
            "session_ids": [first.id, second.id],
            "operation": "assign_project",
            "project_id": project["id"],
        },
    )
    assert assigned.status_code == 200
    assert [outcome["ok"] for outcome in assigned.json()["outcomes"]] == [True, True]

    added = client.post(
        "/sessions/bulk",
        json={
            "session_ids": [first.id, second.id],
            "operation": "add_tags",
            "tags": [" solar ", "roof"],
        },
    )
    assert added.status_code == 200
    assert client.get(f"/sessions/{first.id}").json()["tags"] == ["roof", "solar"]
    assert client.get(f"/sessions/{second.id}").json()["tags"] == ["solar", "roof"]

    replaced = client.post(
        "/sessions/bulk",
        json={"session_ids": [first.id, second.id], "operation": "replace_tags", "tags": ["north"]},
    )
    assert replaced.status_code == 200
    assert client.get(f"/sessions/{first.id}").json()["tags"] == ["north"]
    assert client.get(f"/sessions/{second.id}").json()["project_id"] == project["id"]


def test_bulk_reports_missing_and_failed_archives_without_hiding_successes(client, tmp_path):
    first = _make_session(client, name="Archive first")
    second = _make_session(client, name="Archive second")

    def build_archive(zip_path, session, _db):
        if session.id == second.id:
            raise OSError("disk full")
        return {"bundle_path": str(zip_path)}

    cfg = type("Cfg", (), {"exports_dir": str(tmp_path / "exports")})()
    with (
        patch("backend.routers.sessions.get_config", return_value=cfg),
        patch("backend.services.session_bundle.build_session_archive", side_effect=build_archive),
    ):
        response = client.post(
            "/sessions/bulk",
            json={"session_ids": [first.id, 999999, second.id], "operation": "archive"},
        )

    assert response.status_code == 200
    outcomes = response.json()["outcomes"]
    assert outcomes == [
        {
            "session_id": first.id,
            "ok": True,
            "error": None,
            "bundle_path": str(tmp_path / "exports" / f"session_{first.id}_archive.zip"),
        },
        {"session_id": 999999, "ok": False, "error": "Session not found", "bundle_path": None},
        {"session_id": second.id, "ok": False, "error": "disk full", "bundle_path": None},
    ]


def test_bulk_delete_requires_confirmation_and_deletes_each_selected_session(client):
    first = _make_session(client, name="Delete first")
    second = _make_session(client, name="Delete second")

    rejected = client.post(
        "/sessions/bulk",
        json={"session_ids": [first.id], "operation": "delete", "confirm": "yes"},
    )
    assert rejected.status_code == 422
    assert client.get(f"/sessions/{first.id}").status_code == 200

    deleted = client.post(
        "/sessions/bulk",
        json={"session_ids": [first.id, second.id], "operation": "delete", "confirm": "DELETE"},
    )
    assert deleted.status_code == 200
    assert [outcome["ok"] for outcome in deleted.json()["outcomes"]] == [True, True]
    assert client.get(f"/sessions/{first.id}").status_code == 404
    assert client.get(f"/sessions/{second.id}").status_code == 404


def test_bulk_validates_ids_and_project(client):
    invalid_ids = client.post(
        "/sessions/bulk", json={"session_ids": [0, 0], "operation": "archive"}
    )
    assert invalid_ids.status_code == 422

    missing_project = client.post(
        "/sessions/bulk",
        json={"session_ids": [1], "operation": "assign_project", "project_id": 999999},
    )
    assert missing_project.status_code == 404


# ---- cross-session search (issue #390) ----


def test_search_rejects_non_sqlite_dialect_before_running_fts_sql():
    db = Mock()
    db.get_bind.return_value.dialect.name = "postgresql"

    with pytest.raises(HTTPException) as exc:
        _ensure_session_search_schema(db)

    assert exc.value.status_code == 501
    assert "SQLite FTS5" in exc.value.detail
    db.execute.assert_not_called()


def test_search_sessions_indexes_metadata_logs_and_defects(client):
    s = _make_session(client, name="Riverside roof survey")
    client.patch(f"/sessions/{s.id}", json={"tags": ["solar"], "notes": "Windy west elevation"})

    assert client.get("/sessions/search", params={"q": "riverside"}).json()[0]["id"] == s.id
    tag_hit = client.get("/sessions/search", params={"q": "solar"}).json()[0]
    assert tag_hit["matches"][0]["source"] == "session"
    assert "solar" in tag_hit["matches"][0]["snippet"].lower()
    assert client.get("/sessions/search", params={"q": "windy"}).json()[0]["id"] == s.id

    from backend.main import app

    db = app.state.test_db_session
    db.add(
        SessionLogEntry(session_id=s.id, event_type="import_complete", message="Tree obstruction")
    )
    db.add(Defect(session_id=s.id, category="crack", severity="high", note="North parapet crack"))
    db.commit()

    log_hit = client.get("/sessions/search", params={"q": "obstruction"}).json()[0]
    assert log_hit["id"] == s.id
    assert log_hit["matches"][0]["source"] == "log"
    defect_hit = client.get(
        "/sessions/search", params={"q": "parapet", "source": "defect"}
    ).json()[0]
    assert defect_hit["matches"][0]["source"] == "defect"


def test_search_sessions_groups_results_and_rejects_punctuation_only_query(client):
    first = _make_session(client, name="North roof")
    second = _make_session(client, name="South roof")

    response = client.get("/sessions/search", params={"q": "roof"})
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [first.id, second.id]

    invalid = client.get("/sessions/search", params={"q": "---"})
    assert invalid.status_code == 422


def test_project_sessions_include_tags_and_notes(client):
    from backend.db.models import Project
    from backend.main import app
    db = app.state.test_db_session
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


def test_list_sessions_survives_a_null_folder_path(client):
    """Regression test for #795: a legacy row with a NULL ``folder_path`` used to fail
    ``list[SessionOut]`` serialization and take down the whole listing, not just itself.

    The app's own creation paths always write a string, so insert the bad row directly.
    """
    from backend.main import app

    good = _make_session(client, name="Has a path")
    db = app.state.test_db_session
    bad = SessionModel(name="No path", folder_path=None, photo_count=0, usable_count=0)
    db.add(bad)
    db.commit()
    db.refresh(bad)

    resp = client.get("/sessions/")
    assert resp.status_code == 200
    by_id = {row["id"]: row for row in resp.json()}
    assert good.id in by_id
    assert by_id[bad.id]["folder_path"] is None
