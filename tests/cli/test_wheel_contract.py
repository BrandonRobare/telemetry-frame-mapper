from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path


def _venv_script(venv: Path, name: str) -> Path:
    scripts_dir = "Scripts" if sys.platform == "win32" else "bin"
    suffix = ".exe" if sys.platform == "win32" else ""
    return venv / scripts_dir / f"{name}{suffix}"


def test_wheel_is_cli_only_and_every_console_script_runs(tmp_path: Path) -> None:
    repo_root = Path(__file__).parents[2]
    wheel_dir = tmp_path / "wheel"
    venv_dir = tmp_path / "wheel-venv"

    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(wheel_dir)],
        check=True,
        cwd=repo_root,
    )
    wheel = next(wheel_dir.glob("*.whl"))

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        entry_points_name = next(
            name for name in names if name.endswith(".dist-info/entry_points.txt")
        )
        metadata = archive.read(metadata_name).decode()
        entry_points = archive.read(entry_points_name).decode().splitlines()

    packaged_top_levels = {name.split("/", maxsplit=1)[0] for name in names if name.endswith(".py")}
    assert packaged_top_levels == {"drone_video_geotagger"}
    assert "Provides-Extra:" not in metadata

    console_scripts = {
        line.partition(" = ")[0]
        for line in entry_points
        if " = " in line and not line.startswith("[")
    }
    assert console_scripts == {"drone-video-geotagger", "dvg-pipeline"}

    subprocess.run(["uv", "venv", "--clear", "--python", sys.executable, str(venv_dir)], check=True)
    wheel_python = _venv_script(venv_dir, "python")
    subprocess.run(
        ["uv", "pip", "install", "--python", str(wheel_python), str(wheel)],
        check=True,
    )

    for script in console_scripts:
        result = subprocess.run(
            [_venv_script(venv_dir, script), "--help"],
            capture_output=True,
            check=False,
            text=True,
        )
        assert result.returncode == 0, result.stderr
