"""Integration tests for GCP accuracy and checkpoint validation endpoints."""

from __future__ import annotations

import json

from backend.db.models import Image, Reconstruction, ReconstructionFrame
from backend.db.models import Session as SessionModel


def _db(client):
    from backend.main import app

    return app.state.test_db_session


_SAMPLE_GEO_TRANSFORM = json.dumps(
    {
        "scale": 1.0,
        "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "translation": [500000.0, 4500000.0, 100.0],
        "utm_zone": "17N",
        "utm_origin": [0.0, 0.0],
    }
)


# ---------------------------------------------------------------------------
#  GCP accuracy report endpoint
# ---------------------------------------------------------------------------


def test_gcp_accuracy_report_no_completed_reconstruction(client):
    db = _db(client)
    session = SessionModel(name="NoRec", folder_path="/tmp/norec")
    db.add(session)
    db.commit()
    db.refresh(session)

    resp = client.post(
        f"/georeferencing/sessions/{session.id}/accuracy-report",
        json={
            "points": [
                {
                    "x": 0,
                    "y": 0,
                    "z": 0,
                    "reconstructed_x": 0,
                    "reconstructed_y": 0,
                    "reconstructed_z": 0,
                }
            ]
        },
    )
    assert resp.status_code == 404
    assert "No completed reconstruction" in resp.json()["detail"]


def test_gcp_accuracy_report_no_geo_transform(client):
    db = _db(client)
    session = SessionModel(name="NoGeo", folder_path="/tmp/nogeo")
    db.add(session)
    db.commit()
    db.refresh(session)

    rec = Reconstruction(
        session_id=session.id,
        status="complete",
        preset="quick",
        frames_used=5,
        geo_transform=None,
    )
    db.add(rec)
    db.commit()

    resp = client.post(
        f"/georeferencing/sessions/{session.id}/accuracy-report",
        json={
            "points": [
                {
                    "x": 0,
                    "y": 0,
                    "z": 0,
                    "reconstructed_x": 0,
                    "reconstructed_y": 0,
                    "reconstructed_z": 0,
                }
            ]
        },
    )
    assert resp.status_code == 400
    assert "geo-transform" in resp.json()["detail"]


def test_gcp_accuracy_report_missing_session(client):
    resp = client.post(
        "/georeferencing/sessions/99999/accuracy-report",
        json={
            "points": [
                {
                    "x": 0,
                    "y": 0,
                    "z": 0,
                    "reconstructed_x": 0,
                    "reconstructed_y": 0,
                    "reconstructed_z": 0,
                }
            ]
        },
    )
    assert resp.status_code == 404


