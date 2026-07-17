from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from datetime import datetime, time, timedelta
from pathlib import Path

from backend.core.config import AppConfig, get_backup_config, get_backup_schedule_config

_SECRET_KEY = re.compile(r"(?:password|secret|token|credential|api[_-]?key)", re.IGNORECASE)


def next_daily_run(now: datetime, daily_at: str) -> datetime:
    """Return the next local daily occurrence of an HH:MM schedule."""
    if not re.fullmatch(r"\d{2}:\d{2}", daily_at):
        raise ValueError("backup.schedule.daily_at must be HH:MM")
    scheduled_time = time.fromisoformat(daily_at)
    candidate = now.replace(
        hour=scheduled_time.hour,
        minute=scheduled_time.minute,
        second=0,
        microsecond=0,
    )
    return candidate if candidate > now else candidate + timedelta(days=1)


class BackupScheduler:
    """One opt-in daily backup runner; its lock also guards manual test calls."""

    def __init__(
        self,
        *,
        schedule: dict,
        backup_config: dict,
        cfg: AppConfig,
        config_path: Path = Path("config.yaml"),
        clock: Callable[[], datetime] = datetime.now,
        backup: Callable[..., dict] | None = None,
    ):
        self._clock = clock
        self._cfg = cfg
        self._config_path = config_path
        self._backup_config = backup_config
        self._backup = backup or self._create_backup
        self._stop = threading.Event()
        self._run_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._enabled = bool(schedule.get("enabled", False))
        self._target_name = str(schedule.get("target", "")) if self._enabled else ""
        self._daily_at = str(schedule.get("daily_at", "02:00"))
        self._target: dict | None = None
        self._last_run: datetime | None = None
        self._result: dict | None = None
        self._next_run: datetime | None = None

        if not self._enabled:
            return
        targets = backup_config.get("targets", {})
        target = targets.get(self._target_name) if isinstance(targets, dict) else None
        if not isinstance(target, dict):
            self._result = {"status": "configuration_error"}
            return
        try:
            self._next_run = next_daily_run(self._clock(), self._daily_at)
        except ValueError:
            self._result = {"status": "configuration_error"}
            return
        self._target = target

    @staticmethod
    def _create_backup(**kwargs) -> dict:
        from backend.services.artifact_backup import create_backup

        return create_backup(**kwargs)

    @property
    def enabled(self) -> bool:
        return self._enabled and self._target is not None

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="artifact-backup-schedule", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def status(self) -> dict:
        with self._state_lock:
            return {
                "enabled": self.enabled,
                "target": self._target_name or None,
                "daily_at": self._daily_at if self.enabled else None,
                "running": self._run_lock.locked(),
                "last_run": self._last_run.isoformat() if self._last_run else None,
                "next_run": self._next_run.isoformat() if self._next_run else None,
                "result": self._result.copy() if self._result else None,
            }

    def run_due(self) -> bool:
        if not self.enabled or self._next_run is None or self._clock() < self._next_run:
            return False
        return self._run_once()

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._state_lock:
                next_run = self._next_run
            if next_run is None:
                return
            delay = max(0.0, (next_run - self._clock()).total_seconds())
            if self._stop.wait(delay):
                return
            self.run_due()

    def _run_once(self) -> bool:
        if not self._run_lock.acquire(blocking=False):
            return False
        try:
            started = self._clock()
            with self._state_lock:
                self._last_run = started
            try:
                target = self._target or {}
                result = self._backup(
                    destination=target.get("destination"),
                    local_destination=target.get("local_destination"),
                    artifacts=target.get("artifacts", ["processed", "exports"]),
                    cfg=self._cfg,
                    config_path=self._config_path,
                    backup_config=self._backup_config,
                )
            except Exception:
                logging.getLogger("backend").warning("Scheduled artifact backup failed")
                result = {"status": "failed"}
            else:
                result = {
                    **{key: value for key, value in result.items() if not _SECRET_KEY.search(key)},
                    "status": "success",
                }
            with self._state_lock:
                self._result = result
                self._next_run = next_daily_run(self._clock(), self._daily_at)
            return True
        finally:
            self._run_lock.release()


def scheduled_backup_from_config(
    cfg: AppConfig, config_path: Path = Path("config.yaml")
) -> BackupScheduler:
    """Build the singleton scheduler from the same config used by manual backups."""
    return BackupScheduler(
        schedule=get_backup_schedule_config(str(config_path)),
        backup_config=get_backup_config(str(config_path)),
        cfg=cfg,
        config_path=config_path,
    )
