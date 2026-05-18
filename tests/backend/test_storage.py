from __future__ import annotations

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


def test_delete_file_not_found(client, tmp_path, monkeypatch):
    import backend.routers.storage as storage_router
    mock_cfg = type("Cfg", (), {
        "imports_dir": str(tmp_path),
        "processed_dir": str(tmp_path),
        "exports_dir": str(tmp_path),
        "data_dir": str(tmp_path),
    })()
    monkeypatch.setattr(storage_router, "get_config", lambda: mock_cfg)

    resp = client.delete("/storage/file?directory=imports&filename=does_not_exist.jpg")
    assert resp.status_code == 404


def test_delete_file_success(client, tmp_path, monkeypatch):
    import backend.routers.storage as storage_router
    mock_cfg = type("Cfg", (), {
        "imports_dir": str(tmp_path),
        "processed_dir": str(tmp_path),
        "exports_dir": str(tmp_path),
        "data_dir": str(tmp_path),
    })()
    monkeypatch.setattr(storage_router, "get_config", lambda: mock_cfg)

    f = tmp_path / "deleteme.txt"
    f.write_text("bye")

    resp = client.delete("/storage/file?directory=imports&filename=deleteme.txt")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == str(f)
    assert not f.exists()


def test_delete_file_traversal_rejected(client):
    resp = client.delete("/storage/file?directory=imports&filename=../../../etc/passwd")
    assert resp.status_code == 400


def test_delete_file_invalid_directory(client):
    resp = client.delete("/storage/file?directory=secret&filename=foo.txt")
    assert resp.status_code == 422
