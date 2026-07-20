from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from backend.core.config import AppConfig
from backend.db.models import Reconstruction
from backend.db.models import Session as SessionModel

# ---- Policy model ----------------------------------------------------------


class PolicyRule:
    """A single cleanup rule.  Set exactly one of *age_days* or *disk_pct*."""

    def __init__(
        self,
        *,
        target: str,
        age_days: int | None = None,
        disk_pct: float | None = None,
    ):
        has_age = age_days is not None
        has_disk = disk_pct is not None
        if (not has_age and not has_disk) or (has_age and has_disk):
            raise ValueError("Set exactly one of age_days or disk_pct")
        self.target = target
        self.age_days = age_days
        self.disk_pct = disk_pct


# ---- Candidate discovery ----------------------------------------------------


def _configured_roots(cfg: AppConfig) -> tuple[Path, ...]:
    return (
        Path(cfg.processed_dir).resolve(),
        Path(cfg.exports_dir).resolve(),
        Path(cfg.data_dir).resolve(),
        Path(cfg.imports_dir).resolve(),
    )


def _is_relative_to_any(path: Path, roots: tuple[Path, ...]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    return any(resolved == root or resolved.is_relative_to(root) for root in roots)


def _size_of(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _archive_root(cfg: AppConfig) -> Path:
    return Path(cfg.exports_dir).resolve() / "storage_archive"


def _archive_destination(path: Path, cfg: AppConfig) -> Path:
    resolved = path.resolve()
    for root in _configured_roots(cfg):
        if resolved == root or resolved.is_relative_to(root):
            rel = resolved.relative_to(root)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            return _archive_root(cfg) / stamp / root.name / rel
    raise ValueError("path is outside configured storage roots")


def _make_cutoff(rule: PolicyRule) -> datetime | None:
    if rule.age_days is None:
        return None
    return datetime.now(timezone.utc) - timedelta(days=rule.age_days)


def _age_from_dt(dt: datetime) -> int:
    return (datetime.now(timezone.utc) - dt.replace(tzinfo=timezone.utc)).days


def _age_from_file(path: Path) -> int:
    mtime = path.stat().st_mtime
    return (datetime.now(timezone.utc) - datetime.fromtimestamp(mtime, tz=timezone.utc)).days


def _discover_candidates(
    rule: PolicyRule,
    cfg: AppConfig,
    db: DBSession,
) -> list[dict]:
    """Return a list of candidate items with path, bytes, reason, action."""
    roots = _configured_roots(cfg)
    candidates: list[dict] = []
    cutoff = _make_cutoff(rule)

    if rule.target == "raw_frames":
        imports = Path(cfg.imports_dir).resolve()
        if not imports.exists():
            return candidates

        for session_dir in sorted(imports.iterdir()):
            if not session_dir.is_dir():
                continue
            session = (
                db.query(SessionModel)
                .filter(SessionModel.folder_path.like(f"%{session_dir.name}%"))
                .first()
            )
            if session and session.imported_at:
                age = _age_from_dt(session.imported_at)
            else:
                age = _age_from_file(session_dir)

            if cutoff is not None and rule.age_days is not None and age <= rule.age_days:
                continue

            size = _size_of(session_dir)
            if size == 0:
                continue

            reason = (
                f"Age {age}d > {rule.age_days}d threshold"
                if rule.age_days is not None
                else f"Disk pressure {rule.disk_pct}%"
            )
            candidates.append(
                {
                    "path": str(session_dir.resolve()),
                    "bytes": size,
                    "reason": reason,
                    "action": "archive" if rule.age_days is not None else "delete",
                    "directory": True,
                }
            )

    elif rule.target == "colmap_intermediates":
        processed = Path(cfg.processed_dir).resolve()
        if not processed.exists():
            return candidates

        for session_dir in sorted(processed.iterdir()):
            if not session_dir.is_dir():
                continue
            colmap_dir = session_dir / "colmap"
            if not colmap_dir.is_dir():
                continue
            age = _age_from_file(colmap_dir)
            if cutoff is not None and rule.age_days is not None and age <= rule.age_days:
                continue
            size = _size_of(colmap_dir)
            if size == 0:
                continue
            reason = (
                f"Age {age}d > {rule.age_days}d threshold"
                if rule.age_days
                else f"Disk pressure {rule.disk_pct}%"
            )
            candidates.append(
                {
                    "path": str(colmap_dir.resolve()),
                    "bytes": size,
                    "reason": reason,
                    "action": "delete",
                    "directory": True,
                }
            )

    elif rule.target == "reconstruction_artifacts":
        recs = db.query(Reconstruction).filter(Reconstruction.status == "complete").all()

        for rec in recs:
            if not rec.completed_at:
                continue
            age = _age_from_dt(rec.completed_at)
            if cutoff is not None and rule.age_days is not None and age <= rule.age_days:
                continue

            artifact_paths = [
                rec.splat_path,
                rec.splat_preview_path,
                rec.splat_medium_path,
                rec.pointcloud_path,
                rec.mesh_glb_path,
                rec.mesh_obj_path,
                rec.mesh_mtl_path,
                rec.flythrough_path,
                rec.coverage_gaps_path,
            ]
            for artifact_raw in artifact_paths:
                if not artifact_raw:
                    continue
                p = Path(artifact_raw)
                if not p.exists():
                    continue
                try:
                    resolved = p.resolve()
                except OSError:
                    continue
                if not _is_relative_to_any(resolved, roots):
                    continue
                size = p.stat().st_size if p.is_file() else _size_of(p)
                reason = (
                    f"Reconstruction #{rec.id} completed {age}d ago > {rule.age_days}d threshold"
                )
                candidates.append(
                    {
                        "path": str(resolved),
                        "bytes": size,
                        "reason": reason,
                        "action": "archive" if rule.age_days else "delete",
                        "directory": p.is_dir(),
                    }
                )

    return candidates


# ---- Disk-pressure check ----------------------------------------------------


def _disk_usage_pct(path: str) -> float:
    """Return disk usage percentage for the filesystem containing *path*."""
    usage = shutil.disk_usage(path)
    return (usage.used / usage.total) * 100.0


# ---- Apply / dry-run --------------------------------------------------------


def apply_policy(
    rules: list[dict],
    *,
    execute: bool = False,
    cfg: AppConfig | None = None,
    db: DBSession | None = None,
) -> dict:
    """Apply (or dry-run) storage lifecycle rules.

    *rules*: list of dicts with keys ``target`` (str), ``age_days`` (int|None),
    ``disk_pct`` (float|None).  ``cfg`` and ``db`` are injected; callers that
    don't pass them must ensure the global config/DB are accessible.

    Returns a dict with ``mode``, ``candidates`` list, and ``summary``.
    """
    if cfg is None:
        from backend.core.config import get_config  # noqa: PLC0415

        cfg = get_config()

    # Parse rules
    parsed_rules: list[PolicyRule] = []
    for r in rules:
        target = r.get("target", "")
        valid = {"raw_frames", "colmap_intermediates", "reconstruction_artifacts"}
        if target not in valid:
            return {"error": f"Unknown target: {target}"}
        age_days = r.get("age_days")
        disk_pct = r.get("disk_pct")
        try:
            parsed_rules.append(
                PolicyRule(
                    target=target,
                    age_days=int(age_days) if age_days is not None else None,
                    disk_pct=float(disk_pct) if disk_pct is not None else None,
                )
            )
        except (ValueError, TypeError):
            return {"error": "Invalid storage-policy rule"}

    all_candidates: list[dict] = []
    if db is None:
        if execute:
            return {"error": "db session required for execute mode"}
    else:
        for rule in parsed_rules:
            if rule.disk_pct is not None:
                usage = _disk_usage_pct(cfg.data_dir)
                if usage < rule.disk_pct:
                    continue
                rule.age_days = 0

            all_candidates.extend(_discover_candidates(rule, cfg, db))

    total_bytes = sum(c["bytes"] for c in all_candidates)
    actions: dict[str, int] = {}
    for c in all_candidates:
        actions[c["action"]] = actions.get(c["action"], 0) + 1

    result: dict = {
        "mode": "execute" if execute else "dry-run",
        "candidates": all_candidates,
        "summary": {
            "total_items": len(all_candidates),
            "total_bytes": total_bytes,
            "actions": actions,
        },
    }

    if execute:
        if db is None:
            return {"error": "db session required for execute mode"}
        removed: list[str] = []
        archived: list[dict] = []
        failed: list[dict] = []
        roots = _configured_roots(cfg)

        for cand in all_candidates:
            p = Path(cand["path"])
            if not p.exists():
                removed.append(cand["path"])
                continue
            try:
                resolved = p.resolve()
            except OSError:
                failed.append({"path": cand["path"], "reason": "resolve error"})
                continue
            if not _is_relative_to_any(resolved, roots):
                failed.append({"path": str(resolved), "reason": "outside storage roots"})
                continue
            try:
                if cand.get("action") == "archive":
                    destination = _archive_destination(p, cfg)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(p), str(destination))
                    archived.append(
                        {
                            "path": str(resolved),
                            "archive_path": str(destination),
                        }
                    )
                else:
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
                    removed.append(str(resolved))
            except (OSError, ValueError):
                failed.append({"path": str(resolved), "reason": "operation failed"})

        result["executed"] = {"removed": removed, "archived": archived, "failed": failed}
        result["summary"]["removed_items"] = len(removed)
        result["summary"]["archived_items"] = len(archived)
        result["summary"]["failed_items"] = len(failed)

    return result
