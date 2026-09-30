from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

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


# A solved COLMAP->UTM transform (yawed 90 degrees, scaled 3x, shifted) in zone 17N.
_GEO_TRANSFORM = json.dumps({
    "scale": 3.0,
    "rotation": [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
    "translation": [12.0, -4.0, 30.0],
    "utm_zone": "17N",
    "utm_origin": [591253.0, 3873500.0],
})


def _make_reconstruction(db, session, geo_transform=None):
    rec = Reconstruction(
        session_id=session.id,
        preset="quick",
        status="complete",
        progress_pct=100.0,
        frames_used=1,
        geo_transform=geo_transform,
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


@pytest.mark.parametrize("ungeoreferenced", ["a", "b", "both"])
def test_create_comparison_refuses_reconstruction_without_geo_transform(client, ungeoreferenced):
    """NULL geo_transform = not georeferenced: its voxels are in COLMAP's arbitrary frame (#950)."""
    db = _get_db(client)
    session_a = _make_session(db, "A")
    session_b = _make_session(db, "B")
    geo_a = None if ungeoreferenced in {"a", "both"} else _GEO_TRANSFORM
    geo_b = None if ungeoreferenced in {"b", "both"} else _GEO_TRANSFORM
    rec_a = _make_reconstruction(db, session_a, geo_transform=geo_a)
    rec_b = _make_reconstruction(db, session_b, geo_transform=geo_b)
    ungeoreferenced_id = rec_b.id if ungeoreferenced == "b" else rec_a.id

    with patch("backend.services.reconstruction.enqueue") as mock_enqueue:
        resp = client.post(
            "/comparisons",
            json={
                "session_a_id": session_a.id,
                "session_b_id": session_b.id,
                "reconstruction_a_id": rec_a.id,
                "reconstruction_b_id": rec_b.id,
            },
        )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert f"reconstruction {ungeoreferenced_id} is not georeferenced" in detail.lower()
    mock_enqueue.assert_not_called()
    assert db.query(SessionComparison).count() == 0


def test_create_comparison_of_georeferenced_reconstructions_is_queued(client):
    db = _get_db(client)
    session_a = _make_session(db, "A")
    session_b = _make_session(db, "B")
    rec_a = _make_reconstruction(db, session_a, geo_transform=_GEO_TRANSFORM)
    rec_b = _make_reconstruction(db, session_b, geo_transform=_GEO_TRANSFORM)

    with patch("backend.services.reconstruction.enqueue") as mock_enqueue:
        resp = client.post(
            "/comparisons",
            json={
                "session_a_id": session_a.id,
                "session_b_id": session_b.id,
                "reconstruction_a_id": rec_a.id,
                "reconstruction_b_id": rec_b.id,
            },
        )

    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"
    mock_enqueue.assert_called_once()


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
