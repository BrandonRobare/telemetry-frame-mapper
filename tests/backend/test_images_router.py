from __future__ import annotations

import pytest


def _insert_session_and_image(client, flag="good"):
    from backend.db.database import get_db
    from backend.db.models import Image
    from backend.db.models import Session as SM
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    s = SM(name="img_s", folder_path="/tmp", photo_count=1, usable_count=1)
    db.add(s)
    db.commit()
    db.refresh(s)
    img = Image(
        session_id=s.id,
        filename="a.jpg",
        filepath="/tmp/a.jpg",
        flag=flag,
        usable=True,
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    return s, img


def test_list_images_empty(client):
    resp = client.get("/images?session_id=999999")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_images_filter_flag(client):
    s, img = _insert_session_and_image(client, flag="blurry")
    resp = client.get(f"/images?session_id={s.id}&flag=blurry")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(i["flag"] == "blurry" for i in data)


def test_patch_image_flag(client):
    _, img = _insert_session_and_image(client)
    resp = client.patch(f"/images/{img.id}", json={"flag": "blurry"})
    assert resp.status_code == 200
    assert resp.json()["flag"] == "blurry"


def test_patch_image_not_found(client):
    resp = client.patch("/images/999999", json={"flag": "blurry"})
    assert resp.status_code == 404


def test_session_log_empty(client):
    resp = client.get("/session-log?session_id=999999")
    assert resp.status_code == 200
    assert resp.json() == []


def test_georeferencing_csv_export(client):
    s, _ = _insert_session_and_image(client)
    resp = client.post(f"/export/georeferencing-csv?session_id={s.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "zip_path" in data
    assert data["image_count"] == 1


def test_image_list_includes_colmap_error_when_reconstruction_complete(client):
    from backend.db.database import get_db
    from backend.db.models import Image, Reconstruction, ReconstructionFrame
    from backend.db.models import Session as SessionModel
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    s = SessionModel(name="ReprojTest", folder_path="/tmp/rp", photo_count=1, usable_count=1)
    db.add(s)
    db.commit()
    db.refresh(s)

    img = Image(session_id=s.id, filename="frame_001.jpg", filepath="/f.jpg", usable=True)
    db.add(img)
    db.commit()
    db.refresh(img)

    rec = Reconstruction(session_id=s.id, preset="quick", status="complete", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    frame = ReconstructionFrame(reconstruction_id=rec.id, image_id=img.id, colmap_error_px=0.75)
    db.add(frame)
    db.commit()

    try:
        resp = client.get(f"/images?session_id={s.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        target = next(d for d in data if d["filename"] == "frame_001.jpg")
        assert target["colmap_error_px"] == pytest.approx(0.75)
    finally:
        # Clean up to avoid polluting the shared session-scoped DB
        db.delete(frame)
        db.delete(rec)
        db.delete(img)
        db.delete(s)
        db.commit()


def test_image_list_colmap_error_null_when_no_reconstruction(client):
    from backend.db.database import get_db
    from backend.db.models import Image
    from backend.db.models import Session as SessionModel
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    s = SessionModel(name="NoRecTest", folder_path="/tmp/nr", photo_count=1, usable_count=1)
    db.add(s)
    db.commit()
    db.refresh(s)
    img = Image(session_id=s.id, filename="lone.jpg", filepath="/l.jpg", usable=True)
    db.add(img)
    db.commit()

    resp = client.get(f"/images?session_id={s.id}")
    assert resp.status_code == 200
    data = resp.json()
    target = next(d for d in data if d["filename"] == "lone.jpg")
    assert target["colmap_error_px"] is None
