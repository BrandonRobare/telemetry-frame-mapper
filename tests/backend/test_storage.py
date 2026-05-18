from __future__ import annotations
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_list_files_returns_list(client, tmp_path, monkeypatch):
    (tmp_path / "test.jpg").write_bytes(b"fake image")

    import backend.routers.storage as storage_router
    mock_cfg = type("Cfg", (), {
        "imports_dir": str(tmp_path),
        "processed_dir": str(tmp_path),
        "exports_dir": str(tmp_path),
        "data_dir": str(tmp_path),
    })()
    monkeypatch.setattr(storage_router, "get_config", lambda: mock_cfg)

    resp = client.get("/storage/files?directory=imports")
    assert resp.status_code == 200
    data = resp.json()
    assert "files" in data
    assert any(f["name"] == "test.jpg" for f in data["files"])


def test_list_files_invalid_directory(client):
    resp = client.get("/storage/files?directory=nonexistent")
    assert resp.status_code == 422


def test_delete_file_not_found(client):
    resp = client.delete("/storage/file?path=/tmp/does_not_exist_xyz.jpg")
    assert resp.status_code == 404


def test_delete_file_success(client, tmp_path):
    f = tmp_path / "deleteme.txt"
    f.write_text("bye")

    resp = client.delete(f"/storage/file?path={f}")
    assert resp.status_code == 200
    assert not f.exists()
