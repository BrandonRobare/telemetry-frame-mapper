"""Regression and structural coverage for the shared filesystem confinement boundary."""

from pathlib import Path

import pytest

from backend.core.paths import confine_path


@pytest.mark.parametrize("escaping", ["../escape.txt", "../../escape.txt"])
def test_confine_path_rejects_escaping_paths(tmp_path, escaping):
    root = tmp_path / "exports"

    with pytest.raises(ValueError, match="outside allowed directory"):
        confine_path(root / escaping, root)


def test_confine_path_rejects_symlink_escape_and_can_reject_root(tmp_path):
    root = tmp_path / "exports"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="outside allowed directory"):
        confine_path(root / "escape" / "secret.txt", root)
    with pytest.raises(ValueError, match="outside allowed directory"):
        confine_path(root, root, allow_root=False)


def test_confine_path_allows_child_and_root_when_requested(tmp_path):
    root = tmp_path / "exports"

    assert confine_path(root / "nested" / "artifact.bin", root) == root / "nested" / "artifact.bin"
    assert confine_path(root, root, allow_root=True) == root


def test_user_influenced_filesystem_boundaries_use_public_guard():
    """Keep the audited containment boundaries on the one canonical guard."""
    root = Path(__file__).resolve().parents[2]
    expected_importers = {
        "backend/routers/export.py",
        "backend/routers/projects.py",
        "backend/routers/reconstruction.py",
        "backend/routers/sessions.py",
        "backend/routers/share_links.py",
        "backend/routers/storage.py",
        "backend/routers/tiles.py",
        "backend/routers/uploads.py",
        "backend/services/artifact_backup.py",
        "backend/services/artifact_cleanup.py",
        "backend/services/auto_import.py",
        "backend/services/ingest_orchestrator.py",
        "backend/services/ply_io.py",
        "backend/services/potree_export.py",
        "backend/services/reconstruction.py",
        "backend/services/reproducibility_manifest.py",
        "backend/services/session_bundle.py",
        "backend/services/share_bundle.py",
        "backend/services/storage_lifecycle.py",
        "backend/services/webodm_package.py",
    }

    for relative in expected_importers:
        source = (root / relative).read_text()
        assert "from backend.core.paths import confine_path" in source or (
            "from ..core.paths import confine_path" in source
        ), relative
        assert "_safe_export_path" not in source, relative
        assert "confine_path(" in source, relative

    reconstruction = (root / "backend/services/reconstruction.py").read_text()
    assert "def _safe_export_path" not in reconstruction
