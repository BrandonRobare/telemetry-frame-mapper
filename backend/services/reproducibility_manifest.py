from __future__ import annotations

import hashlib
import logging
import os
import platform
import shutil
import stat
import subprocess
from collections.abc import Iterable
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from backend.core.paths import confine_path


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def binary_version(name: str) -> dict:
    path = shutil.which(name)
    if not path:
        return {"available": False, "path": None, "version": None}
    try:
        proc = subprocess.run(
            [path, "-version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
            check=False,
        )
        version = proc.stdout.splitlines()[0] if proc.stdout else None
    except Exception:
        logging.getLogger("backend").warning("Unable to determine %s version", name, exc_info=True)
        version = "unavailable"
    return {"available": True, "path": path, "version": version}


def _artifact_entry(path: Path, root: Path) -> dict:
    """Inspect a validated path through root-anchored descriptors, not mutable names."""
    entry = {"path": str(path), "exists": False}
    relative = path.relative_to(root)
    parts = relative.parts
    # Never fall back to path-based reads on hosts without descriptor-relative,
    # no-follow opens: a symlink swap after validation would read outside root.
    if not (os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW")):
        raise ValueError("secure manifest artifact inspection is unavailable on this platform")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as stack:
        try:
            directory_fd = os.open(root, directory_flags)
            stack.callback(os.close, directory_fd)
            for part in parts[:-1]:
                directory_fd = os.open(part, directory_flags, dir_fd=directory_fd)
                stack.callback(os.close, directory_fd)
            if not parts:
                info = os.fstat(directory_fd)
                entry["exists"] = True
                return entry
            fd = os.open(
                parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd
            )
            stack.callback(os.close, fd)
        except FileNotFoundError:
            return entry
        except OSError as exc:
            raise ValueError("artifact_path is outside configured safe directories") from exc

        info = os.fstat(fd)
        entry["exists"] = True
        if stat.S_ISREG(info.st_mode):
            h = hashlib.sha256()
            with os.fdopen(os.dup(fd), "rb") as file:
                for chunk in iter(lambda: file.read(1024 * 1024), b""):
                    h.update(chunk)
            entry.update({"size_bytes": info.st_size, "sha256": h.hexdigest()})
    return entry


def build_reproducibility_manifest(
    *,
    workflow: str,
    settings: dict,
    artifacts: Iterable[Path],
    artifact_roots: Iterable[Path],
    dataset: dict | None = None,
) -> dict:
    roots = tuple(
        (Path(root), confine_path(root, root, allow_root=True)) for root in artifact_roots
    )
    entries = []
    for artifact in artifacts:
        for root, canonical_root in roots:
            try:
                path = confine_path(artifact, root, allow_root=True)
            except ValueError:
                continue
            entries.append(_artifact_entry(path, canonical_root))
            break
        else:
            raise ValueError("artifact_path is outside configured safe directories")
    return {
        "manifest_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "workflow": workflow,
        "dataset": dataset or {},
        "settings": settings,
        "artifacts": entries,
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "external_binaries": {n: binary_version(n) for n in ("ffmpeg", "exiftool", "colmap")},
    }
