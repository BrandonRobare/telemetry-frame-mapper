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


def _add_image(
    db,
    session_id: int,
    index: int,
    *,
    timestamp=None,
    latitude=35.0,
    longitude=-80.0,
    flag="good",
    usable=True,
):
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
    from backend.main import app
    from backend.services.survey_report import build_survey_report

    db = app.state.test_db_session
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
    from backend.main import app
    from backend.services.survey_report import build_survey_report

    db = app.state.test_db_session
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
    from backend.main import app

    db = app.state.test_db_session
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
    from backend.main import app

    db = app.state.test_db_session
    session = _make_session(db)
    t0 = datetime(2026, 1, 1, 12, 0, 0)

    for i in range(3):
        _add_image(db, session.id, i, timestamp=t0 + timedelta(seconds=i))

    resp = client.post(f"/export/survey-report?session_id={session.id}&format=html")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"
    assert "<!DOCTYPE html>" in resp.text
    assert "Survey Report" in resp.text


def test_survey_report_get_serves_the_export_tab_links(client):
    """The Export tab opens the report with window.open and a download link: both GET (#952)."""
    from backend.main import app

    db = app.state.test_db_session
    session = _make_session(db)
    for i in range(3):
        _add_image(db, session.id, i)

    html = client.get(f"/export/survey-report?session_id={session.id}&format=html")
    assert html.status_code == 200
    assert html.headers["content-type"] == "text/html; charset=utf-8"
    assert "Survey Report" in html.text

    data = client.get(f"/export/survey-report?session_id={session.id}&format=json")
    assert data.status_code == 200
    assert data.json()["report_type"] == "survey-report"
    assert data.json()["frame_summary"]["total"] == 3

    assert client.get("/export/survey-report?session_id=999999").status_code == 404


def test_survey_report_404(client):
    resp = client.post("/export/survey-report?session_id=999999")
    assert resp.status_code == 404


def test_survey_report_endpoint_pdf_requires_optional_backend(client):
    from unittest.mock import patch

    from backend.main import app

    db = app.state.test_db_session
    session = _make_session(db)
    for i in range(3):
        _add_image(db, session.id, i)

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "weasyprint":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        resp = client.post(f"/export/survey-report?session_id={session.id}&format=pdf")

    assert resp.status_code == 422
    assert "weasyprint" in resp.json()["detail"].lower()


def test_survey_report_endpoint_rejects_unknown_format(client):
    from backend.main import app

    db = app.state.test_db_session
    session = _make_session(db)
    for i in range(3):
        _add_image(db, session.id, i)

    resp = client.post(f"/export/survey-report?session_id={session.id}&format=docx")

    assert resp.status_code == 422
    assert "format" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
#  Empty and partially failed sessions (#951)
# ---------------------------------------------------------------------------

_EMPTY_FRAME_SUMMARY = {
    "total": 0,
    "usable": 0,
    "quality_breakdown": {},
    "camera": None,
    "gps_present": 0,
}


def _make_empty_session(db):
    session = SessionModel(
        name="Empty Survey", folder_path="/tmp/empty-survey", photo_count=0, usable_count=0
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def test_frame_summary_section_has_the_same_keys_with_zero_frames():
    from backend.services.survey_report import _frame_summary_section

    populated = _frame_summary_section(
        [Image(filename="a.jpg", filepath="/tmp/a.jpg", flag="good", usable=True)]
    )
    empty = _frame_summary_section([])

    assert set(empty) == set(populated)
    assert empty == _EMPTY_FRAME_SUMMARY


def test_survey_report_endpoint_empty_session_json(client):
    from backend.main import app

    session = _make_empty_session(app.state.test_db_session)

    resp = client.post(f"/export/survey-report?session_id={session.id}&format=json")

    assert resp.status_code == 200
    data = resp.json()
    assert data["frame_summary"] == _EMPTY_FRAME_SUMMARY
    assert data["reconstructions"] == []
    assert data["annotations"] == []
    assert "<!DOCTYPE html>" in data["html"]


def test_survey_report_endpoint_empty_session_html(client):
    from backend.main import app

    session = _make_empty_session(app.state.test_db_session)

    resp = client.post(f"/export/survey-report?session_id={session.id}&format=html")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"
    assert "<!DOCTYPE html>" in resp.text
    assert "<dt>Total frames</dt><dd>0</dd>" in resp.text
    assert "<dt>GPS frames</dt><dd>0</dd>" in resp.text
    assert "No frames in this session." in resp.text


def test_survey_report_endpoint_empty_session_pdf(client, monkeypatch):
    import sys
    import types

    from backend.main import app

    session = _make_empty_session(app.state.test_db_session)
    rendered: list[str] = []

    class _FakeHTML:
        def __init__(self, string: str):
            rendered.append(string)

        def write_pdf(self) -> bytes:
            return b"%PDF-1.7 fake"

    fake_weasyprint = types.ModuleType("weasyprint")
    fake_weasyprint.HTML = _FakeHTML
    monkeypatch.setitem(sys.modules, "weasyprint", fake_weasyprint)

    resp = client.post(f"/export/survey-report?session_id={session.id}&format=pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == b"%PDF-1.7 fake"
    assert len(rendered) == 1
    assert "<dt>Total frames</dt><dd>0</dd>" in rendered[0]


def test_survey_report_endpoint_survives_unavailable_preflight(client, monkeypatch):
    from backend.main import app

    db = app.state.test_db_session
    session = _make_session(db)
    for i in range(3):
        _add_image(db, session.id, i)

    def _preflight_fails(_session_id, _db):
        raise ValueError("Session not found")

    monkeypatch.setattr(
        "backend.services.survey_report.build_preflight_quality_report", _preflight_fails
    )

    json_resp = client.post(f"/export/survey-report?session_id={session.id}&format=json")
    html_resp = client.post(f"/export/survey-report?session_id={session.id}&format=html")

    assert json_resp.status_code == 200
    data = json_resp.json()
    assert data["quality_assessment"]["available"] is False
    assert data["coverage"]["available"] is False
    assert data["frame_summary"]["total"] == 3
    assert html_resp.status_code == 200
    assert "Preflight quality check could not run" in html_resp.text
    assert "Coverage data is not available" in html_resp.text
