from __future__ import annotations

import pytest

from backend.db.models import Image
from backend.db.models import Session as SessionModel


def _get_db(client):
    from backend.db.database import get_db
    from backend.main import app
    return next(app.dependency_overrides[get_db]())


def _make_session_with_images(db, n: int = 2) -> tuple[SessionModel, list[Image]]:
    s = SessionModel(
        name="Defect Router Test", folder_path="/tmp/dr", photo_count=n, usable_count=n
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    images = []
    for i in range(n):
        img = Image(
            session_id=s.id,
            filename=f"img_{i}.jpg",
            filepath=f"/tmp/img_{i}.jpg",
            thumb_path=f"processed/{s.id}/thumbs/img_{i}.jpg",
            latitude=35.0 + i * 0.001,
            longitude=-80.0 - i * 0.001,
            usable=True,
        )
        db.add(img)
        db.commit()
        db.refresh(img)
        images.append(img)
    return s, images


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def test_create_defect_happy_path(client):
    db = _get_db(client)
    s, images = _make_session_with_images(db, 1)

    resp = client.post(
        f"/sessions/{s.id}/defects",
        json={
            "category": "crack",
            "severity": "medium",
            "note": "Vertical crack on the north wall",
            "image_ids": [images[0].id],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["session_id"] == s.id
    assert data["category"] == "crack"
    assert data["severity"] == "medium"
    assert data["note"] == "Vertical crack on the north wall"
    assert data["image_ids"] == [images[0].id]
    assert len(data["images"]) == 1
    assert data["images"][0]["id"] == images[0].id
    assert data["images"][0]["latitude"] == pytest.approx(35.0)
    assert "id" in data
    assert "created_at" in data


def test_create_defect_links_multiple_images(client):
    db = _get_db(client)
    s, images = _make_session_with_images(db, 2)

    resp = client.post(
        f"/sessions/{s.id}/defects",
        json={"category": "vegetation", "image_ids": [img.id for img in images]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert set(data["image_ids"]) == {img.id for img in images}


def test_create_defect_session_not_found(client):
    resp = client.post(
        "/sessions/999999/defects",
        json={"category": "crack", "image_ids": [1]},
    )
    assert resp.status_code == 404


def test_create_defect_invalid_category(client):
    db = _get_db(client)
    s, images = _make_session_with_images(db, 1)
    resp = client.post(
        f"/sessions/{s.id}/defects",
        json={"category": "not_a_real_category", "image_ids": [images[0].id]},
    )
    assert resp.status_code == 422


def test_create_defect_invalid_severity(client):
    db = _get_db(client)
    s, images = _make_session_with_images(db, 1)
    resp = client.post(
        f"/sessions/{s.id}/defects",
        json={"category": "crack", "severity": "catastrophic", "image_ids": [images[0].id]},
    )
    assert resp.status_code == 422


def test_create_defect_requires_at_least_one_image(client):
    db = _get_db(client)
    s, _ = _make_session_with_images(db, 1)
    resp = client.post(
        f"/sessions/{s.id}/defects",
        json={"category": "crack", "image_ids": []},
    )
    assert resp.status_code == 422


def test_create_defect_rejects_image_from_other_session(client):
    db = _get_db(client)
    s1, images1 = _make_session_with_images(db, 1)
    s2, images2 = _make_session_with_images(db, 1)
    resp = client.post(
        f"/sessions/{s1.id}/defects",
        json={"category": "crack", "image_ids": [images2[0].id]},
    )
    assert resp.status_code == 422


def test_create_defect_rejects_unknown_image_id(client):
    db = _get_db(client)
    s, _ = _make_session_with_images(db, 1)
    resp = client.post(
        f"/sessions/{s.id}/defects",
        json={"category": "crack", "image_ids": [999999]},
    )
    assert resp.status_code == 422


def test_create_defect_severity_defaults_to_none(client):
    db = _get_db(client)
    s, images = _make_session_with_images(db, 1)
    resp = client.post(
        f"/sessions/{s.id}/defects",
        json={"category": "other", "image_ids": [images[0].id]},
    )
    assert resp.status_code == 201
    assert resp.json()["severity"] is None


# ---------------------------------------------------------------------------
# List / Get
# ---------------------------------------------------------------------------

def test_list_defects_empty(client):
    db = _get_db(client)
    s, _ = _make_session_with_images(db, 1)
    resp = client.get(f"/sessions/{s.id}/defects")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_defects_multiple(client):
    db = _get_db(client)
    s, images = _make_session_with_images(db, 2)
    client.post(
        f"/sessions/{s.id}/defects", json={"category": "crack", "image_ids": [images[0].id]}
    )
    client.post(
        f"/sessions/{s.id}/defects", json={"category": "corrosion", "image_ids": [images[1].id]}
    )
    resp = client.get(f"/sessions/{s.id}/defects")
    assert resp.status_code == 200
    categories = {d["category"] for d in resp.json()}
    assert categories == {"crack", "corrosion"}


def test_list_defects_isolation(client):
    db = _get_db(client)
    s1, images1 = _make_session_with_images(db, 1)
    s2, _ = _make_session_with_images(db, 1)
    client.post(
        f"/sessions/{s1.id}/defects", json={"category": "crack", "image_ids": [images1[0].id]}
    )
    resp = client.get(f"/sessions/{s2.id}/defects")
    assert resp.json() == []


def test_list_defects_filter_by_category(client):
    db = _get_db(client)
    s, images = _make_session_with_images(db, 2)
    client.post(
        f"/sessions/{s.id}/defects", json={"category": "crack", "image_ids": [images[0].id]}
    )
    client.post(
        f"/sessions/{s.id}/defects", json={"category": "corrosion", "image_ids": [images[1].id]}
    )
    resp = client.get(f"/sessions/{s.id}/defects?category=corrosion")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["category"] == "corrosion"


def test_list_defects_session_not_found(client):
    resp = client.get("/sessions/999999/defects")
    assert resp.status_code == 404


def test_get_defect_happy_path(client):
    db = _get_db(client)
    s, images = _make_session_with_images(db, 1)
    create_resp = client.post(
        f"/sessions/{s.id}/defects", json={"category": "crack", "image_ids": [images[0].id]}
    )
    defect_id = create_resp.json()["id"]
    resp = client.get(f"/sessions/{s.id}/defects/{defect_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == defect_id


def test_get_defect_not_found(client):
    db = _get_db(client)
    s, _ = _make_session_with_images(db, 1)
    resp = client.get(f"/sessions/{s.id}/defects/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------

def test_patch_defect_updates_fields(client):
    db = _get_db(client)
    s, images = _make_session_with_images(db, 1)
    create_resp = client.post(
        f"/sessions/{s.id}/defects",
        json={"category": "crack", "severity": "low", "image_ids": [images[0].id]},
    )
    defect_id = create_resp.json()["id"]

    resp = client.patch(
        f"/sessions/{s.id}/defects/{defect_id}",
        json={"severity": "high", "note": "Escalated after re-inspection"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["severity"] == "high"
    assert data["note"] == "Escalated after re-inspection"
    assert data["category"] == "crack"


def test_patch_defect_replaces_linked_images(client):
    db = _get_db(client)
    s, images = _make_session_with_images(db, 2)
    create_resp = client.post(
        f"/sessions/{s.id}/defects", json={"category": "crack", "image_ids": [images[0].id]}
    )
    defect_id = create_resp.json()["id"]

    resp = client.patch(
        f"/sessions/{s.id}/defects/{defect_id}",
        json={"image_ids": [images[1].id]},
    )
    assert resp.status_code == 200
    assert resp.json()["image_ids"] == [images[1].id]


def test_patch_defect_invalid_category(client):
    db = _get_db(client)
    s, images = _make_session_with_images(db, 1)
    create_resp = client.post(
        f"/sessions/{s.id}/defects", json={"category": "crack", "image_ids": [images[0].id]}
    )
    defect_id = create_resp.json()["id"]
    resp = client.patch(f"/sessions/{s.id}/defects/{defect_id}", json={"category": "bogus"})
    assert resp.status_code == 422


def test_patch_defect_not_found(client):
    db = _get_db(client)
    s, _ = _make_session_with_images(db, 1)
    resp = client.patch(f"/sessions/{s.id}/defects/999999", json={"severity": "high"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_defect_happy_path(client):
    db = _get_db(client)
    s, images = _make_session_with_images(db, 1)
    create_resp = client.post(
        f"/sessions/{s.id}/defects", json={"category": "crack", "image_ids": [images[0].id]}
    )
    defect_id = create_resp.json()["id"]

    resp = client.delete(f"/sessions/{s.id}/defects/{defect_id}")
    assert resp.status_code == 200

    list_resp = client.get(f"/sessions/{s.id}/defects")
    ids = [d["id"] for d in list_resp.json()]
    assert defect_id not in ids


def test_delete_defect_not_found(client):
    db = _get_db(client)
    s, _ = _make_session_with_images(db, 1)
    resp = client.delete(f"/sessions/{s.id}/defects/999999")
    assert resp.status_code == 404


def test_delete_defect_wrong_session(client):
    db = _get_db(client)
    s1, images1 = _make_session_with_images(db, 1)
    s2, _ = _make_session_with_images(db, 1)
    create_resp = client.post(
        f"/sessions/{s1.id}/defects", json={"category": "crack", "image_ids": [images1[0].id]}
    )
    defect_id = create_resp.json()["id"]

    resp = client.delete(f"/sessions/{s2.id}/defects/{defect_id}")
    assert resp.status_code == 404
