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
    reject_aliases: bool = False,
) -> Path:
    """Resolve *path* and reject it unless it remains inside *root*.

    ``realpath`` follows existing symlinks and normalizes both case and separators,
    so the containment decision has the same Windows behavior as the previous
    export-specific guard. ``reject_aliases`` additionally disallows lexical parent
    traversal and symlink components below the configured root for untrusted paths.
    The returned path is canonical and safe at the time it is checked.
    """
    if reject_aliases:
        # Inspect the original spelling before realpath erases traversal/symlinks.
        # The configured root may itself be a symlink; only its children are untrusted.
        if ".." in path.parts or "\\" in str(path):
            raise ValueError(f"Path {path} is outside {boundary_name}")
        root_lexical = Path(os.path.abspath(root))
        try:
            child = Path(os.path.abspath(path)).relative_to(root_lexical)
        except ValueError as exc:
            raise ValueError(f"Path {path} is outside {boundary_name}") from exc
        current = root_lexical
        for part in child.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"Path {path} is outside {boundary_name}")
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
