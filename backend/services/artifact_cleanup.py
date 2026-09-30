from __future__ import annotations

import logging
import shutil
from collections.abc import Iterable
from pathlib import Path

from backend.core.config import AppConfig
from backend.core.paths import confine_path
from backend.db.models import Image, Reconstruction

logger = logging.getLogger(__name__)


def _configured_roots(cfg: AppConfig) -> tuple[Path, ...]:
    return (
        Path(cfg.processed_dir).resolve(),
        Path(cfg.exports_dir).resolve(),
        Path(cfg.data_dir).resolve(),
    )


def _is_relative_to_any(path: Path, roots: tuple[Path, ...]) -> bool:
    for root in roots:
        try:
            confine_path(path, root, allow_root=True)
        except (OSError, RuntimeError, ValueError):
            continue
        return True
    return False


def _remove_path(path: Path, roots: tuple[Path, ...]) -> bool:
    if not _is_relative_to_any(path, roots) or not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True


def reconstruction_artifact_paths(rec: Reconstruction, cfg: AppConfig) -> list[Path]:
    """List the on-disk artifacts a reconstruction owns, while its row is still loaded."""
    candidate_values = [
        rec.colmap_dir,
        rec.splat_path,
        rec.splat_preview_path,
        rec.splat_medium_path,
        rec.thumb_path,
        rec.pointcloud_path,
        rec.mesh_glb_path,
        rec.mesh_obj_path,
        rec.mesh_mtl_path,
        rec.flythrough_path,
        rec.coverage_gaps_path,
    ]
    paths = [Path(value) for value in candidate_values if value]
    paths.append(Path(cfg.exports_dir) / str(rec.id))
    return paths


def session_artifact_paths(
    session_id: int,
    images: list[Image],
    reconstructions: list[Reconstruction],
    cfg: AppConfig,
) -> list[Path]:
    """List the thumbnails and reconstruction artifacts a session owns."""
    paths = [path for rec in reconstructions for path in reconstruction_artifact_paths(rec, cfg)]
    paths.extend(Path(img.thumb_path) for img in images if img.thumb_path)
    paths.append(Path(cfg.processed_dir) / str(session_id) / "thumbs")
    return paths


def remove_artifacts(paths: Iterable[Path], cfg: AppConfig) -> list[str]:
    """Remove artifacts whose rows were already deleted and committed, within app storage.

    Deletes remove rows first and files second (#945), so a failure here leaves an
    orphaned file on disk, never a row pointing at a missing one. Each failure is
    logged and the remaining paths are still removed.
    """
    roots = _configured_roots(cfg)
    removed: list[str] = []
    seen: set[Path] = set()
    for path in sorted(paths, key=lambda p: len(p.parts), reverse=True):
        resolved = path.resolve() if path.exists() else path.absolute()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            if _remove_path(path, roots):
                removed.append(str(resolved))
        except OSError as exc:
            logger.warning("Could not remove %s after deleting its record: %s", resolved, exc)
    return removed
