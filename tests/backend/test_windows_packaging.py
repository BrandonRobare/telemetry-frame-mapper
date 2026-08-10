from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_windows_packaging_assets_include_frontend_config_and_user_data_hook() -> None:
    build_script = (ROOT / "packaging" / "build-windows.ps1").read_text(encoding="utf-8")
    runtime_hook = (ROOT / "packaging" / "runtime_hook.py").read_text(encoding="utf-8")
    installer = (ROOT / "packaging" / "telemetry-frame-mapper.iss").read_text(encoding="utf-8")

    assert "frontend/dist;frontend/dist" in build_script
    assert "config.yaml;." in build_script
    assert "alembic.ini;." in build_script
    assert "backend/db/migrations;backend/db/migrations" in build_script
    assert "$LASTEXITCODE" in build_script
    assert "runtime_hook.py" in build_script
    assert 'Path(os.environ.get("LOCALAPPDATA"' in runtime_hook
    assert '"data", "imports", "processed", "exports"' in runtime_hook
    assert 'Source: "..\\dist\\Telemetry Frame Mapper\\*"' in installer
    assert 'WorkingDir: "{localappdata}\\Telemetry Frame Mapper"' in installer


def test_ci_builds_and_smokes_the_windows_bundle() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    smoke_script = ROOT / "packaging" / "smoke-windows.ps1"

    assert "windows-package:" in workflow
    assert "packaging/build-windows.ps1" in workflow
    assert "packaging/smoke-windows.ps1" in workflow
    assert smoke_script.is_file()

    smoke = smoke_script.read_text(encoding="utf-8")
    assert "LOCALAPPDATA" in smoke
    assert "/health" in smoke
    assert "alembic_version" in smoke
