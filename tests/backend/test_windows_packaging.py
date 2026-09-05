import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WINDOWS_PACKAGING = ROOT / "packaging" / "windows"
RUNTIME_PATHS = ROOT / "packaging" / "common" / "runtime_paths.py"


def _load_runtime_paths_module():
    spec = importlib.util.spec_from_file_location("runtime_paths_test_module", RUNTIME_PATHS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_packaging_assets_include_frontend_config_and_user_data_hook() -> None:
    build_script = (WINDOWS_PACKAGING / "build.ps1").read_text(encoding="utf-8")
    runtime_paths = RUNTIME_PATHS.read_text(encoding="utf-8")
    installer = (WINDOWS_PACKAGING / "telemetry-frame-mapper.iss").read_text(encoding="utf-8")

    assert "frontend/dist;frontend/dist" in build_script
    assert "config.yaml;." in build_script
    assert "alembic.ini;." in build_script
    assert "backend/db/migrations;backend/db/migrations" in build_script
    assert "$LASTEXITCODE" in build_script
    assert "packaging/common/runtime_paths.py" in build_script
    assert "resolve_app_data_dir" in runtime_paths
    assert '"data", "imports", "processed", "exports"' in runtime_paths
    assert 'Source: "..\\..\\dist\\Telemetry Frame Mapper\\*"' in installer
    assert 'WorkingDir: "{localappdata}\\Telemetry Frame Mapper"' in installer


def test_ci_builds_and_smokes_the_windows_bundle() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    smoke_script = WINDOWS_PACKAGING / "smoke.ps1"

    assert "desktop-package =" in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "--group desktop-package" in workflow
    assert "packaging/windows/build.ps1" in workflow
    assert "packaging/windows/smoke.ps1" in workflow
    assert smoke_script.is_file()

    smoke = smoke_script.read_text(encoding="utf-8")
    assert "LOCALAPPDATA" in smoke
    assert "/health" in smoke
    assert "alembic_version" in smoke


def test_runtime_paths_preserve_windows_data_and_use_macos_application_support(monkeypatch) -> None:
    runtime_paths = _load_runtime_paths_module()
    home = Path("/users/example")

    monkeypatch.setattr(runtime_paths.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "/users/example/AppData/Local")
    assert runtime_paths.resolve_app_data_dir() == Path(
        "/users/example/AppData/Local/Telemetry Frame Mapper"
    )
    monkeypatch.delenv("LOCALAPPDATA")
    assert runtime_paths.resolve_app_data_dir(platform="win32", home=home) == (
        home / "Telemetry Frame Mapper"
    )
    assert runtime_paths.resolve_app_data_dir(platform="darwin", home=home) == (
        home / "Library/Application Support/Telemetry Frame Mapper"
    )
