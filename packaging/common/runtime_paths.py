from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable, MutableMapping
from pathlib import Path

APP_NAME = "Telemetry Frame Mapper"
MACOS_EXECUTABLE_PATHS = ("/opt/homebrew/bin", "/usr/local/bin")


def prepend_macos_executable_paths(
    *,
    platform: str | None = None,
    environ: MutableMapping[str, str] | None = None,
    is_dir: Callable[[str], bool] | None = None,
) -> None:
    """Expose existing Homebrew tools to Finder/launchd-started macOS bundles."""
    if (platform or sys.platform) != "darwin":
        return

    target_environ = environ if environ is not None else os.environ
    current_path = target_environ.get("PATH", "")
    current_entries = current_path.split(os.pathsep) if current_path else []
    directory_exists = is_dir or (lambda value: Path(value).is_dir())
    additions = [
        path
        for path in MACOS_EXECUTABLE_PATHS
        if path not in current_entries and directory_exists(path)
    ]
    if additions:
        prefix = os.pathsep.join(additions)
        target_environ["PATH"] = prefix + (os.pathsep + current_path if current_path else "")


def resolve_app_data_dir(
    *,
    platform: str | None = None,
    local_app_data: Path | None = None,
    home: Path | None = None,
) -> Path:
    """Return the per-user writable directory for the current desktop platform."""
    current_platform = platform or sys.platform
    current_home = home or Path.home()

    if current_platform == "win32":
        return (local_app_data or Path(os.environ.get("LOCALAPPDATA", current_home))) / APP_NAME
    if current_platform == "darwin":
        return current_home / "Library" / "Application Support" / APP_NAME
    return current_home / APP_NAME


def _merge_current_defaults(
    stored: dict[str, object], defaults: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    """Merge a stored config with current defaults; return (merged, removed).

    Values of keys that still exist are kept as stored. Keys only present in
    *defaults* take their default values. Keys only present in *stored* are
    collected into ``removed`` (for quarantine) — that is the #804 class of
    rot that otherwise survives upgrades forever (#871).
    """
    merged: dict[str, object] = {}
    removed: dict[str, object] = {}
    for key, value in defaults.items():
        existing = stored.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            sub_merged, sub_removed = _merge_current_defaults(existing, value)
            merged[key] = sub_merged
            if sub_removed:
                removed[key] = sub_removed
        else:
            merged[key] = existing if existing is not None else value
    for key in stored:
        if key not in defaults:
            removed[key] = stored[key]
    return merged, removed


def initialize_application_data() -> None:
    """Initialize writable bundled-app data before the backend process starts."""
    prepend_macos_executable_paths()
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    app_data = resolve_app_data_dir()
    app_data.mkdir(parents=True, exist_ok=True)

    config = app_data / "config.yaml"
    if not config.exists():
        shutil.copyfile(bundle_root / "config.yaml", config)
    else:
        # Upgrade path: reconcile an old first-run config with current
        # defaults — drop removed keys into a legacy quarantine and add new
        # defaults — instead of letting a stale file shadow the release (#871).
        import yaml

        try:
            stored = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
            defaults = yaml.safe_load(
                (bundle_root / "config.yaml").read_text(encoding="utf-8")
            ) or {}
            merged, removed = _merge_current_defaults(stored, defaults)
            rendered = yaml.safe_dump(merged, sort_keys=False)
            if rendered != config.read_text(encoding="utf-8"):
                if removed:
                    shutil.copyfile(config, config.with_name("config.yaml.legacy"))
                config.write_text(rendered, encoding="utf-8")
        except (OSError, yaml.YAMLError):
            # Corrupt or unreadable stored config: leave it untouched rather
            # than destroying operator data. The app logs its own failure.
            pass

    for name in ("data", "imports", "processed", "exports"):
        (app_data / name).mkdir(exist_ok=True)

    os.chdir(app_data)


if getattr(sys, "frozen", False):
    initialize_application_data()
