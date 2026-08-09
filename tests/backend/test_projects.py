from __future__ import annotations

from datetime import UTC, datetime

from backend.db.models import CoverageRun, Project, Reconstruction, TargetArea
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
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
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
