from __future__ import annotations

import importlib.util
from pathlib import Path


def test_cli_package_resolves_to_repo_src() -> None:
    spec = importlib.util.find_spec("drone_video_geotagger")

    assert spec is not None
    assert spec.origin is not None
    assert Path(spec.origin).resolve().is_relative_to((Path.cwd() / "src").resolve())
