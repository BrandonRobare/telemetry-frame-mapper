from __future__ import annotations
from pathlib import Path
from unittest.mock import patch

from PIL import Image as PILImage


def _make_test_jpg(folder: Path, name: str) -> Path:
    p = folder / name
    img = PILImage.new("RGB", (100, 100), color=(128, 128, 128))
    img.save(str(p))
    return p


def test_import_endpoint_bad_folder(client):
    with patch("backend.routers.sessions.start_import") as mock_start:
        resp = client.post(
            "/sessions/import", json={"folder_path": "/nonexistent/path/xyz", "name": "bad"}
        )
    assert resp.status_code == 400
    mock_start.assert_not_called()


def test_import_endpoint_creates_session(client, tmp_path):
    _make_test_jpg(tmp_path, "frame_001.jpg")
    _make_test_jpg(tmp_path, "frame_002.jpg")
    with patch("backend.routers.sessions.start_import") as mock_start:
        resp = client.post(
            "/sessions/import", json={"folder_path": str(tmp_path), "name": "Test Import"}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Import"
    assert "id" in data
    mock_start.assert_called_once()
    # start_import should have received session id (first arg) and the folder path
    call_args = mock_start.call_args
    assert call_args.args[0] == data["id"]
    assert call_args.args[1] == tmp_path


def test_progress_endpoint_returns_pending(client, tmp_path):
    """After import is kicked off, progress endpoint returns a known status."""
    _make_test_jpg(tmp_path, "p.jpg")
    with patch("backend.routers.sessions.start_import"):
        session_id = client.post(
            "/sessions/import",
            json={"folder_path": str(tmp_path), "name": "prog"},
        ).json()["id"]
    resp = client.get(f"/sessions/{session_id}/progress")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("running", "done", "pending", "unknown")
