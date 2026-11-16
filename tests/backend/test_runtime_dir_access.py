"""Startup refuses runtime directories the backend cannot write (non-root Docker upgrades)."""

from __future__ import annotations

import asyncio
import os
import stat
from types import SimpleNamespace

import pytest

import backend.main as main
from backend.core.paths import require_writable_runtime_dirs


@pytest.fixture
def unwritable_dir(tmp_path):
    path = tmp_path / "exports"
    path.mkdir()
    path.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        if os.access(path, os.W_OK):
            pytest.skip("chmod cannot make a directory unwritable here (Windows or root)")
        yield path
    finally:
        path.chmod(stat.S_IRWXU)


def test_unwritable_dir_fails_fast_naming_dir_uid_and_fix(tmp_path, unwritable_dir):
    writable = tmp_path / "data"
    writable.mkdir()

    with pytest.raises(PermissionError) as exc_info:
        require_writable_runtime_dirs({"data_dir": writable, "exports_dir": unwritable_dir})

    message = str(exc_info.value)
    uid, gid = os.getuid(), os.getgid()
    assert f"exports_dir {unwritable_dir}" in message
    assert f"UID {uid}" in message
    assert f"chown -R {uid}:{gid} {unwritable_dir}" in message
    assert str(writable) not in message


def test_every_unwritable_dir_is_reported_in_one_error(tmp_path, monkeypatch):
    """Runs everywhere (including as root): simulate the access check failing."""
    import backend.core.paths as paths

    dirs = {name: tmp_path / name for name in ("data", "imports", "processed", "exports")}
    for path in dirs.values():
        path.mkdir()
    unwritable = {dirs["data"], dirs["exports"]}
    real_access = os.access
    monkeypatch.setattr(
        paths.os,
        "access",
        lambda path, mode: False if path in unwritable else real_access(path, mode),
    )

    with pytest.raises(PermissionError) as exc_info:
        require_writable_runtime_dirs({f"{name}_dir": path for name, path in dirs.items()})

    message = str(exc_info.value)
    assert f"data_dir {dirs['data']}" in message
    assert f"exports_dir {dirs['exports']}" in message
    assert str(dirs["imports"]) not in message
    assert "README" in message
    if hasattr(os, "getuid"):
        uid, gid = os.getuid(), os.getgid()
        assert f"UID {uid}" in message
        assert f"chown -R {uid}:{gid} {dirs['data']}" in message


def test_writable_and_missing_dirs_pass(tmp_path):
    writable = tmp_path / "data"
    writable.mkdir()
    # Not created yet: the app creates it when it first needs it.
    require_writable_runtime_dirs({"data_dir": writable, "imports_dir": tmp_path / "later"})
    assert writable.is_dir()
    assert not (tmp_path / "later").exists()


def test_lifespan_checks_runtime_dirs_before_opening_the_database(tmp_path, monkeypatch):
    calls = []
    cfg = SimpleNamespace(
        data_dir=str(tmp_path / "data"),
        imports_dir=str(tmp_path / "imports"),
        processed_dir=str(tmp_path / "processed"),
        exports_dir=str(tmp_path / "exports"),
    )

    def refuse(dirs):
        calls.append(("check", dict(dirs)))
        raise PermissionError("exports_dir is not writable")

    monkeypatch.setattr(main, "get_config", lambda: cfg)
    monkeypatch.setattr(main, "require_writable_runtime_dirs", refuse)
    monkeypatch.setattr(main, "configure_application_logging", lambda config: None)
    monkeypatch.setattr(main, "init_db", lambda: calls.append(("init_db", None)))

    async def open_lifespan():
        async with main.lifespan(main.app):
            pass

    with pytest.raises(PermissionError, match="not writable"):
        asyncio.run(open_lifespan())

    assert calls == [
        (
            "check",
            {
                "data_dir": cfg.data_dir,
                "imports_dir": cfg.imports_dir,
                "processed_dir": cfg.processed_dir,
                "exports_dir": cfg.exports_dir,
            },
        )
    ]
