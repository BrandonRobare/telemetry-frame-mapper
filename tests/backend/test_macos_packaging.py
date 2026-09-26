import importlib.util
import re
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MACOS_PACKAGING = ROOT / "packaging" / "macos"
BUILD_SCRIPT = MACOS_PACKAGING / "build.sh"
SMOKE_SCRIPT = MACOS_PACKAGING / "smoke.sh"
RUNTIME_PATHS = ROOT / "packaging" / "common" / "runtime_paths.py"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


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
    assert (
        "uv run --frozen --no-sync python -m PyInstaller "
        "--noconfirm --clean --onedir --windowed"
    ) in build
    assert not re.search(r"^\s*python\b", build, flags=re.MULTILINE)
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
    assert "--collect-all msplat" in build
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
    # Two alembic probes + one /system/resources tool-discovery probe (#832).
    assert smoke.count("uv run --frozen --no-sync python -c") == 3
    assert "$(python -c" not in smoke
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


def test_runtime_hook_reconciles_old_config_with_defaults() -> None:
    runtime_paths = _load_runtime_paths_module()
    stored = {
        "reconstruction": {"presets": {"quick": {"max_frames": 500, "sh_degree": 3}}},
        "deployment": {"host": "0.0.0.0", "port": 8000, "auto_open_browser": False},
    }
    defaults = {
        "reconstruction": {"presets": {"quick": {"sh_degree": 1, "downscale_factor": 4}}},
        "deployment": {"host": "127.0.0.1", "port": 8000, "cors_origins": ["http://localhost:5173"]},
        "render": {"lod_medium_ratio": 0.5},
    }
    merged, removed = runtime_paths._merge_current_defaults(stored, defaults)

    # Stored values survive, including keys the defaults do not carry.
    assert merged["deployment"]["host"] == "0.0.0.0"
    assert merged["deployment"]["auto_open_browser"] is False
    assert merged["reconstruction"]["presets"]["quick"]["sh_degree"] == 3
    # New defaults are added.
    assert merged["render"]["lod_medium_ratio"] == 0.5
    assert merged["deployment"]["cors_origins"] == ["http://localhost:5173"]
    assert merged["reconstruction"]["presets"]["quick"]["downscale_factor"] == 4
    # Only retired keys are removed, and they are reported for quarantine.
    assert removed == {"reconstruction.presets.quick.max_frames": 500}
    assert "max_frames" not in merged["reconstruction"]["presets"]["quick"]
    # The caller's stored mapping is not mutated.
    assert stored["reconstruction"]["presets"]["quick"]["max_frames"] == 500


