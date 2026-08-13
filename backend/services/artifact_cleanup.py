from __future__ import annotations

import shutil
from pathlib import Path

from backend.core.config import AppConfig
from backend.core.paths import confine_path
from backend.db.models import Image, Reconstruction


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


def cleanup_reconstruction_artifacts(rec: Reconstruction, cfg: AppConfig) -> list[str]:
    """Remove on-disk artifacts owned by a reconstruction, constrained to app storage roots."""
    roots = _configured_roots(cfg)
    removed: list[str] = []

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
    candidates = [Path(value) for value in candidate_values if value]
    candidates.append(Path(cfg.exports_dir) / str(rec.id))

    seen: set[Path] = set()
    for path in sorted(candidates, key=lambda p: len(p.parts), reverse=True):
        resolved = path.resolve() if path.exists() else path.absolute()
        if resolved in seen:
            continue
        seen.add(resolved)
        if _remove_path(path, roots):
            removed.append(str(resolved))

    return removed


def cleanup_session_artifacts(
    session_id: int,
    images: list[Image],
    reconstructions: list[Reconstruction],
    cfg: AppConfig,
) -> list[str]:
    """Remove thumbnails and reconstruction artifacts owned by a session."""
    roots = _configured_roots(cfg)
    removed: list[str] = []

    for rec in reconstructions:
        removed.extend(cleanup_reconstruction_artifacts(rec, cfg))

    candidates = [Path(img.thumb_path) for img in images if img.thumb_path]
    candidates.append(Path(cfg.processed_dir) / str(session_id) / "thumbs")

    seen: set[Path] = set()
    for path in sorted(candidates, key=lambda p: len(p.parts), reverse=True):
        resolved = path.resolve() if path.exists() else path.absolute()
        if resolved in seen:
            continue
        seen.add(resolved)
        if _remove_path(path, roots):
            removed.append(str(resolved))

    return removed
