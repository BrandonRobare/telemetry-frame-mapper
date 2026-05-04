from __future__ import annotations
import datetime


def _insert_session_and_image(client, flag="good"):
    from backend.db.database import get_db
    from backend.main import app
    from backend.db.models import Session as SM, Image

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


def test_webodm_export(client):
    s, _ = _insert_session_and_image(client)
    resp = client.post(f"/export/webodm?session_id={s.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "zip_path" in data
    assert data["image_count"] == 1
