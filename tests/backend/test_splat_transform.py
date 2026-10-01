"""Tests for splat_transform — the pinned @playcanvas/splat-transform subprocess wrapper."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.services import splat_transform
from backend.services.splat_transform import cleanup_splat, compress_splat

TOOL_DIR = Path(__file__).resolve().parents[2] / "tools" / "splat-transform"

_PROBE_OK = {"available": True, "node_path": "/usr/bin/node", "npx_path": "/usr/bin/npx"}


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["npx"], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


def test_cleanup_nonzero_exit_raises_runtime_error(tmp_path):
    """A failed subprocess must not be reported as success (#645)."""
    with (
        patch("backend.services.splat_transform.splat_transform_available",
              return_value=_PROBE_OK),
        patch("backend.services.splat_transform.subprocess.run",
              return_value=_completed(1, stderr="npm ERR! network unreachable")),
    ):
        with pytest.raises(RuntimeError) as exc:
            cleanup_splat(tmp_path / "in.ply", tmp_path / "out.ply")
    assert "network unreachable" in str(exc.value)


def test_cleanup_nonzero_exit_without_stderr_reports_returncode(tmp_path):
    with (
        patch("backend.services.splat_transform.splat_transform_available",
              return_value=_PROBE_OK),
        patch("backend.services.splat_transform.subprocess.run",
              return_value=_completed(3)),
    ):
        with pytest.raises(RuntimeError, match="exited 3"):
            cleanup_splat(tmp_path / "in.ply", tmp_path / "out.ply")


def test_compress_nonzero_exit_raises_runtime_error(tmp_path):
    """The sibling wrapper inherits the same guard."""
    with (
        patch("backend.services.splat_transform.splat_transform_available",
              return_value=_PROBE_OK),
        patch("backend.services.splat_transform.subprocess.run",
              return_value=_completed(1, stderr="unsupported format")),
    ):
        with pytest.raises(RuntimeError, match="unsupported format"):
            compress_splat(tmp_path / "in.ply", tmp_path / "out.spz")


def test_timeout_is_reported_as_runtime_error(tmp_path):
    """TimeoutExpired is a SubprocessError, not a RuntimeError — the routers
    would otherwise let it escape as an unhandled 500."""
    with (
        patch("backend.services.splat_transform.splat_transform_available",
              return_value=_PROBE_OK),
        patch("backend.services.splat_transform.subprocess.run",
              side_effect=subprocess.TimeoutExpired(cmd="npx", timeout=300)),
    ):
        with pytest.raises(RuntimeError, match="timed out"):
            cleanup_splat(tmp_path / "in.ply", tmp_path / "out.ply")


def test_success_returns_completed_process(tmp_path):
    with (
        patch("backend.services.splat_transform.splat_transform_available",
              return_value=_PROBE_OK),
        patch("backend.services.splat_transform.subprocess.run",
              return_value=_completed(0, stdout="done")) as run,
    ):
        result = cleanup_splat(Path(tmp_path / "in.ply"), Path(tmp_path / "out.ply"))
    assert result.returncode == 0
    assert result.stdout == "done"
    assert run.call_args.args[0][0] == "/usr/bin/npx"


def _pinned_version() -> str:
    package = json.loads((TOOL_DIR / "package.json").read_text(encoding="utf-8"))
    return package["dependencies"]["@playcanvas/splat-transform"]


def test_argv_runs_the_pinned_locked_tool_and_never_installs(tmp_path, monkeypatch):
    """No bare `npx <pkg>`: npx would download whatever version the registry serves."""
    monkeypatch.chdir(tmp_path)
    with (
        patch("backend.services.splat_transform.splat_transform_available",
              return_value=_PROBE_OK),
        patch("backend.services.splat_transform.subprocess.run",
              return_value=_completed(0)) as run,
    ):
        cleanup_splat(Path("in.ply"), Path("out.ply"), opacity_floor=None, sh_bands=None)

    argv = run.call_args.args[0]
    version = _pinned_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert argv[:3] == ["/usr/bin/npx", "--no-install", f"@playcanvas/splat-transform@{version}"]
    assert "@playcanvas/splat-transform" not in argv
    # npx resolves the package from the lockfile-installed tool directory...
    assert Path(run.call_args.kwargs["cwd"]) == TOOL_DIR
    # ...so the file arguments must not depend on the caller's working directory.
    assert argv[3:] == [
        "cleanup", str(tmp_path / "in.ply"), str(tmp_path / "out.ply"), "--morton"
    ]


def test_tool_dir_lockfile_pins_the_exact_version():
    version = _pinned_version()
    lock = json.loads((TOOL_DIR / "package-lock.json").read_text(encoding="utf-8"))
    locked = lock["packages"]["node_modules/@playcanvas/splat-transform"]
    assert lock["packages"][""]["dependencies"]["@playcanvas/splat-transform"] == version
    assert locked["version"] == version
    assert locked["integrity"].startswith("sha512-")


def _probe_with_tool_dir(monkeypatch, tool_dir):
    monkeypatch.setattr(splat_transform, "SPLAT_TRANSFORM_TOOL_DIR", tool_dir)
    monkeypatch.setattr(splat_transform.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        splat_transform.subprocess, "run", lambda *a, **k: _completed(0, stdout="v22.12.0")
    )
    splat_transform.clear_splat_transform_cache()
    try:
        return splat_transform.splat_transform_available()
    finally:
        splat_transform.clear_splat_transform_cache()


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_probe_requires_the_locked_install_at_the_pinned_version(tmp_path, monkeypatch):
    tool_dir = tmp_path / "splat-transform"
    _write_json(
        tool_dir / "package.json", {"dependencies": {"@playcanvas/splat-transform": "3.8.0"}}
    )

    missing = _probe_with_tool_dir(monkeypatch, tool_dir)
    assert missing["available"] is False
    assert "npm ci --prefix tools/splat-transform" in missing["reason"]

    installed = tool_dir / "node_modules" / "@playcanvas" / "splat-transform" / "package.json"
    _write_json(installed, {"version": "3.7.0"})
    stale = _probe_with_tool_dir(monkeypatch, tool_dir)
    assert stale["available"] is False
    assert stale["installed_version"] == "3.7.0"

    _write_json(installed, {"version": "3.8.0"})
    ready = _probe_with_tool_dir(monkeypatch, tool_dir)
    assert ready["available"] is True
    assert ready["pinned_version"] == ready["installed_version"] == "3.8.0"


def test_probe_refuses_a_version_range(tmp_path, monkeypatch):
    tool_dir = tmp_path / "splat-transform"
    _write_json(
        tool_dir / "package.json", {"dependencies": {"@playcanvas/splat-transform": "^3.8.0"}}
    )
    probe = _probe_with_tool_dir(monkeypatch, tool_dir)
    assert probe["available"] is False
    assert probe["pinned_version"] is None


def test_unavailable_tool_raises_install_guidance(tmp_path):
    probe = {**_PROBE_OK, "available": False, "reason": "splat-transform is not installed"}
    with (
        patch("backend.services.splat_transform.splat_transform_available", return_value=probe),
        patch("backend.services.splat_transform.subprocess.run") as run,
    ):
        with pytest.raises(RuntimeError, match="not installed"):
            cleanup_splat(tmp_path / "in.ply", tmp_path / "out.ply")
    run.assert_not_called()
