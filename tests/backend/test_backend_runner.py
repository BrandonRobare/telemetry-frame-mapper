from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

from backend import __main__
from backend.core.config import get_deployment_config

ROOT = Path(__file__).resolve().parents[2]


def test_runner_uses_deployment_profile(monkeypatch):
    deployment = {"host": "192.168.1.50", "port": 8080, "cors_origins": []}
    monkeypatch.setattr(__main__, "get_deployment_config", lambda: deployment)
    calls = []
    monkeypatch.setattr(
        __main__.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    __main__.main()

    assert calls == [
        (("backend.main:app",), {"host": "192.168.1.50", "port": 8080, "workers": 1})
    ]


def test_docker_launcher_uses_validated_deployment_bind(monkeypatch, tmp_path) -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    docker_cmd_line = next(line for line in dockerfile.splitlines() if line.startswith("CMD "))
    docker_cmd = json.loads(docker_cmd_line[4:])

    assert "DEPLOYMENT_HOST=0.0.0.0" in dockerfile
    assert docker_cmd == ["python", "-m", "backend"]
    assert "Reject the default unauthenticated LAN bind" in workflow
    assert "allow_unauthenticated_lan: true" in workflow

    monkeypatch.setenv("DEPLOYMENT_HOST", "0.0.0.0")
    with pytest.raises(ValueError, match="not loopback but no authentication"):
        get_deployment_config(str(tmp_path / "config.yaml"))


def test_packaged_launchers_use_one_api_worker() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    windows_build = (ROOT / "packaging" / "build-windows.ps1").read_text(encoding="utf-8")

    docker_cmd_lines = [line for line in dockerfile.splitlines() if line.startswith("CMD ")]
    docker_cmd = json.loads(docker_cmd_lines[-1].removeprefix("CMD "))
    assert docker_cmd == ["python", "-m", "backend"]

    lines = windows_build.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("python -m PyInstaller"))
    end = next(i for i, line in enumerate(lines[start:], start) if not line.rstrip().endswith("`"))
    command = " ".join(line.strip().removesuffix("`") for line in lines[start : end + 1])
    windows_args = shlex.split(command)
    assert windows_args[:3] == ["python", "-m", "PyInstaller"]
    assert windows_args[-1] == "backend/__main__.py"
