from __future__ import annotations

from backend.db.models import AutoImportRecord, Session
from backend.services.auto_import import AutoImportWatcher
from tests.conftest import TestSessionLocal


def _watcher(config: dict, clock, calls: list[tuple[int, object]]) -> AutoImportWatcher:
    return AutoImportWatcher(
        config_getter=lambda: config,
        db_factory=TestSessionLocal,
        importer=lambda session_id, folder, _db_factory: calls.append((session_id, folder)),
        clock=lambda: clock[0],
    )


def _config(root, stable_seconds: int = 5) -> dict:
    return {
        "enabled": True,
        "roots": [str(root)],
        "poll_interval_seconds": 1,
        "stable_seconds": stable_seconds,
    }


def test_waits_for_a_media_directory_to_stabilize_before_import(tmp_path):
    root = tmp_path / "card"
    flight = root / "100MEDIA"
    flight.mkdir(parents=True)
    frame = flight / "DJI_0001.JPG"
    frame.write_bytes(b"first")
    clock = [0.0]
    calls: list[tuple[int, object]] = []
    watcher = _watcher(_config(root), clock, calls)

    first = watcher.poll_once()
    clock[0] = 4.0
    watcher.poll_once()
    assert calls == []
    assert first["roots"][0]["status"] == "watching"

    frame.write_bytes(b"changed")
    clock[0] = 6.0
    watcher.poll_once()
    clock[0] = 10.0
    watcher.poll_once()
    assert calls == []

    clock[0] = 11.0
    watcher.poll_once()
    assert len(calls) == 1
    assert calls[0][1] == flight.resolve()


def test_persisted_fingerprint_prevents_reimport_after_watcher_restart(tmp_path):
    root = tmp_path / "card"
    flight = root / "100MEDIA"
    flight.mkdir(parents=True)
    (flight / "DJI_0001.JPG").write_bytes(b"same media")
    clock = [0.0]
    first_calls: list[tuple[int, object]] = []
    first = _watcher(_config(root, stable_seconds=0), clock, first_calls)

    first.poll_once()
    first.poll_once()
    assert len(first_calls) == 1
    with TestSessionLocal() as db:
        assert db.query(AutoImportRecord).count() == 1
        assert db.query(Session).count() == 1

    restarted_calls: list[tuple[int, object]] = []
    restarted = _watcher(_config(root, stable_seconds=0), clock, restarted_calls)
    restarted.poll_once()
    restarted.poll_once()
    assert restarted_calls == []
    with TestSessionLocal() as db:
        assert db.query(AutoImportRecord).count() == 1
        assert db.query(Session).count() == 1


def test_missing_and_file_roots_are_reported_without_importing(tmp_path):
    missing = tmp_path / "not-mounted"
    unsupported = tmp_path / "card-image.img"
    unsupported.write_bytes(b"not a directory")
    clock = [0.0]
    calls: list[tuple[int, object]] = []
    watcher = _watcher(
        {**_config(missing), "roots": [str(missing), str(unsupported)]}, clock, calls
    )

    status = watcher.poll_once()

    assert calls == []
    assert [root["status"] for root in status["roots"]] == ["missing", "unsupported"]


def test_status_is_safe_when_auto_import_is_disabled(client, tmp_path):
    clock = [0.0]
    calls: list[tuple[int, object]] = []
    watcher = _watcher(
        {
            "enabled": False,
            "roots": [str(tmp_path)],
            "poll_interval_seconds": 1,
            "stable_seconds": 0,
        },
        clock,
        calls,
    )

    status = watcher.poll_once()

    assert status["enabled"] is False
    assert status["running"] is False
    assert status["roots"] == []
    assert calls == []

    from backend.main import app

    previous = getattr(app.state, "auto_import_watcher", None)
    try:
        app.state.auto_import_watcher = watcher
        response = client.get("/auto-import/status")
        assert response.status_code == 200
        assert response.json()["enabled"] is False
    finally:
        if previous is None:
            del app.state.auto_import_watcher
        else:
            app.state.auto_import_watcher = previous
