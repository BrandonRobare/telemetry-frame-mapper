from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from PIL import Image as PILImage

from backend.db.models import CoverageRun, Image, Project, Reconstruction, TargetArea
from backend.db.models import Session as SessionModel


def test_list_projects_empty(client):
    resp = client.get("/projects/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_project(client):
    resp = client.post("/projects/", json={"name": "Test Site", "description": "A test project"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Site"
    assert data["description"] == "A test project"
    assert data["session_count"] == 0
    assert "id" in data


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "/absolute",
        "..",
        "./dot",
        "site/name",
        r"site\\name",
        "C:site",
        r"C:\\site",
        r"\\\\server\\share",
    ],
)
def test_create_project_rejects_unsafe_filesystem_names(client, name):
    response = client.post("/projects/", json={"name": name})

    assert response.status_code == 422


def test_create_project_keeps_human_readable_name(client):
    response = client.post("/projects/", json={"name": "North Field — Phase 2"})

    assert response.status_code == 201
    assert response.json()["name"] == "North Field — Phase 2"


def test_project_folder_import_processes_nested_images(client, tmp_path):
    """Project folder imports invoke the shared recursive ingest service."""
    from backend.main import app
    from backend.services.ingest_orchestrator import _run
    from tests.conftest import TestSessionLocal

    db = app.state.test_db_session
    project = Project(name="Nested project")
    db.add(project)
    db.commit()
    imports_dir = tmp_path / "imports"
    nested = imports_dir / "Nested project" / "card" / "DCIM" / "100MEDIA"
    nested.mkdir(parents=True)
    PILImage.new("RGB", (100, 100)).save(nested / "DJI_0001.jpg")
    cfg = type("Cfg", (), {"imports_dir": str(imports_dir)})()
    ingest_cfg = {
        "accepted_extensions": [".jpg"],
        "filter_zero_gps": False,
        "thumbnail_size_px": 64,
    }

    with patch("backend.routers.projects.get_config", return_value=cfg), patch(
        "backend.core.config.get_ingest_config", return_value=ingest_cfg
    ), patch("backend.core.config.load_config") as mock_load_cfg, patch(
        "backend.routers.projects.start_import",
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
            f"/projects/{project.id}/sessions/import",
            json={"folder_path": "card", "name": "Nested card"},
        )

    assert response.status_code == 200
    assert db.query(Image).filter(Image.session_id == response.json()["id"]).count() == 1


def test_list_projects_after_create(client):
    client.post("/projects/", json={"name": "Site A"})
    client.post("/projects/", json={"name": "Site B"})
    resp = client.get("/projects/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = {p["name"] for p in data}
    assert "Site A" in names
    assert "Site B" in names
    # Most recent first (Site B created after Site A).
    assert data[0]["name"] == "Site B"


def test_create_project_duplicate(client):
    client.post("/projects/", json={"name": "Dup"})
    resp = client.post("/projects/", json={"name": "Dup"})
    assert resp.status_code == 409


def test_get_project(client):
    create = client.post("/projects/", json={"name": "Single"})
    pid = create.json()["id"]

    resp = client.get(f"/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Single"


def test_get_project_not_found(client):
    resp = client.get("/projects/99999")
    assert resp.status_code == 404


def test_delete_project(client):
    create = client.post("/projects/", json={"name": "ToDelete"})
    pid = create.json()["id"]

    resp = client.delete(f"/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    resp = client.get(f"/projects/{pid}")
    assert resp.status_code == 404


def test_delete_project_cancels_every_child_job_and_removes_artifacts(client, tmp_path):
    from backend.main import app

    db = app.state.test_db_session
    processed_dir = tmp_path / "processed"
    exports_dir = tmp_path / "exports"
    data_dir = tmp_path / "data"
    project = Project(name="Delete artifacts")
    db.add(project)
    db.commit()

    sessions = [
        SessionModel(name="First", folder_path="/tmp/first", project_id=project.id),
        SessionModel(name="Second", folder_path="/tmp/second", project_id=project.id),
    ]
    db.add_all(sessions)
    db.commit()
    for session in sessions:
        db.refresh(session)
    session_ids = [session.id for session in sessions]

    paths = []
    rec_ids = []
    for session in sessions:
        thumb = processed_dir / str(session.id) / "thumbs" / "frame.jpg"
        thumb.parent.mkdir(parents=True, exist_ok=True)
        thumb.write_bytes(b"thumb")
        workspace = data_dir / "colmap" / str(session.id)
        workspace.mkdir(parents=True)
        export = exports_dir / str(session.id) / "splat.ply"
        export.parent.mkdir(parents=True)
        export.write_bytes(b"splat")
        db.add(
            Image(
                session_id=session.id,
                filename="frame.jpg",
                filepath="/tmp/frame.jpg",
                thumb_path=str(thumb),
            )
        )
        rec = Reconstruction(
            session_id=session.id,
            status="running",
            preset="quick",
            colmap_dir=str(workspace),
            splat_path=str(export),
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        rec_ids.append(rec.id)
        paths.extend([thumb, workspace, export.parent])

    cfg = type("Cfg", (), {
        "processed_dir": str(processed_dir),
        "exports_dir": str(exports_dir),
        "data_dir": str(data_dir),
    })()
    with patch("backend.routers.sessions.get_config", return_value=cfg), patch(
        "backend.routers.sessions.cancel_reconstruction"
    ) as cancel:
        response = client.delete(f"/projects/{project.id}")

    assert response.status_code == 200
    assert cancel.call_args_list == [((rec_id,),) for rec_id in rec_ids]
    assert all(not path.exists() for path in paths)
    assert db.query(Project).filter(Project.id == project.id).first() is None
    assert db.query(SessionModel).filter(SessionModel.id.in_(session_ids)).count() == 0


def test_delete_project_keeps_database_rows_when_child_cleanup_fails(client):
    from backend.main import app

    db = app.state.test_db_session
    project = Project(name="Cleanup failure")
    db.add(project)
    db.commit()
    session = SessionModel(name="Child", folder_path="/tmp/child", project_id=project.id)
    db.add(session)
    db.commit()

    with patch(
        "backend.routers.sessions.cleanup_session_artifacts", side_effect=OSError("disk failed")
    ):
        response = client.delete(f"/projects/{project.id}")

    assert response.status_code == 500
    assert "database unchanged" in response.json()["detail"]
    assert db.query(Project).filter(Project.id == project.id).first() is not None
    assert db.query(SessionModel).filter(SessionModel.id == session.id).first() is not None


def test_project_import_rejects_unsafe_legacy_project_name_before_path_use(client, tmp_path):
    from backend.main import app

    db = app.state.test_db_session
    project = Project(name="../legacy")
    db.add(project)
    db.commit()

    cfg = type("Cfg", (), {"imports_dir": str(tmp_path / "imports")})()
    with patch("backend.routers.projects.get_config", return_value=cfg), patch(
        "backend.routers.projects.start_import"
    ):
        response = client.post(
            f"/projects/{project.id}/sessions/import",
            json={"folder_path": "flight", "name": "Unsafe legacy"},
        )

    assert response.status_code == 400
    assert "Project name" in response.json()["detail"]


def test_project_import_preserves_confined_flat_legacy_fallback(client, tmp_path):
    from backend.main import app

    db = app.state.test_db_session
    project = Project(name="Safe project")
    db.add(project)
    db.commit()
    imports_dir = tmp_path / "imports"
    legacy_folder = imports_dir / "legacy" / "flight"
    legacy_folder.mkdir(parents=True)

    cfg = type("Cfg", (), {"imports_dir": str(imports_dir)})()
    with patch("backend.routers.projects.get_config", return_value=cfg), patch(
        "backend.routers.projects.start_import"
    ):
        response = client.post(
            f"/projects/{project.id}/sessions/import",
            json={"folder_path": "legacy/flight", "name": "Legacy import"},
        )

    assert response.status_code == 200
    assert response.json()["folder_path"] == str(legacy_folder.resolve())


def test_project_session_count(client):
    """session_count field is computed, not a column."""
    create = client.post("/projects/", json={"name": "Counted"})
    pid = create.json()["id"]

    resp = client.get(f"/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json()["session_count"] == 0


def test_list_project_sessions_empty(client):
    create = client.post("/projects/", json={"name": "EmptySessions"})
    pid = create.json()["id"]

    resp = client.get(f"/projects/{pid}/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_project_trends_are_time_ordered_and_project_scoped(client):
    from backend.main import app

    db = app.state.test_db_session
    project = Project(name="Trend site")
    other_project = Project(name="Other site")
    target = TargetArea(name="Trend target")
    db.add_all([project, other_project, target])
    db.commit()

    later = SessionModel(
        name="Later flight",
        folder_path="/tmp/later",
        project_id=project.id,
        imported_at=datetime(2026, 7, 2, tzinfo=UTC),
        photo_count=10,
        usable_count=9,
    )
    earlier = SessionModel(
        name="Earlier flight",
        folder_path="/tmp/earlier",
        project_id=project.id,
        imported_at=datetime(2026, 7, 1, tzinfo=UTC),
        photo_count=0,
        usable_count=0,
    )
    same_day = SessionModel(
        name="Same-day flight",
        folder_path="/tmp/same-day",
        project_id=project.id,
        imported_at=datetime(2026, 7, 1, tzinfo=UTC),
        photo_count=4,
        usable_count=4,
    )
    foreign = SessionModel(
        name="Foreign flight",
        folder_path="/tmp/foreign",
        project_id=other_project.id,
        imported_at=datetime(2026, 6, 1, tzinfo=UTC),
        photo_count=50,
        usable_count=50,
    )
    db.add_all([later, earlier, same_day, foreign])
    db.commit()

    db.add_all([
        Reconstruction(
            session_id=later.id,
            status="complete",
            preset="quick",
            frames_used=10,
            frames_registered=8,
            psnr=29.0,
            ssim=0.89,
            completed_at=datetime(2026, 7, 2, 12, tzinfo=UTC),
        ),
        Reconstruction(
            session_id=later.id,
            status="complete",
            preset="full",
            frames_used=10,
            frames_registered=9,
            psnr=31.5,
            ssim=0.93,
            completed_at=datetime(2026, 7, 3, 12, tzinfo=UTC),
        ),
        Reconstruction(
            session_id=foreign.id,
            status="complete",
            preset="full",
            frames_used=50,
            frames_registered=50,
            psnr=99.0,
            ssim=0.99,
            completed_at=datetime(2026, 7, 4, tzinfo=UTC),
        ),
        CoverageRun(
            target_area_id=target.id,
            session_ids=str(later.id),
            coverage_pct=71.0,
            run_at=datetime(2026, 7, 2, tzinfo=UTC),
        ),
        CoverageRun(
            target_area_id=target.id,
            session_ids=str(later.id),
            coverage_pct=84.5,
            run_at=datetime(2026, 7, 3, tzinfo=UTC),
        ),
        CoverageRun(
            target_area_id=target.id,
            session_ids=str(foreign.id),
            coverage_pct=100.0,
            run_at=datetime(2026, 7, 4, tzinfo=UTC),
        ),
    ])
    db.commit()

    response = client.get(f"/projects/{project.id}/trends")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project.id
    assert [point["session_id"] for point in body["points"]] == [
        earlier.id,
        same_day.id,
        later.id,
    ]
    assert body["points"][0]["usable_pct"] is None
    assert body["points"][0]["coverage_pct"] is None
    assert body["points"][0]["psnr"] is None
    latest = body["points"][2]
    assert latest["session_name"] == "Later flight"
    assert latest["usable_pct"] == 90.0
    assert latest["coverage_pct"] == 84.5
    assert latest["reconstruction_id"] is not None
    assert latest["frames_registered"] == 9
    assert latest["psnr"] == 31.5
    assert latest["ssim"] == 0.93


def test_project_trends_rejects_unknown_project(client):
    response = client.get("/projects/99999/trends")

    assert response.status_code == 404
