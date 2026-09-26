"""Regression and structural coverage for the shared filesystem confinement boundary."""

import os
from pathlib import Path, PureWindowsPath

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


def test_confine_path_rejects_sibling_whose_name_extends_the_root(tmp_path):
    # The classic prefix-check trap: "/tmp/x/exports2/evil" starts with the plain
    # string "/tmp/x/exports" even though it is a sibling, not a descendant. The
    # containment check must anchor on a path separator, not a bare string prefix.
    root = tmp_path / "exports"
    sibling = tmp_path / "exports2"
    sibling.mkdir()

    with pytest.raises(ValueError, match="outside allowed directory"):
        confine_path(sibling / "evil.zip", root)


def test_confine_path_treats_filesystem_root_as_a_trailing_separator_root(tmp_path):
    # os.path.normpath keeps the trailing separator only for an actual filesystem
    # root ("/" on POSIX, a drive root on Windows). The prefix built from it must
    # not double that separator, which would then reject every real child.
    fs_root = Path(os.path.abspath(os.sep))
    candidate = tmp_path / "nested" / "artifact.bin"
    assert confine_path(candidate, fs_root) == Path(os.path.realpath(candidate))


@pytest.mark.skipif(os.name != "nt", reason="drive letters only exist on Windows")
def test_confine_path_rejects_different_drive_without_raising(tmp_path):
    root = Path("C:\\exports")
    other_drive = Path("D:\\exports\\evil.zip")

    with pytest.raises(ValueError, match="outside allowed directory"):
        confine_path(other_drive, root)


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


@pytest.mark.parametrize("escaping", ["../escape.zip", "../../escape.zip"])
def test_atomic_zip_rejects_paths_outside_root(tmp_path, escaping):
    """_atomic_zip confines its own target before replacing or unlinking it (#641)."""
    from backend.routers.export import _atomic_zip

    root = tmp_path / "exports"
    root.mkdir()
    victim = tmp_path / "escape.zip"
    victim.write_bytes(b"pre-existing")

    with pytest.raises(ValueError, match="outside exports directory"):
        with _atomic_zip(root / escaping, root):
            pass

    assert victim.read_bytes() == b"pre-existing"
    assert not list(root.iterdir())


@pytest.mark.parametrize("kind", ["traversal", "symlink_parent", "symlink_target"])
def test_atomic_zip_rejects_aliases_within_root_without_modifying_target(tmp_path, kind):
    from backend.routers.export import _atomic_zip

    root = tmp_path / "exports"
    real = root / "real"
    real.mkdir(parents=True)
    target = real / "bundle.zip"
    target.write_bytes(b"original")
    if kind == "traversal":
        candidate = real / ".." / "real" / "bundle.zip"
    elif kind == "symlink_parent":
        (root / "alias").symlink_to(real, target_is_directory=True)
        candidate = root / "alias" / "bundle.zip"
    else:
        candidate = root / "bundle.zip"
        candidate.symlink_to(target)
    with pytest.raises(ValueError, match="outside exports directory"):
        with _atomic_zip(candidate, root):
            pass
    assert target.read_bytes() == b"original"
    assert not list(root.glob("*.tmp"))


def test_atomic_zip_preserves_configured_symlink_root(tmp_path):
    from backend.routers.export import _atomic_zip

    real = tmp_path / "real"
    real.mkdir()
    root = tmp_path / "configured-exports"
    root.symlink_to(real, target_is_directory=True)
    with _atomic_zip(root / "bundle.zip", root) as zf:
        zf.writestr("manifest.json", "{}")
    assert (real / "bundle.zip").is_file()


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows filesystem paths")
def test_windows_native_paths_work_for_confined_atomic_zip(tmp_path):
    from backend.routers.export import _atomic_zip

    root = tmp_path / "exports"
    root.mkdir()
    target = Path(PureWindowsPath(root / "nested" / "bundle.zip"))
    target.parent.mkdir()
    assert "\\" in str(PureWindowsPath(target))
    assert confine_path(target, root, reject_aliases=True) == target
    with _atomic_zip(target, root) as zf:
        zf.writestr("manifest.json", "{}")
    assert target.is_file()


def test_canonical_child_of_configured_symlink_root_remains_confined(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    root = tmp_path / "exports"
    root.symlink_to(real, target_is_directory=True)
    canonical_child = confine_path(root / "bundle.zip", root, reject_aliases=True)
    assert canonical_child == real / "bundle.zip"
    assert confine_path(canonical_child, root, reject_aliases=True) == canonical_child

    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"secret")
    (real / "alias.zip").symlink_to(outside)
    with pytest.raises(ValueError, match="outside allowed directory"):
        confine_path(real / "alias.zip", root, reject_aliases=True)


@pytest.mark.skipif(os.name == "nt", reason="backslash is native on Windows")
def test_posix_rejects_foreign_backslash_below_root(tmp_path):
    with pytest.raises(ValueError, match="outside allowed directory"):
        confine_path(tmp_path / r"sub\bundle.zip", tmp_path, reject_aliases=True)


def test_configured_root_parent_spelling_does_not_reject_its_own_children(tmp_path):
    (tmp_path / "intermediate").mkdir()
    root = tmp_path / "intermediate" / ".." / "exports"
    root.mkdir()
    child = root / "bundle.zip"
    assert confine_path(child, root, reject_aliases=True) == tmp_path / "exports" / "bundle.zip"
    with pytest.raises(ValueError, match="outside allowed directory"):
        confine_path(root / "sub" / ".." / "bundle.zip", root, reject_aliases=True)
