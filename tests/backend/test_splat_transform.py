"""Tests for splat_transform — the npx @playcanvas/splat-transform subprocess wrapper."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.services.splat_transform import cleanup_splat, compress_splat

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
    assert run.call_args.args[0][:2] == ["/usr/bin/npx", "@playcanvas/splat-transform"]
