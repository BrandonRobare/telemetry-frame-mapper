from __future__ import annotations

import threading
from datetime import datetime

import pytest

from backend.core.config import AppConfig, get_backup_schedule_config
from backend.services.artifact_backup_schedule import BackupScheduler, next_daily_run


class Clock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _scheduler(clock: Clock, backup, **schedule) -> BackupScheduler:
    return BackupScheduler(
        schedule={"enabled": True, "target": "nightly", "daily_at": "02:00", **schedule},
        backup_config={
            "local_destinations": [],
            "rclone_remote": "",
            "targets": {
                "nightly": {
                    "destination": "local",
                    "local_destination": "E:/telemetry-backups",
                    "artifacts": ["processed"],
                }
            },
        },
        cfg=AppConfig(),
        clock=clock,
        backup=backup,
    )


def test_next_daily_run_uses_the_next_occurrence():
    now = datetime(2026, 7, 17, 2, 0)
    assert next_daily_run(now, "02:00") == datetime(2026, 7, 18, 2, 0)
    assert next_daily_run(now, "03:30") == datetime(2026, 7, 17, 3, 30)
    with pytest.raises(ValueError, match="HH:MM"):
        next_daily_run(now, "2:00")


def test_disabled_schedule_stays_idle_and_has_safe_status(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("backup:\n  schedule:\n    enabled: false\n")
    assert get_backup_schedule_config(str(path))["enabled"] is False

    called = False

    def backup(**kwargs):
        nonlocal called
        called = True
        return {}

    scheduler = _scheduler(Clock(datetime(2026, 7, 17, 1, 0)), backup, enabled=False)
    scheduler.start()
    assert scheduler.run_due() is False
    assert called is False
    assert scheduler.status() == {
        "enabled": False,
        "target": None,
        "daily_at": None,
        "running": False,
        "last_run": None,
        "next_run": None,
        "result": None,
    }


def test_scheduler_prevents_overlapping_runs():
    clock = Clock(datetime(2026, 7, 17, 1, 0))
    started = threading.Event()
    release = threading.Event()

    def backup(**kwargs):
        started.set()
        assert release.wait(1)
        return {"snapshot_id": "one"}

    scheduler = _scheduler(clock, backup)
    clock.value = datetime(2026, 7, 17, 2, 0)
    worker = threading.Thread(target=scheduler.run_due)
    worker.start()
    assert started.wait(1)
    assert scheduler.run_due() is False
    assert scheduler.status()["running"] is True
    release.set()
    worker.join(1)
    assert not worker.is_alive()


def test_scheduler_records_success_and_failure_without_secrets():
    clock = Clock(datetime(2026, 7, 17, 1, 0))
    scheduler = _scheduler(clock, lambda **kwargs: {"snapshot_id": "one", "token": "hidden"})

    clock.value = datetime(2026, 7, 17, 2, 0)
    assert scheduler.run_due() is True
    assert scheduler.status() == {
        "enabled": True,
        "target": "nightly",
        "daily_at": "02:00",
        "running": False,
        "last_run": "2026-07-17T02:00:00",
        "next_run": "2026-07-18T02:00:00",
        "result": {"status": "success", "snapshot_id": "one"},
    }

    clock.value = datetime(2026, 7, 18, 1, 0)
    failing = _scheduler(
        clock, lambda **kwargs: (_ for _ in ()).throw(RuntimeError("token=hidden"))
    )
    clock.value = datetime(2026, 7, 18, 2, 0)
    assert failing.run_due() is True
    assert failing.status()["result"] == {"status": "failed"}
