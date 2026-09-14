"""Concurrent browser-upload reservation bound (#864)."""

from __future__ import annotations


def test_start_rejects_when_reservation_cap_reached(
    client, tmp_path, monkeypatch
) -> None:
    from backend.routers import uploads

    root = tmp_path / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    for index in range(uploads._MAX_ACTIVE_RESERVATIONS):
        (root / f"reserved-{index}").mkdir()

    monkeypatch.setattr(
        "backend.routers.uploads._upload_root", lambda: root
    )
    monkeypatch.setattr(
        "backend.routers.uploads.get_config",
        lambda: type("Cfg", (), {"imports_dir": str(tmp_path)})(),
    )

    resp = client.post(
        "/uploads/imports/start",
        json={
            "name": "capped",
            "total_bytes": 1,
            "files": [{"path": "a.jpg", "size": 1}],
        },
    )

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