def test_gcp_accuracy_report_valid(client):
    db = _db(client)
    session = SessionModel(name="GCPTest", folder_path="/tmp/gcptest")
    db.add(session)
    db.commit()
    db.refresh(session)

    rec = Reconstruction(
        session_id=session.id,
        status="complete",
        preset="quick",
        frames_used=5,
        geo_transform=_SAMPLE_GEO_TRANSFORM,
    )
    db.add(rec)
    db.commit()

    resp = client.post(
        f"/georeferencing/sessions/{session.id}/accuracy-report",
        json={
            "points": [
                {
                    "label": "A",
                    "x": 500000.0,
                    "y": 4500000.0,
                    "z": 100.0,
                    "reconstructed_x": 500000.0,
                    "reconstructed_y": 4500000.0,
                    "reconstructed_z": 100.0,
                },
                {
                    "label": "B",
                    "x": 500003.0,
                    "y": 4500004.0,
                    "z": 100.0,
                    "reconstructed_x": 500000.0,
                    "reconstructed_y": 4500000.0,
                    "reconstructed_z": 100.0,
                },
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["point_count"] == 2
    assert "rmse" in data
    assert data["rmse"]["3d_m"] is not None
    assert len(data["residuals"]) == 2
    # Point A at exactly the translation: 3d distance = 0
    assert data["residuals"][0]["distance_3d_m"] == 0.0
    # Point B: dx=3, dy=4, dz=0 → distance 5.0
    assert data["residuals"][1]["distance_3d_m"] == 5.0


def test_gcp_accuracy_report_empty_points_rejected(client):
    db = _db(client)
    session = SessionModel(name="EmptyPoints", folder_path="/tmp/emptypoints")
    db.add(session)
    db.commit()
    db.refresh(session)

    rec = Reconstruction(
        session_id=session.id,
        status="complete",
        preset="quick",
        frames_used=5,
        geo_transform=_SAMPLE_GEO_TRANSFORM,
    )
    db.add(rec)
    db.commit()

    resp = client.post(
        f"/georeferencing/sessions/{session.id}/accuracy-report",
        json={"points": []},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
#  Quality scorecard endpoint
# ---------------------------------------------------------------------------


def test_quality_scorecard_no_reconstruction(client):
    resp = client.get("/reconstruction/99999/quality-scorecard")
    assert resp.status_code == 404


def test_quality_scorecard_not_complete(client):
    db = _db(client)
    session = SessionModel(name="ScorecardPending", folder_path="/tmp/scpending")
    db.add(session)
    db.commit()
    db.refresh(session)

    rec = Reconstruction(session_id=session.id, status="pending", preset="quick")
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/quality-scorecard")
    assert resp.status_code == 202


def test_quality_scorecard_complete(client):
    db = _db(client)
    session = SessionModel(name="ScorecardOK", folder_path="/tmp/scok")
    db.add(session)
    db.commit()
    db.refresh(session)

    img = Image(
        session_id=session.id,
        filename="f001.jpg",
        filepath="/tmp/f001.jpg",
        usable=True,
        latitude=35.0,
        longitude=-80.0,
    )
    db.add(img)
    db.commit()
    db.refresh(img)

    rec = Reconstruction(
        session_id=session.id,
        status="complete",
        preset="full",
        frames_used=1,
        frames_registered=1,
        gaussian_count=120000,
        psnr=28.3,
        ssim=0.88,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    rf = ReconstructionFrame(
        reconstruction_id=rec.id,
        image_id=img.id,
        colmap_error_px=0.75,
    )
    db.add(rf)
    db.commit()

    resp = client.get(f"/reconstruction/{rec.id}/quality-scorecard")
    assert resp.status_code == 200
    data = resp.json()

    assert data["reconstruction_id"] == rec.id
    assert data["frame_counts"]["frames_used"] == 1
    assert data["frame_counts"]["registration_completeness_pct"] == 100.0
    assert data["density"]["gaussian_count"] == 120000
    assert data["reprojection_error"]["mean_px"] == 0.75
    assert data["quality"]["psnr_final"] == 28.3


def test_calibration_drift_report_is_unavailable_when_sparse_model_is_missing(client):
    db = _db(client)
    session = SessionModel(name="CalibrationReport", folder_path="/tmp/calibration-report")
    db.add(session)
    db.commit()
    db.refresh(session)
    rec = Reconstruction(session_id=session.id, status="complete", colmap_dir="/tmp/missing-colmap")
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/calibration-drift-report")

    assert resp.status_code == 200
    assert resp.json()["status"] == "unavailable"


# ---------------------------------------------------------------------------
#  Checkpoint validation endpoint
# ---------------------------------------------------------------------------


def test_validate_checkpoints_no_reconstruction(client):
    resp = client.post(
        "/reconstruction/99999/validate-checkpoints",
        json={
            "points": [
                {
                    "x": 0,
                    "y": 0,
                    "z": 0,
                    "reconstructed_x": 0,
                    "reconstructed_y": 0,
                    "reconstructed_z": 0,
                }
            ]
        },
    )
    assert resp.status_code == 404


def test_validate_checkpoints_not_complete(client):
    db = _db(client)
    session = SessionModel(name="CheckPending", folder_path="/tmp/chkpending")
    db.add(session)
    db.commit()
    db.refresh(session)

    rec = Reconstruction(session_id=session.id, status="pending", preset="quick")
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.post(
        f"/reconstruction/{rec.id}/validate-checkpoints",
        json={
            "points": [
                {
                    "x": 0,
                    "y": 0,
                    "z": 0,
                    "reconstructed_x": 0,
                    "reconstructed_y": 0,
                    "reconstructed_z": 0,
                }
            ]
        },
    )
    assert resp.status_code == 202


def test_validate_checkpoints_no_surface_available(client):
    db = _db(client)
    session = SessionModel(name="CheckNoSurface", folder_path="/tmp/chnosurface")
    db.add(session)
    db.commit()
    db.refresh(session)

    rec = Reconstruction(
        session_id=session.id,
        status="complete",
        preset="quick",
        frames_used=5,
        splat_path=None,
        mesh_glb_path=None,
        pointcloud_path=None,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.post(
        f"/reconstruction/{rec.id}/validate-checkpoints",
        json={
            "points": [
                {
                    "x": 0,
                    "y": 0,
                    "z": 0,
                    "reconstructed_x": 0,
                    "reconstructed_y": 0,
                    "reconstructed_z": 0,
                }
            ]
        },
    )
    assert resp.status_code == 422
    assert "No surface source" in resp.json()["detail"]


def test_validate_checkpoints_empty_points_rejected(client):
    db = _db(client)
    session = SessionModel(name="CheckEmpty", folder_path="/tmp/chkempty")
    db.add(session)
    db.commit()
    db.refresh(session)

    rec = Reconstruction(
        session_id=session.id,
        status="complete",
        preset="quick",
        frames_used=5,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.post(
        f"/reconstruction/{rec.id}/validate-checkpoints",
        json={"points": []},
    )
    assert resp.status_code == 422
