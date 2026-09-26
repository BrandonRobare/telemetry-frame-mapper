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
        # Compare original spellings before realpath erases traversal/symlinks.
        # A configured root may contain '..' or be a symlink; a previously returned
        # canonical child may therefore start at the root's real location instead.
        for base in (root, Path(os.path.abspath(root)), Path(os.path.realpath(root))):
            try:
                child = path.relative_to(base)
            except ValueError:
                continue
            # Backslash is a foreign separator only on POSIX; WindowsPath uses it
            # for every ordinary child. Never allow aliases in the child suffix.
            if ".." in child.parts or (os.sep != "\\" and "\\" in str(child)):
                raise ValueError(f"Path {path} is outside {boundary_name}")
            current = base
            for part in child.parts:
                current = current / part
                if current.is_symlink():
                    raise ValueError(f"Path {path} is outside {boundary_name}")
            break
        else:
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
