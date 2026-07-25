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
    """Return a safe CLI argument string for a file path.

    Resolves to absolute form to prevent dash-prefix injection where
    `-relative/path` could be parsed as an ExifTool option.

    Rejects newlines outright: ExifTool's ``-@ argfile`` format is one argument per
    line, so a frame named ``frame\\n-config\\n/tmp/evil.cfg\\n001.jpg`` would inject
    ``-config`` — which loads a Perl file — into the argument list.
    """
    arg = (
        windows_path(path)
        if is_wsl() and is_windows_executable(executable)
        else str(path.resolve())
    )
    if "\n" in arg or "\r" in arg:
        raise ValueError(f"Refusing to pass a path containing a newline to {executable}: {arg!r}")
    return arg
