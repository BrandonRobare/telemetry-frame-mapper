from __future__ import annotations
from pathlib import Path
from PIL import Image as PILImage


def _make_test_jpg(folder: Path, name: str) -> Path:
    p = folder / name
    img = PILImage.new("RGB", (100, 100), color=(128, 128, 128))
    img.save(str(p))
    return p


def test_import_endpoint_bad_folder(client):
    resp = client.post("/sessions/import", json={"folder_path": "/nonexistent/path/xyz", "name": "bad"})
    assert resp.status_code == 400


def test_import_endpoint_creates_session(client, tmp_path):
    _make_test_jpg(tmp_path, "frame_001.jpg")
    _make_test_jpg(tmp_path, "frame_002.jpg")
    resp = client.post("/sessions/import", json={"folder_path": str(tmp_path), "name": "Test Import"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Import"
    assert "id" in data


def test_progress_endpoint(client, tmp_path):
    _make_test_jpg(tmp_path, "p.jpg")
    session_id = client.post(
        "/sessions/import",
        json={"folder_path": str(tmp_path), "name": "prog"},
    ).json()["id"]
    resp = client.get(f"/sessions/{session_id}/progress")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("running", "done", "unknown")
