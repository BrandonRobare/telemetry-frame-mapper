import importlib.util
import re
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MACOS_PACKAGING = ROOT / "packaging" / "macos"
BUILD_SCRIPT = MACOS_PACKAGING / "build.sh"
SMOKE_SCRIPT = MACOS_PACKAGING / "smoke.sh"
RUNTIME_PATHS = ROOT / "packaging" / "common" / "runtime_paths.py"


def _load_runtime_paths_module():
    spec = importlib.util.spec_from_file_location("macos_runtime_paths_test_module", RUNTIME_PATHS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_executable_shell_script(path: Path) -> str:
    assert path.is_file(), f"Missing macOS packaging script: {path}"
    assert path.stat().st_mode & stat.S_IXUSR, f"Script is not executable: {path}"
    subprocess.run(["bash", "-n", str(path)], check=True)
    return path.read_text(encoding="utf-8")


def test_macos_build_script_uses_windowed_posix_pyinstaller_bundle_contract() -> None:
    build = _read_executable_shell_script(BUILD_SCRIPT)

    assert build.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in build
    assert '[[ "$(uname -m)" != "arm64" ]]' in build
    assert "frontend/dist/index.html" in build
    assert "python -m PyInstaller --noconfirm --clean --onedir --windowed" in build
    assert '--name "Telemetry Frame Mapper"' in build
    assert "--runtime-hook \"$repo_root/packaging/common/runtime_paths.py\"" in build
    for asset in (
        "config.yaml:.",
        "alembic.ini:.",
        "backend/db/migrations:backend/db/migrations",
        "frontend/dist:frontend/dist",
    ):
        assert asset in build
    add_data_sources = re.findall(r'--add-data "([^"]+)"', build)
    assert add_data_sources == [
        "$repo_root/config.yaml:.",
        "$repo_root/alembic.ini:.",
        "$repo_root/backend/db/migrations:backend/db/migrations",
        "$repo_root/frontend/dist:frontend/dist",
    ]
    assert all(";" not in source for source in add_data_sources)
    assert "--collect-all backend" in build
    assert "--collect-all drone_video_geotagger" in build
    assert build.rstrip().endswith("backend/__main__.py")
    assert "resolve_app_data_dir" in RUNTIME_PATHS.read_text(encoding="utf-8")


def test_macos_smoke_script_uses_fresh_home_health_migrations_and_cleanup_contract() -> None:
    smoke = _read_executable_shell_script(SMOKE_SCRIPT)

    assert smoke.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in smoke
    assert 'dist/Telemetry Frame Mapper.app/Contents/MacOS/Telemetry Frame Mapper' in smoke
    assert "mktemp -d" in smoke
    assert 'HOME="$smoke_root"' in smoke
    assert 'PATH="/usr/bin:/bin:/usr/sbin:/sbin"' in smoke
    assert 'health_url="http://127.0.0.1:8000/health"' in smoke
    assert 'curl --fail --silent --show-error --max-time 2 "$health_url"' in smoke
    assert "Packaged app exited before health check" in smoke
    assert "Packaged app did not become healthy" in smoke
    assert "alembic_version" in smoke
    assert "get_current_head()" in smoke
    assert "Migration head mismatch" in smoke
    assert "kill -0 \"$app_pid\"" in smoke
    assert "rm -rf \"$smoke_root\"" in smoke
    assert "trap cleanup EXIT" in smoke


def test_macos_runtime_hook_prepends_only_existing_missing_homebrew_paths() -> None:
    runtime_paths = _load_runtime_paths_module()
    environment = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
    existing = {"/opt/homebrew/bin", "/usr/local/bin"}

    runtime_paths.prepend_macos_executable_paths(
        platform="darwin",
        environ=environment,
        is_dir=existing.__contains__,
    )

    assert environment["PATH"] == "/opt/homebrew/bin:/usr/bin:/bin:/usr/local/bin"

    no_homebrew_environment = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    runtime_paths.prepend_macos_executable_paths(
        platform="darwin",
        environ=no_homebrew_environment,
        is_dir=lambda _path: False,
    )
    assert no_homebrew_environment["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"


def test_runtime_hook_does_not_change_path_outside_macos() -> None:
    runtime_paths = _load_runtime_paths_module()
    environment = {"PATH": "/usr/bin:/bin"}

    runtime_paths.prepend_macos_executable_paths(
        platform="linux",
        environ=environment,
        is_dir=lambda _path: True,
    )

    assert environment["PATH"] == "/usr/bin:/bin"


def test_macos_packaging_scripts_have_no_nonportable_environment_assumptions() -> None:
    for script in (BUILD_SCRIPT, SMOKE_SCRIPT):
        source = _read_executable_shell_script(script)
        assert "LOCALAPPDATA" not in source
        assert "powershell" not in source.lower()
        add_data_sources = re.findall(r'--add-data "([^"]+)"', source)
        assert all(";" not in add_data_source for add_data_source in add_data_sources)
        assert "\r\n" not in source
