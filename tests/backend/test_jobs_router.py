from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.db.database import get_db
from backend.db.models import Reconstruction
from backend.db.models import Session as SessionModel
from backend.main import app


@pytest.fixture
def client(setup_test_db):
    with TestClient(app) as c:
        yield c


def _get_db(client):  # noqa: ARG001
    return next(app.dependency_overrides[get_db]())


def _make_session(db):
    s = SessionModel(name="Test", folder_path="/tmp/test", import_mode="copy")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_list_jobs_empty(client):
    resp = client.get("/jobs/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_jobs_returns_reconstruction_shape(client):
    db = _get_db(client)
    s = _make_session(db)
    rec = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="complete",
        progress_pct=100.0,
        frames_used=5,
    )
    db.add(rec)
    db.commit()

    resp = client.get("/jobs/")
    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) == 1
    job = jobs[0]
    assert job["type"] == "reconstruction"
    assert job["status"] == "complete"
    assert job["session_id"] == s.id
    assert job["preset"] == "quick"
    assert job["frames_used"] == 5
    assert job["progress_pct"] == 100.0
    for field in ["id", "step", "started_at", "completed_at", "error_msg"]:
        assert field in job


def test_list_jobs_orders_by_started_at_desc(client):
    db = _get_db(client)
    s = _make_session(db)
    base = datetime.now(timezone.utc)
    recs = []
    for i in range(3):
        rec = Reconstruction(
            session_id=s.id,
            preset="quick",
            status="complete",
            progress_pct=100.0,
            frames_used=i + 1,
            started_at=base + timedelta(seconds=i),
        )
        db.add(rec)
        recs.append(rec)
    db.commit()
    for r in recs:
        db.refresh(r)

    resp = client.get("/jobs/")
    jobs = resp.json()
    session_jobs = [j for j in jobs if j["session_id"] == s.id]
    assert len(session_jobs) == 3
    ids = [j["id"] for j in session_jobs]
    assert ids == sorted(ids, reverse=True)
