from __future__ import annotations

import platform
import sys
from pathlib import Path


def force_utf8_streams() -> None:
    """Make stdout/stderr UTF-8 so redirected output cannot raise UnicodeEncodeError.

    Windows falls back to the ANSI code page for stdout/stderr whenever they are
    redirected to a pipe or file rather than attached to a console. Printing
    anything outside that code page then raises — including this project's own
    output literals (``\\u2192``), not just non-ASCII paths. Because the failing
    print happens after the work is done, the command reports failure on a run
    that fully succeeded.

    Call once at the top of every console-script entry point.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


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
