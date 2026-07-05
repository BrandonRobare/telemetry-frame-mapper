from __future__ import annotations

from datetime import datetime, timedelta

from backend.db.models import Annotation, Image, Reconstruction
from backend.db.models import Session as SessionModel


def _make_session(db):
    session = SessionModel(
        name="Survey Report Test", folder_path="/tmp/survey", photo_count=10, usable_count=8
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _add_image(db, session_id: int, index: int, *, timestamp=None, latitude=35.0,
               longitude=-80.0, flag="good", usable=True):
    image = Image(
        session_id=session_id,
        filename=f"frame_{index:04d}.jpg",
        filepath=f"/tmp/frame_{index:04d}.jpg",
        timestamp=timestamp or datetime(2026, 1, 1, 12, 0, 0) + timedelta(seconds=index),
        latitude=latitude,
        longitude=longitude,
        altitude_m=100.0,
        sharpness_score=250.0,
        brightness_score=128.0,
        flag=flag,
        usable=usable,
        camera_make="DJI",
        camera_model="FC8282",
        width=4000,
        height=3000,
        focal_length_mm=8.8,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


def test_survey_report_builds_json(client):
    from backend.db.database import get_db
    from backend.main import app
    from backend.services.survey_report import build_survey_report

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)

    for i in range(5):
        _add_image(db, session.id, i, timestamp=t0 + timedelta(seconds=i))

    report = build_survey_report(session.id, db)
    assert report["report_type"] == "survey-report"
    assert report["version"] == "1.0"
    assert "generated_at" in report
    assert report["session"]["id"] == session.id
    assert report["frame_summary"]["total"] == 5
    assert report["frame_summary"]["usable"] == 5
    assert report["frame_summary"]["camera"]["make"] == "DJI"
    assert report["quality_assessment"]["available"] is True
    assert "html" in report
    assert "<!DOCTYPE html>" in report["html"]


def test_survey_report_with_reconstructions(client):
    from backend.db.database import get_db
    from backend.main import app
    from backend.services.survey_report import build_survey_report

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)

    for i in range(3):
        _add_image(db, session.id, i, timestamp=t0 + timedelta(seconds=i))

    rec = Reconstruction(
        session_id=session.id,
        status="complete",
        preset="quick",
        frames_used=3,
        frames_registered=3,
        gaussian_count=150000,
        psnr=28.5,
        ssim=0.85,
        started_at=datetime(2026, 1, 1, 12, 5, 0),
        completed_at=datetime(2026, 1, 1, 12, 10, 0),
        duration_s=300.0,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    ann = Annotation(
        reconstruction_id=rec.id,
        label="Test Point",
        lat=35.0,
        lon=-80.0,
        alt_m=100.0,
        color="#ff0000",
    )
    db.add(ann)
    db.commit()

    report = build_survey_report(session.id, db)
    assert len(report["reconstructions"]) == 1
    assert report["reconstructions"][0]["id"] == rec.id
    assert report["reconstructions"][0]["psnr"] == 28.5
    assert len(report["annotations"]) == 1
    assert report["annotations"][0]["label"] == "Test Point"


def test_survey_report_endpoint_json(client):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)

    for i in range(3):
        _add_image(db, session.id, i, timestamp=t0 + timedelta(seconds=i))

    resp = client.post(f"/export/survey-report?session_id={session.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "survey-report"
    assert "generated_at" in data


def test_survey_report_endpoint_html(client):
    from backend.db.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)

    for i in range(3):
        _add_image(db, session.id, i, timestamp=t0 + timedelta(seconds=i))

    resp = client.post(f"/export/survey-report?session_id={session.id}&format=html")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"
    assert "<!DOCTYPE html>" in resp.text
    assert "Survey Report" in resp.text


def test_survey_report_404(client):
    resp = client.post("/export/survey-report?session_id=999999")
    assert resp.status_code == 404