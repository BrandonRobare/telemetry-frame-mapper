from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Telemetry Frame Mapper"


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


def initialize_application_data() -> None:
    """Initialize writable bundled-app data before the backend process starts."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    app_data = resolve_app_data_dir()
    app_data.mkdir(parents=True, exist_ok=True)

    config = app_data / "config.yaml"
    if not config.exists():
        shutil.copyfile(bundle_root / "config.yaml", config)

    for name in ("data", "imports", "processed", "exports"):
        (app_data / name).mkdir(exist_ok=True)

    os.chdir(app_data)


if getattr(sys, "frozen", False):
    initialize_application_data()
