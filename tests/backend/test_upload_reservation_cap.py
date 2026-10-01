"""Concurrent browser-upload reservation bound (#864)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

_PLAN = {"name": "capped", "total_bytes": 1, "files": [{"path": "a.jpg", "size": 1}]}


def _use_upload_root(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("backend.routers.uploads._upload_root", lambda: root)
    monkeypatch.setattr(
        "backend.routers.uploads.get_config",
        lambda: type("Cfg", (), {"imports_dir": str(tmp_path)})(),
    )
    return root


def test_start_rejects_when_reservation_cap_reached(
    client, tmp_path, monkeypatch
) -> None:
    from backend.routers import uploads

    _use_upload_root(tmp_path, monkeypatch)
    for _ in range(uploads._MAX_ACTIVE_RESERVATIONS):
        assert client.post("/uploads/imports/start", json=_PLAN).status_code == 200

    resp = client.post("/uploads/imports/start", json=_PLAN)

    assert resp.status_code == 409
    assert "Too many concurrent uploads" in resp.json()["detail"]


def test_start_accepts_under_the_cap(client, tmp_path, monkeypatch) -> None:

    root = tmp_path / "uploads"
    root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("backend.routers.uploads._upload_root", lambda: root)
    monkeypatch.setattr(
        "backend.routers.uploads.get_config",
        lambda: type("Cfg", (), {"imports_dir": str(tmp_path)})(),
    )

    resp = client.post(
        "/uploads/imports/start",
        json={
            "name": "fine",
            "total_bytes": 1,
            "files": [{"path": "a.jpg", "size": 1}],
        },
    )

    assert resp.status_code == 200
    assert "upload_id" in resp.json()


def test_finished_imports_do_not_consume_reservation_slots(
    client, tmp_path, monkeypatch
) -> None:
    """Only uploads still receiving chunks count toward the cap (#944)."""
    from backend.routers import uploads

    root = _use_upload_root(tmp_path, monkeypatch)
    # An upload a release that imported in place left in staging after /complete.
    legacy_id = uuid.uuid4().hex
    (root / legacy_id).mkdir()
    (root / legacy_id / ".upload.json").write_text(json.dumps({
        "id": legacy_id,
        "name": "legacy",
        "files": {"a.jpg": {"size": 1, "received": 1}},
        "uploaded_bytes": 1,
        "total_bytes": 1,
        "status": "importing",
        "session_id": 1,
        "error": None,
    }))
    with patch("backend.routers.uploads.start_import"):
        for index in range(uploads._MAX_ACTIVE_RESERVATIONS):
            start = client.post("/uploads/imports/start", json={**_PLAN, "name": f"f{index}"})
            assert start.status_code == 200
            upload_id = start.json()["upload_id"]
            assert client.post(
                f"/uploads/imports/{upload_id}/chunk",
                data={"path": "a.jpg", "offset": "0"},
                files={"chunk": ("chunk", b"x", "application/octet-stream")},
            ).status_code == 200
            assert client.post(f"/uploads/imports/{upload_id}/complete").status_code == 200

        resp = client.post("/uploads/imports/start", json=_PLAN)

    assert resp.status_code == 200
