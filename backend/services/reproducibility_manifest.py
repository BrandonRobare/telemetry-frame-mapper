from __future__ import annotations

import hashlib
import logging
import platform
import shutil
import subprocess
from collections.abc import Iterable
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


def build_reproducibility_manifest(
    *,
    workflow: str,
    settings: dict,
    artifacts: Iterable[Path],
    artifact_roots: Iterable[Path],
    dataset: dict | None = None,
) -> dict:
    roots = tuple(Path(root) for root in artifact_roots)
    entries = []
    for artifact in artifacts:
        for root in roots:
            try:
                path = confine_path(artifact, root, allow_root=True)
            except ValueError:
                continue
            entry = {"path": str(path), "exists": path.exists()}
            if path.is_file():
                h = hashlib.sha256()
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(chunk)
                entry.update({"size_bytes": path.stat().st_size, "sha256": h.hexdigest()})
            entries.append(entry)
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
