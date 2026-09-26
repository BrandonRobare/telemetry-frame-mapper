from pathlib import Path
from urllib.parse import quote

import pytest

import backend.services.reproducibility_manifest as manifest_service
from backend.services.reproducibility_manifest import build_reproducibility_manifest, sha256_file


def test_manifest_hashes_artifacts(tmp_path):
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("hello")
    manifest = build_reproducibility_manifest(
        workflow="export",
        settings={"mode": "webodm"},
        artifacts=[artifact],
        artifact_roots=[tmp_path],
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


def test_manifest_rejects_sibling_of_configured_root(tmp_path):
    safe_root = tmp_path / "safe"
    safe_root.mkdir()
    sibling = tmp_path / "safe-sibling"
    sibling.mkdir()
    artifact = sibling / "secret.txt"
    artifact.write_text("secret")

    with pytest.raises(ValueError, match="outside configured safe directories"):
        build_reproducibility_manifest(
            workflow="export",
            settings={},
            artifacts=[artifact],
            artifact_roots=[safe_root],
        )


def test_manifest_allows_configured_root(tmp_path):
    safe_root = tmp_path / "safe"
    safe_root.mkdir()

    manifest = build_reproducibility_manifest(
        workflow="export",
        settings={},
        artifacts=[safe_root],
        artifact_roots=[safe_root],
    )

    entry = manifest["artifacts"][0]
    assert entry["exists"] is True
    assert Path(entry["path"]).samefile(safe_root)
    assert "sha256" not in entry


def test_manifest_rejects_parent_traversal(tmp_path):
    safe_root = tmp_path / "safe"
    safe_root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")

    with pytest.raises(ValueError, match="outside configured safe directories"):
        build_reproducibility_manifest(
            workflow="export",
            settings={},
            artifacts=[safe_root / ".." / outside.name],
            artifact_roots=[safe_root],
        )


def test_manifest_rejects_symlink_escape(tmp_path):
    safe_root = tmp_path / "safe"
    safe_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    link = safe_root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")

    with pytest.raises(ValueError, match="outside configured safe directories"):
        build_reproducibility_manifest(
            workflow="export",
            settings={},
            artifacts=[link / "secret.txt"],
            artifact_roots=[safe_root],
        )


def test_manifest_rejects_symlink_swap_after_confinement(tmp_path, monkeypatch):
    safe_root = tmp_path / "safe"
    folder = safe_root / "sub"
    folder.mkdir(parents=True)
    (folder / "artifact.txt").write_text("safe")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "artifact.txt").write_text("secret")
    original = manifest_service.confine_path

    def swap_after_validation(path, root, **kwargs):
        validated = original(path, root, **kwargs)
        if Path(path) == folder / "artifact.txt":
            folder.rename(safe_root / "moved")
            folder.symlink_to(outside, target_is_directory=True)
        return validated

    monkeypatch.setattr(manifest_service, "confine_path", swap_after_validation)
    with pytest.raises(ValueError, match="outside configured safe directories"):
        build_reproducibility_manifest(
            workflow="export",
            settings={},
            artifacts=[folder / "artifact.txt"],
            artifact_roots=[safe_root],
        )


def test_manifest_hashes_in_root_symlink_target_and_preserves_missing_path(tmp_path):
    root = tmp_path / "safe"
    root.mkdir()
    real_file = root / "real.txt"
    real_file.write_text("safe")
    (root / "alias.txt").symlink_to(real_file)

    result = build_reproducibility_manifest(
        workflow="export",
        settings={},
        artifacts=[root / "alias.txt", root / "missing.txt"],
        artifact_roots=[root],
    )
    assert result["artifacts"][0]["path"] == str(real_file)
    assert result["artifacts"][0]["sha256"] == sha256_file(real_file)
    assert result["artifacts"][1] == {"path": str(root / "missing.txt"), "exists": False}


def test_manifest_fails_closed_without_descriptor_relative_opens(tmp_path, monkeypatch):
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("safe")
    monkeypatch.setattr(manifest_service.os, "supports_dir_fd", set())
    with pytest.raises(ValueError, match="secure manifest artifact inspection is unavailable"):
        build_reproducibility_manifest(
            workflow="export", settings={}, artifacts=[artifact], artifact_roots=[tmp_path]
        )
