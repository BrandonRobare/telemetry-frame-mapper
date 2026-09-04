from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml

from backend.core.config import AppConfig, get_backup_config
from backend.core.paths import confine_path

ARTIFACT_DIRECTORIES = frozenset({"imports", "processed", "exports"})
_RCLONE_REMOTE = re.compile(r"^[A-Za-z0-9_.-]+:(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]*$")
_SECRET_KEY = re.compile(r"(?:password|secret|token|credential|api[_-]?key)", re.IGNORECASE)


class BackupError(RuntimeError):
    """A backup could not be completed without exposing command output."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_config(value):
    if isinstance(value, dict):
        return {
            key: ("***REDACTED***" if _SECRET_KEY.search(key) else _safe_config(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_safe_config(item) for item in value]
    return value


def _write_sanitized_config(source: Path, destination: Path) -> None:
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise BackupError("Configuration file is missing") from exc
    if not isinstance(raw, dict):
        raise BackupError("Configuration file must contain a mapping")
    destination.write_text(
        yaml.safe_dump(_safe_config(raw), sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def sqlite_database_path() -> Path:
    """Resolve the file backing the database.

    The engine is looked up at call time, not import time: backend.db.database
    imports this module back (locally, to snapshot before migrating), and a
    live lookup also honours a rebound engine.
    """
    from backend.db.database import engine

    if (
        engine.dialect.name != "sqlite"
        or not engine.url.database
        or engine.url.database == ":memory:"
    ):
        raise BackupError("Artifact backup requires a file-backed SQLite database")
    return Path(engine.url.database).resolve()


def copy_sqlite_database(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise BackupError("SQLite database is missing")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_db = sqlite3.connect(source)
    destination_db = sqlite3.connect(destination)
    try:
        source_db.backup(destination_db)
    finally:
        destination_db.close()
        source_db.close()


def _copy_artifacts(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    source_root = source.resolve()
    for candidate in source.rglob("*"):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        try:
            confine_path(candidate, source_root)
        except ValueError:
            continue
        target = destination / candidate.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate, target)


def _manifest_files(snapshot: Path) -> list[dict]:
    return [
        {
            "path": path.relative_to(snapshot).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(snapshot.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    ]


def verify_backup(snapshot: Path) -> dict:
    """Re-hash a snapshot against its own manifest and return that manifest.

    Restoring is only safe once this passes: any recorded file that is missing,
    resized, or re-hashed differently rejects the whole snapshot, as does any
    file the manifest does not record.
    """
    snapshot = snapshot.resolve()
    try:
        manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BackupError("Backup manifest is missing or unreadable") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != "telemetry-frame-mapper-artifact-backup"
        or manifest.get("version") != 1
        or not isinstance(manifest.get("files"), list)
    ):
        raise BackupError("Backup manifest is not a version 1 artifact backup")

    recorded: set[str] = set()
    for entry in manifest["files"]:
        try:
            relative = entry["path"]
            path = confine_path(snapshot / relative, snapshot)
        except (KeyError, TypeError, ValueError) as exc:
            raise BackupError("Backup manifest lists a file outside the snapshot") from exc
        if not path.is_file() or path.stat().st_size != entry.get("bytes"):
            raise BackupError(f"Backup file is missing or resized: {relative}")
        if _sha256(path) != entry.get("sha256"):
            raise BackupError(f"Backup file failed checksum verification: {relative}")
        recorded.add(relative)

    present = {
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    unexpected = sorted(present - recorded)
    if unexpected:
        raise BackupError(f"Backup holds files the manifest does not record: {unexpected}")
    return manifest


def _snapshot_name() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"artifact-backup-v1-{stamp}-{uuid4().hex[:8]}"


def _approved_local_destination(value: str | None, allowed: list, config_path: Path) -> Path:
    if not value:
        raise ValueError(
            "local_destination must match a configured backup.local_destinations entry"
        )
    config_dir = os.path.normpath(os.path.realpath(config_path.parent))
    approved: list[Path] = []
    for candidate in allowed:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        path = os.path.expanduser(candidate)
        approved.append(Path(os.path.normpath(os.path.realpath(os.path.join(config_dir, path)))))
    requested = os.path.expanduser(value)
    requested = os.path.normpath(os.path.realpath(os.path.join(config_dir, requested)))
    for path in approved:
        if requested == os.path.normpath(os.path.realpath(path)):
            return path
    raise ValueError("local_destination is not an approved backup destination")


def _validated_rclone_remote(value: object) -> str:
    if not isinstance(value, str) or not _RCLONE_REMOTE.fullmatch(value):
        raise ValueError("backup.rclone_remote must be a configured rclone remote path")
    return value.rstrip("/")


def _build_snapshot(
    snapshot: Path,
    *,
    artifacts: list[str],
    cfg: AppConfig,
    config_path: Path,
    database_path: Path,
) -> dict:
    copy_sqlite_database(database_path, snapshot / "database" / database_path.name)
    _write_sanitized_config(config_path, snapshot / "config.yaml")
    roots = {
        "imports": Path(cfg.imports_dir),
        "processed": Path(cfg.processed_dir),
        "exports": Path(cfg.exports_dir),
    }
    for name in artifacts:
        _copy_artifacts(roots[name], snapshot / "artifacts" / name)

    manifest = {
        "format": "telemetry-frame-mapper-artifact-backup",
        "version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "snapshot_id": snapshot.name,
        "artifacts": artifacts,
        "files": _manifest_files(snapshot),
    }
    manifest_path = snapshot / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _result(snapshot: Path, manifest: dict, destination: str) -> dict:
    manifest_path = snapshot / "manifest.json"
    return {
        "snapshot_id": snapshot.name,
        "destination": destination,
        "file_count": len(manifest["files"]),
        "manifest_sha256": _sha256(manifest_path),
    }


def create_backup(
    *,
    destination: str,
    artifacts: list[str],
    local_destination: str | None = None,
    cfg: AppConfig,
    config_path: Path = Path("config.yaml"),
    database_path: Path | None = None,
    backup_config: dict | None = None,
) -> dict:
    """Create an additive, checksummed snapshot at an approved local or rclone destination."""
    if destination not in {"local", "rclone"}:
        raise ValueError("destination must be local or rclone")
    if any(name not in ARTIFACT_DIRECTORIES for name in artifacts):
        raise ValueError(f"artifacts must be selected from {sorted(ARTIFACT_DIRECTORIES)}")
    artifacts = list(dict.fromkeys(artifacts))
    config_path = config_path.resolve()
    database_path = (database_path or sqlite_database_path()).resolve()
    if backup_config is None:
        backup_config = get_backup_config(str(config_path))
    snapshot_name = _snapshot_name()

    if destination == "local":
        target = _approved_local_destination(
            local_destination, backup_config.get("local_destinations", []), config_path
        )
        selected_roots = [
            Path(getattr(cfg, f"{name}_dir")).resolve() for name in artifacts
        ]
        for root in selected_roots:
            try:
                confine_path(target, root, allow_root=True)
            except ValueError:
                continue
            raise ValueError("local_destination cannot be inside selected artifact storage")
        target.mkdir(parents=True, exist_ok=True)
        staging = target / f"{snapshot_name}.partial"
        snapshot = target / snapshot_name
        if staging.exists() or snapshot.exists():
            raise BackupError("Backup snapshot name collision")
        staging.mkdir()
        try:
            manifest = _build_snapshot(
                staging,
                artifacts=artifacts,
                cfg=cfg,
                config_path=config_path,
                database_path=database_path,
            )
            staging.rename(snapshot)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return _result(snapshot, manifest, str(snapshot))

    remote = _validated_rclone_remote(backup_config.get("rclone_remote"))
    # Keep staging outside configured artifact roots: otherwise selecting exports
    # would recursively copy the snapshot currently being built.
    with tempfile.TemporaryDirectory(prefix="artifact-backup-") as temporary:
        snapshot = Path(temporary) / snapshot_name
        snapshot.mkdir()
        manifest = _build_snapshot(
            snapshot,
            artifacts=artifacts,
            cfg=cfg,
            config_path=config_path,
            database_path=database_path,
        )
        remote_snapshot = f"{remote}/{snapshot_name}"
        try:
            subprocess.run(
                ["rclone", "copy", str(snapshot), remote_snapshot],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise BackupError("rclone copy failed") from exc
        result = _result(snapshot, manifest, remote_snapshot)
    return result


if __name__ == "__main__":  # Verification step of the restore procedure in docs/USER-MANUAL.md.
    import sys

    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m backend.services.artifact_backup <snapshot-directory>")
    directory = Path(sys.argv[1]).resolve()
    try:
        verified = verify_backup(directory)
    except BackupError as exc:
        raise SystemExit(f"backup verification failed: {exc}") from None
    # The directory name, not manifest["snapshot_id"]: a local snapshot is built
    # under a ".partial" staging name that the manifest still records.
    print(f"verified {len(verified['files'])} files in {directory.name}")
