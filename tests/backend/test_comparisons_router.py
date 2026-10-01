from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import patch

from backend.db.models import Reconstruction, SessionComparison
from backend.db.models import Session as SessionModel


def _get_db(client):
    from backend.main import app

    return app.state.test_db_session


def _make_session(db, name="S"):
    session = SessionModel(name=name, folder_path="/tmp/s", photo_count=1, usable_count=1)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _make_reconstruction(db, session):
    rec = Reconstruction(
        session_id=session.id,
        preset="quick",
        status="complete",
        progress_pct=100.0,
        frames_used=1,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def test_create_comparison_starts_job(client):
    db = _get_db(client)
    session_a = _make_session(db, "A")
    session_b = _make_session(db, "B")
    rec_a = _make_reconstruction(db, session_a)
    rec_b = _make_reconstruction(db, session_b)
    comparison = SessionComparison(
        id=1,
        session_a_id=session_a.id,
        session_b_id=session_b.id,
        reconstruction_a_id=rec_a.id,
        reconstruction_b_id=rec_b.id,
        status="pending",
        created_at=datetime.now(UTC),
    )

    with patch(
        "backend.routers.comparisons.start_session_comparison",
        return_value=comparison,
    ) as mock_start:
        resp = client.post(
            "/comparisons",
            json={
                "session_a_id": session_a.id,
                "session_b_id": session_b.id,
                "reconstruction_a_id": rec_a.id,
                "reconstruction_b_id": rec_b.id,
                "voxel_size_m": 1.0,
            },
        )

    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"
    mock_start.assert_called_once()


def test_get_comparison(client):
    db = _get_db(client)
    session_a = _make_session(db, "A")
    session_b = _make_session(db, "B")
    rec_a = _make_reconstruction(db, session_a)
    rec_b = _make_reconstruction(db, session_b)
    comparison = SessionComparison(
        session_a_id=session_a.id,
        session_b_id=session_b.id,
        reconstruction_a_id=rec_a.id,
        reconstruction_b_id=rec_b.id,
        status="running",
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)

    resp = client.get(f"/comparisons/{comparison.id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_get_diff_returns_json(client, tmp_path):
    db = _get_db(client)
    session_a = _make_session(db, "A")
    session_b = _make_session(db, "B")
    rec_a = _make_reconstruction(db, session_a)
    rec_b = _make_reconstruction(db, session_b)
    diff_path = tmp_path / "diff.json"
    diff = {
        "utm_zone": "17N",
        "summary": {"new_count": 1, "removed_count": 0},
        "new": [{"x": 500000, "y": 3900000, "z": 0, "size": 1.0}],
        "removed": [],
    }
    diff_path.write_text(json.dumps(diff), encoding="utf-8")
    comparison = SessionComparison(
        session_a_id=session_a.id,
        session_b_id=session_b.id,
        reconstruction_a_id=rec_a.id,
        reconstruction_b_id=rec_b.id,
        status="complete",
        diff_path=str(diff_path),
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)

    resp = client.get(f"/comparisons/{comparison.id}/diff")
    assert resp.status_code == 200
    assert resp.json()["summary"]["new_count"] == 1


def test_get_diff_geojson_returns_feature_collection(client, tmp_path):
    db = _get_db(client)
    session_a = _make_session(db, "A")
    session_b = _make_session(db, "B")
    rec_a = _make_reconstruction(db, session_a)
    rec_b = _make_reconstruction(db, session_b)
    diff_path = tmp_path / "diff.json"
    diff_path.write_text(
        json.dumps({
            "utm_zone": "17N",
            "summary": {"new_count": 1, "removed_count": 0},
            "new": [{"x": 500000, "y": 3900000, "z": 0, "size": 1.0}],
            "removed": [],
        }),
        encoding="utf-8",
    )
    comparison = SessionComparison(
        session_a_id=session_a.id,
        session_b_id=session_b.id,
        reconstruction_a_id=rec_a.id,
        reconstruction_b_id=rec_b.id,
        status="complete",
        diff_path=str(diff_path),
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)

    resp = client.get(f"/comparisons/{comparison.id}/diff.geojson")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/geo+json"
    assert resp.json()["type"] == "FeatureCollection"


def test_get_diff_still_running_returns_202(client):
    db = _get_db(client)
    session_a = _make_session(db, "A")
    session_b = _make_session(db, "B")
    rec_a = _make_reconstruction(db, session_a)
    rec_b = _make_reconstruction(db, session_b)
    comparison = SessionComparison(
        session_a_id=session_a.id,
        session_b_id=session_b.id,
        reconstruction_a_id=rec_a.id,
        reconstruction_b_id=rec_b.id,
        status="running",
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)

    resp = client.get(f"/comparisons/{comparison.id}/diff")
    assert resp.status_code == 202


# ---- deleting a comparison unblocks its reconstructions (issue #945) ----


def _storage(tmp_path):
    return type("Cfg", (), {
        "processed_dir": str(tmp_path / "processed"),
        "exports_dir": str(tmp_path / "exports"),
        "data_dir": str(tmp_path / "data"),
    })()


def _complete_comparison(db, tmp_path):
    session_a = _make_session(db, "A")
    session_b = _make_session(db, "B")
    rec_a = _make_reconstruction(db, session_a)
    rec_b = _make_reconstruction(db, session_b)
    comparison = SessionComparison(
        session_a_id=session_a.id,
        session_b_id=session_b.id,
        reconstruction_a_id=rec_a.id,
        reconstruction_b_id=rec_b.id,
        status="complete",
    )
    db.add(comparison)
    db.commit()
    diff = tmp_path / "exports" / "comparisons" / str(comparison.id) / "diff.json"
    diff.parent.mkdir(parents=True)
    diff.write_text("{}", encoding="utf-8")
    comparison.diff_path = str(diff)
    db.commit()
    return comparison, rec_a, diff


def test_delete_comparison_removes_the_row_then_its_diff_and_unblocks_its_reconstructions(
    client, tmp_path
):
    db = _get_db(client)
    comparison, rec_a, diff = _complete_comparison(db, tmp_path)

    with patch("backend.routers.reconstruction.get_config", return_value=_storage(tmp_path)):
        assert client.delete(f"/reconstruction/{rec_a.id}").status_code == 409
    with patch("backend.routers.comparisons.get_config", return_value=_storage(tmp_path)):
        resp = client.delete(f"/comparisons/{comparison.id}")

    assert resp.status_code == 200
    assert not diff.parent.exists()
    assert client.get(f"/comparisons/{comparison.id}").status_code == 404
    with patch("backend.routers.reconstruction.get_config", return_value=_storage(tmp_path)):
        assert client.delete(f"/reconstruction/{rec_a.id}").status_code == 200


def test_delete_comparison_refuses_while_its_job_is_queued(client, tmp_path):
    from backend.services.job_queue import SESSION_COMPARISON, enqueue

    db = _get_db(client)
    comparison, _rec_a, diff = _complete_comparison(db, tmp_path)
    enqueue(SESSION_COMPARISON, comparison.id)

    with patch("backend.routers.comparisons.get_config", return_value=_storage(tmp_path)):
        resp = client.delete(f"/comparisons/{comparison.id}")

    assert resp.status_code == 409
    assert diff.exists()
    assert client.get(f"/comparisons/{comparison.id}").status_code == 200


def test_delete_missing_comparison_returns_404(client):
    assert client.delete("/comparisons/999999").status_code == 404
