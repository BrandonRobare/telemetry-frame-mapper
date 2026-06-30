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


def test_manifest_endpoint(client, tmp_path):
    artifact = tmp_path / "a.txt"
    artifact.write_text("x")
    resp = client.post(f"/export/reproducibility-manifest?workflow=import&artifact_path={artifact}")
    assert resp.status_code == 200
    assert resp.json()["workflow"] == "import"
    assert resp.json()["artifacts"][0]["exists"] is True
