from __future__ import annotations

import platform
from pathlib import Path


def is_wsl() -> bool:
    return "microsoft" in platform.release().lower()


def is_windows_executable(executable: str | Path) -> bool:
    return str(executable).lower().endswith(".exe")


def windows_path(path: Path) -> str:
    resolved = path.resolve()
    parts = resolved.parts
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "mnt" and len(parts[2]) == 1:
        drive = parts[2].upper()
        rest = "\\".join(parts[3:])
        return f"{drive}:\\{rest}"
    return str(resolved)


def external_file_arg(path: Path, executable: str | Path) -> str:
    if is_wsl() and is_windows_executable(executable):
        return windows_path(path)
    return str(path)
