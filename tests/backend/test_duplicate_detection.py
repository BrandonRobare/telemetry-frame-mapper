from __future__ import annotations

from backend.db.models import Image
from backend.db.models import Session as SessionModel


def _db(client):
    from backend.main import app
    return app.state.test_db_session


def _make_session_with_images(client, name, folder_path, filenames):
    db = _db(client)
    s = SessionModel(name=name, folder_path=folder_path, photo_count=len(filenames), usable_count=0)
    db.add(s)
    db.commit()
    db.refresh(s)
    session_id = s.id  # capture before further commits expire the ORM instance
    for fn in filenames:
        db.add(Image(session_id=session_id, filename=fn, filepath=f"{folder_path}/{fn}"))
    db.commit()
    return type("Made", (), {"id": session_id, "name": name})()


def test_check_duplicate_empty_when_no_sessions(client):
    resp = client.post("/uploads/imports/check-duplicate", json={"folder_path": "/flights/lane1"})
    assert resp.status_code == 200
    assert resp.json() == {"duplicate": False, "matches": []}


def test_check_duplicate_exact_folder_path_match(client):
    s = _make_session_with_images(client, "Lane 1", "/data/imports/lane1", ["a.jpg", "b.jpg"])
    resp = client.post(
        "/uploads/imports/check-duplicate", json={"folder_path": "/data/imports/lane1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["duplicate"] is True
    assert len(body["matches"]) == 1
    match = body["matches"][0]
    assert match["session_id"] == s.id
    assert match["name"] == "Lane 1"
    assert "folder" in match["reason"].lower()
    assert match["overlap"] == 1.0


def test_check_duplicate_high_filename_overlap_flagged(client):
    filenames = [f"DJI_{i:04d}.jpg" for i in range(10)]
    s = _make_session_with_images(client, "Lane 2", "/data/imports/lane2", filenames)
    # 8/10 = 0.8 overlap, above the 0.7 threshold
    incoming = filenames[:8] + ["NEW_1.jpg", "NEW_2.jpg"]
    resp = client.post("/uploads/imports/check-duplicate", json={"filenames": incoming})
    assert resp.status_code == 200
    body = resp.json()
    assert body["duplicate"] is True
    assert len(body["matches"]) == 1
    assert body["matches"][0]["session_id"] == s.id
    assert "overlap" in body["matches"][0]["reason"].lower()
    assert body["matches"][0]["overlap"] == 0.8


def test_check_duplicate_threshold_boundary(client):
    filenames = [f"DJI_{i:04d}.jpg" for i in range(10)]
    _make_session_with_images(client, "Lane 3", "/data/imports/lane3", filenames)

    # exactly at threshold (0.7) -> flagged
    at_threshold = filenames[:7] + ["x1.jpg", "x2.jpg", "x3.jpg"]
    resp = client.post("/uploads/imports/check-duplicate", json={"filenames": at_threshold})
    assert resp.json()["duplicate"] is True

    # just below threshold (0.6) -> not flagged
    below_threshold = filenames[:6] + ["y1.jpg", "y2.jpg", "y3.jpg", "y4.jpg"]
    resp = client.post("/uploads/imports/check-duplicate", json={"filenames": below_threshold})
    assert resp.json()["duplicate"] is False


def test_check_duplicate_unrelated_session_not_flagged(client):
    _make_session_with_images(
        client, "Unrelated", "/data/imports/other-flight", ["zzz1.jpg", "zzz2.jpg"]
    )
    resp = client.post("/uploads/imports/check-duplicate", json={
        "folder_path": "/data/imports/brand-new-flight",
        "filenames": ["fresh1.jpg", "fresh2.jpg", "fresh3.jpg"],
    })
    assert resp.status_code == 200
    assert resp.json() == {"duplicate": False, "matches": []}
