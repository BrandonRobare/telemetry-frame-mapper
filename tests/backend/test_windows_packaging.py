from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_windows_packaging_assets_include_frontend_config_and_user_data_hook() -> None:
    build_script = (ROOT / "packaging" / "build-windows.ps1").read_text(encoding="utf-8")
    runtime_hook = (ROOT / "packaging" / "runtime_hook.py").read_text(encoding="utf-8")
    installer = (ROOT / "packaging" / "telemetry-frame-mapper.iss").read_text(encoding="utf-8")

    assert "frontend/dist;frontend/dist" in build_script
    assert "config.yaml;." in build_script
    assert "runtime_hook.py" in build_script
    assert 'Path(os.environ.get("LOCALAPPDATA"' in runtime_hook
    assert '"data", "imports", "processed", "exports"' in runtime_hook
    assert 'Source: "..\\dist\\Telemetry Frame Mapper\\*"' in installer
    assert 'WorkingDir: "{localappdata}\\Telemetry Frame Mapper"' in installer
