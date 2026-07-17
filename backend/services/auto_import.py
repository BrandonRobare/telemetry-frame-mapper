from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from ..core.config import get_auto_import_config, get_ingest_config
from ..db.database import SessionLocal
from ..db.models import AutoImportRecord
from ..db.models import Session as SessionModel
from .ingest_orchestrator import start_import


def _accepted_suffixes() -> set[str]:
    extensions = get_ingest_config().get("accepted_extensions", [".jpg", ".jpeg"])
    return {
        extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        for extension in extensions
    }


def directory_fingerprint(folder: Path, suffixes: set[str]) -> str | None:
    """Return a stable metadata manifest for media directly inside *folder*."""
    entries: list[str] = []
    try:
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            stat = path.stat()
            entries.append(f"{path.name}\0{stat.st_size}\0{stat.st_mtime_ns}")
    except OSError:
        return None
    if not entries:
        return None
    return hashlib.sha256("\n".join(entries).encode()).hexdigest()


class AutoImportWatcher:
    """Small polling watcher for explicitly configured media roots."""

    def __init__(
        self,
        config_getter: Callable[[], dict] = get_auto_import_config,
        db_factory=SessionLocal,
        importer: Callable[[int, Path, object], None] = start_import,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config_getter = config_getter
        self._db_factory = db_factory
        self._importer = importer
        self._clock = clock
        self._observed: dict[str, tuple[str, float]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._status: dict = {"enabled": False, "running": False, "roots": []}

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="auto-import", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None
        with self._lock:
            self._status["running"] = False

    def status(self) -> dict:
        with self._lock:
            return {
                **self._status,
                "roots": [dict(root) for root in self._status.get("roots", [])],
            }

    def _run(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            delay = self._config_getter()["poll_interval_seconds"]
            self._stop.wait(delay)

    def poll_once(self) -> dict:
        config = self._config_getter()
        roots_status: list[dict] = []
        active_observations: set[str] = set()
        now = self._clock()

        if config["enabled"]:
            suffixes = _accepted_suffixes()
            for raw_root in config["roots"]:
                roots_status.append(
                    self._scan_root(
                        Path(raw_root).expanduser(),
                        suffixes,
                        config["stable_seconds"],
                        now,
                        active_observations,
                    )
                )

        self._observed = {
            key: value for key, value in self._observed.items() if key in active_observations
        }
        status = {
            "enabled": config["enabled"],
            "running": self._thread is not None and self._thread.is_alive(),
            "roots": roots_status,
            "last_scan_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._status = status
        return self.status()

    def _scan_root(
        self,
        root: Path,
        suffixes: set[str],
        stable_seconds: int,
        now: float,
        active_observations: set[str],
    ) -> dict:
        try:
            if not root.exists():
                return {"path": str(root), "status": "missing", "candidates": 0, "imported": 0}
            if not root.is_dir():
                return {"path": str(root), "status": "unsupported", "candidates": 0, "imported": 0}
            allowed_root = root.resolve()
        except (OSError, ValueError):
            return {"path": str(root), "status": "unsupported", "candidates": 0, "imported": 0}

        candidates: set[Path] = set()
        try:
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.lower() in suffixes:
                    folder = path.parent.resolve()
                    if folder.is_relative_to(allowed_root):
                        candidates.add(folder)
        except OSError:
            return {"path": str(root), "status": "unavailable", "candidates": 0, "imported": 0}

        imported = 0
        stable = 0
        for folder in sorted(candidates):
            fingerprint = directory_fingerprint(folder, suffixes)
            if fingerprint is None:
                continue
            key = str(folder)
            active_observations.add(key)
            previous = self._observed.get(key)
            if previous is None or previous[0] != fingerprint:
                self._observed[key] = (fingerprint, now)
                continue
            if now - previous[1] < stable_seconds:
                continue
            stable += 1
            if self._claim_and_start(fingerprint, folder):
                imported += 1

        return {
            "path": str(root),
            "status": "watching",
            "candidates": len(candidates),
            "stable": stable,
            "imported": imported,
        }

    def _claim_and_start(self, fingerprint: str, folder: Path) -> bool:
        db = self._db_factory()
        try:
            session = SessionModel(
                name=folder.name,
                folder_path=str(folder),
                imported_at=datetime.now(timezone.utc),
                photo_count=0,
                usable_count=0,
            )
            db.add(session)
            db.flush()
            db.add(
                AutoImportRecord(
                    fingerprint=fingerprint,
                    source_path=str(folder),
                    session_id=session.id,
                )
            )
            db.commit()
            session_id = session.id
        except IntegrityError:
            db.rollback()
            return False
        finally:
            db.close()
        self._importer(session_id, folder, self._db_factory)
        return True
