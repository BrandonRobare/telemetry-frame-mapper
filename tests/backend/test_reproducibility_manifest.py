from urllib.parse import quote

from backend.services.reproducibility_manifest import build_reproducibility_manifest, sha256_file


def test_manifest_hashes_artifacts(tmp_path):
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("hello")
    manifest = build_reproducibility_manifest(
        workflow="export",
        settings={"mode": "webodm"},
        artifacts=[artifact],
        dataset={"session_id": 1},
    )
    assert manifest["manifest_version"] == 1
    assert manifest["dataset"]["session_id"] == 1
    assert manifest["artifacts"][0]["sha256"] == sha256_file(artifact)
    assert "ffmpeg" in manifest["external_binaries"]


def test_manifest_endpoint(client, tmp_path, monkeypatch):
    safe_root = tmp_path / "safe"
    safe_root.mkdir()

    class Cfg:
        target_crs = "EPSG:32617"
        default_basemap = "esri"
        exports_dir = str(safe_root)
        processed_dir = str(safe_root)
        imports_dir = str(safe_root)
        data_dir = str(safe_root)

    monkeypatch.setattr("backend.routers.export.get_config", lambda: Cfg())

    artifact = safe_root / "a.txt"
    artifact.write_text("x")
    resp = client.post(
        "/export/reproducibility-manifest"
        f"?workflow=import&artifact_path={quote(str(artifact))}"
    )
    assert resp.status_code == 200
    assert resp.json()["workflow"] == "import"
    assert resp.json()["artifacts"][0]["exists"] is True


def test_manifest_endpoint_rejects_arbitrary_path(client, tmp_path, monkeypatch):
    safe_root = tmp_path / "safe"
    safe_root.mkdir()

    class Cfg:
        target_crs = "EPSG:32617"
        default_basemap = "esri"
        exports_dir = str(safe_root)
        processed_dir = str(safe_root)
        imports_dir = str(safe_root)
        data_dir = str(safe_root)

    monkeypatch.setattr("backend.routers.export.get_config", lambda: Cfg())

    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    resp = client.post(
        "/export/reproducibility-manifest"
        f"?workflow=import&artifact_path={quote(str(outside))}"
    )
    assert resp.status_code == 422
    assert "outside configured safe directories" in resp.json()["detail"]
