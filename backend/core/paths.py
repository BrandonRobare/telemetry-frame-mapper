"""Dependency-light guards for paths that cross a filesystem trust boundary."""

from __future__ import annotations

import os
from pathlib import Path


def confine_path(
    path: Path,
    root: Path,
    *,
    allow_root: bool = False,
    boundary_name: str = "allowed directory",
) -> Path:
    """Resolve *path* and reject it unless it remains inside *root*.

    ``realpath`` follows existing symlinks and normalizes both case and separators,
    so the containment decision has the same Windows behavior as the previous
    export-specific guard.  The returned path is canonical and safe for the caller
    to read or write at the time it is checked.
    """
    root_real = os.path.normcase(os.path.normpath(os.path.realpath(root)))
    path_real = os.path.normcase(os.path.normpath(os.path.realpath(path)))
    try:
        relative = os.path.relpath(path_real, root_real)
    except ValueError as exc:  # Different Windows drives.
        raise ValueError(f"Path {path} is outside {boundary_name}") from exc
    if relative == os.pardir or relative.startswith(f"{os.pardir}{os.sep}"):
        raise ValueError(f"Path {path} is outside {boundary_name}")
    if not allow_root and relative == os.curdir:
        raise ValueError(f"Path {path} is outside {boundary_name}")
    return Path(path_real)
