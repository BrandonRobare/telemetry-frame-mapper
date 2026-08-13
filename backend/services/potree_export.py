from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from backend.core.paths import confine_path

from ..core.config import get_config


def _directory_prefix(root: str) -> str:
    return root if root.endswith(os.sep) else f"{root}{os.sep}"


def _converter_path() -> str:
    configured = os.environ.get("POTREE_CONVERTER")
    converter = configured or shutil.which("PotreeConverter")
    if converter and (configured is None or Path(converter).is_file() or shutil.which(converter)):
        return converter
    raise RuntimeError(
        "PotreeConverter is not available. Install PotreeConverter and add it to PATH, "
        "or set POTREE_CONVERTER to its executable path."
    )


def export_potree(source_path: Path, output_dir: Path) -> Path:
    """Convert an existing LAS/LAZ file into a Potree-compatible output directory."""
    exports_root = Path(get_config().exports_dir)
    try:
        source_path = confine_path(source_path, exports_root, allow_root=True)
        output_dir = confine_path(output_dir, exports_root, allow_root=True)
    except ValueError as exc:
        raise ValueError("Potree paths must be inside the exports directory") from exc
    if source_path.suffix.lower() not in {".las", ".laz"}:
        raise ValueError("Potree export requires a LAS or LAZ point cloud")
    if not source_path.is_file():
        raise FileNotFoundError("LAS point cloud file not found on disk")

    metadata_path = output_dir / "metadata.json"
    if metadata_path.is_file():
        return metadata_path

    output_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [_converter_path(), str(source_path), "-o", str(output_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"PotreeConverter failed: {detail or f'exit code {result.returncode}'}")
    if not metadata_path.is_file():
        raise RuntimeError("PotreeConverter finished without creating metadata.json")
    return metadata_path