def _launch_bundle(runtime_paths, monkeypatch, tmp_path: Path) -> Path:
    """Run the frozen-app hook against the repo config.yaml as bundled defaults."""
    bundle = tmp_path / "bundle"
    bundle.mkdir(exist_ok=True)
    (bundle / "config.yaml").write_bytes((ROOT / "config.yaml").read_bytes())
    app_data = tmp_path / "app-data"
    monkeypatch.setattr(runtime_paths.sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(runtime_paths, "resolve_app_data_dir", lambda: app_data)
    monkeypatch.setattr(runtime_paths, "prepend_macos_executable_paths", lambda: None)
    monkeypatch.chdir(tmp_path)  # the hook chdirs into app data; restore afterwards
    runtime_paths.initialize_application_data()
    return app_data / "config.yaml"


def test_bundle_launch_keeps_valid_keys_absent_from_bundled_defaults(
    monkeypatch, tmp_path
) -> None:
    runtime_paths = _load_runtime_paths_module()
    config = _launch_bundle(runtime_paths, monkeypatch, tmp_path)
    stored = yaml.safe_load(config.read_text(encoding="utf-8"))
    # #833 kill switch, optional and read with a default.
    stored["deployment"]["auto_open_browser"] = False
    # Deliberately omitted from the bundle so accelerator policy fills it.
    stored["reconstruction"]["presets"]["quick"]["iterations"] = 2000
    config.write_text(yaml.safe_dump(stored, sort_keys=False), encoding="utf-8")

    for _ in range(3):
        _launch_bundle(runtime_paths, monkeypatch, tmp_path)

    kept = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert kept["deployment"]["auto_open_browser"] is False
    assert kept["reconstruction"]["presets"]["quick"]["iterations"] == 2000
    assert not config.with_name("config.yaml.legacy").exists()


def test_bundle_launch_quarantines_retired_keys_and_adds_new_defaults(
    monkeypatch, tmp_path
) -> None:
    runtime_paths = _load_runtime_paths_module()
    config = _launch_bundle(runtime_paths, monkeypatch, tmp_path)
    stored = yaml.safe_load(config.read_text(encoding="utf-8"))
    stored["deployment"]["port"] = 9000
    stored["reconstruction"]["presets"]["quick"]["max_frames"] = 500
    stored["reconstruction"]["presets"]["full"]["exhaustive_matching"] = True
    del stored["backup"]["pre_migration_keep"]  # a key an older release did not ship
    old_text = yaml.safe_dump(stored, sort_keys=False)
    config.write_text(old_text, encoding="utf-8")

    _launch_bundle(runtime_paths, monkeypatch, tmp_path)

    reconciled = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert "max_frames" not in reconciled["reconstruction"]["presets"]["quick"]
    assert "exhaustive_matching" not in reconciled["reconstruction"]["presets"]["full"]
    assert reconciled["backup"]["pre_migration_keep"] == 3
    assert reconciled["deployment"]["port"] == 9000
    assert config.with_name("config.yaml.legacy").read_text(encoding="utf-8") == old_text


def test_bundle_launch_with_nothing_to_change_does_not_rewrite_config(
    monkeypatch, tmp_path
) -> None:
    runtime_paths = _load_runtime_paths_module()
    config = _launch_bundle(runtime_paths, monkeypatch, tmp_path)
    # Hand-edited, commented and formatted differently from yaml.safe_dump.
    edited = config.read_text(encoding="utf-8").replace(
        "  port: 8000", "  port: 9000  # moved off 8000\n  auto_open_browser: no"
    )
    config.write_text(edited, encoding="utf-8")

    for _ in range(2):
        _launch_bundle(runtime_paths, monkeypatch, tmp_path)

    assert config.read_text(encoding="utf-8") == edited
    assert not config.with_name("config.yaml.legacy").exists()


@pytest.mark.parametrize("text", ["deployment: [unclosed\n", "- a list, not a mapping\n"])
def test_bundle_launch_leaves_unusable_config_untouched(monkeypatch, tmp_path, text) -> None:
    runtime_paths = _load_runtime_paths_module()
    config = tmp_path / "app-data" / "config.yaml"
    config.parent.mkdir()
    config.write_text(text, encoding="utf-8")

    _launch_bundle(runtime_paths, monkeypatch, tmp_path)

    assert config.read_text(encoding="utf-8") == text
    assert not config.with_name("config.yaml.legacy").exists()


def test_bundled_defaults_carry_no_retired_keys() -> None:
    from backend.core.retired_config import pop_retired_keys

    defaults = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert pop_retired_keys(defaults) == {}


def test_runtime_hook_prepends_extra_tool_roots_from_env(monkeypatch) -> None:
    runtime_paths = _load_runtime_paths_module()
    environment = {"PATH": "/usr/bin:/bin"}
    monkeypatch.setenv(runtime_paths._EXTRA_TOOL_ROOTS_ENV, "/opt/local/bin")
    existing = {"/usr/local/bin", "/opt/local/bin", "/opt/homebrew/bin"}

    runtime_paths.prepend_macos_executable_paths(
        platform="darwin",
        environ=environment,
        is_dir=existing.__contains__,
    )

    parts = environment["PATH"].split(":")
    assert "/opt/local/bin" in parts
    assert parts.index("/opt/local/bin") < parts.index("/usr/bin")


def test_macos_packaging_scripts_have_no_nonportable_environment_assumptions() -> None:
    for script in (BUILD_SCRIPT, SMOKE_SCRIPT):
        source = _read_executable_shell_script(script)
        assert "LOCALAPPDATA" not in source
        assert "powershell" not in source.lower()
        add_data_sources = re.findall(r'--add-data "([^"]+)"', source)
        assert all(";" not in add_data_source for add_data_source in add_data_sources)
        assert "\r\n" not in source


def test_macos_ci_runs_full_arm64_bundle_and_real_tool_contract() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(
        r"^  macos-package:\n(?P<body>.*?)(?=^  [a-z][\w-]*:\n|\Z)",
        ci,
        flags=re.MULTILINE | re.DOTALL,
    )

    assert match is not None
    body = match.group("body")
    normalized_body = " ".join(body.split())
    assert "runs-on: macos-latest" in body
    assert 'test "$(uname -m)" = "arm64"' in body
    assert "brew install ffmpeg exiftool colmap" in body
    assert "for tool in ffmpeg exiftool colmap" in body
    assert 'command -v "$tool"' in body
    assert (
        "uv sync --frozen --group backend --group reconstruction "
        "--group desktop-package --group splat-metal --group dev --group audit"
    ) in normalized_body
    assert "python tests/test_supply_chain_configuration.py" in body
    assert "uv lock --check" in body
    assert "pip-audit -r /tmp/macos-runtime-requirements.txt" in body
    assert "uv run --frozen --no-sync ruff check ." in body
    assert re.search(r"run: uv run --frozen --no-sync pytest\s*$", body, flags=re.MULTILINE)
    assert "npm ci" in body
    assert "npm run build" in body
    assert "get_resources" in body
    assert 'resources["colmap_capabilities"]["available"]' in body
    assert "packaging/macos/build.sh" in body
    assert "packaging/macos/smoke.sh" in body
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in body
    assert "dist/Telemetry Frame Mapper.app" in body
