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

    Containment itself is decided with a ``startswith`` prefix check directly on
    ``path_real`` — the same normalized string this function returns — rather than
    on a value derived from it (``os.path.relpath``'s result, as a prior version of
    this function used). A guard on a derived value doesn't tie back to the
    returned value for static taint analysis; a guard on the returned value itself
    does.
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
    if path_real == root_real:
        if not allow_root:
            raise ValueError(f"Path {path} is outside {boundary_name}")
        # The strings are equal here, so this is the same value either way — but
        # CodeQL doesn't treat equality with a non-constant as a barrier, so
        # returning path_real (derived from the untrusted path) still reads as
        # tainted. Return root_real instead: it derives only from the trusted
        # root argument, so this branch is provably clean.
        return Path(root_real)
    # A bare prefix check would let a sibling whose name extends the root's — e.g.
    # root "/data/exports" and path "/data/exports2/x" — pass, since the string
    # "/data/exports2/x" starts with "/data/exports". Anchor the prefix on a
    # trailing separator (unless root_real already ends in one, i.e. it's a
    # filesystem root like "/" or "C:\\") so only real descendants match. This is
    # also why cross-drive Windows paths need no special case: "d:\\x" never
    # starts with "c:\\..." however it's spelled.
    root_prefix = root_real if root_real.endswith(os.sep) else root_real + os.sep
    if not path_real.startswith(root_prefix):
        raise ValueError(f"Path {path} is outside {boundary_name}")
    return Path(path_real)
