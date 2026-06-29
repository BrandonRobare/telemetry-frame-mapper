from __future__ import annotations

import hashlib
import platform
import shutil
import subprocess
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path


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
    except Exception as exc:
        version = f"unavailable: {exc}"
    return {"available": True, "path": path, "version": version}


def build_reproducibility_manifest(
    *, workflow: str, settings: dict, artifacts: Iterable[str | Path], dataset: dict | None = None
) -> dict:
    entries = []
    for raw in artifacts:
        p = Path(raw)
        entry = {"path": str(p), "exists": p.exists()}
        if p.is_file():
            entry.update({"size_bytes": p.stat().st_size, "sha256": sha256_file(p)})
        entries.append(entry)
    return {
        "manifest_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workflow": workflow,
        "dataset": dataset or {},
        "settings": settings,
        "artifacts": entries,
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "external_binaries": {n: binary_version(n) for n in ("ffmpeg", "exiftool", "colmap")},
    }
