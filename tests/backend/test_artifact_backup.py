from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from backend.core.config import AppConfig
from backend.services.artifact_backup import BackupError, create_backup


def _inputs(tmp_path: Path) -> tuple[AppConfig, Path, Path, Path]:
    imports = tmp_path / "imports"
    processed = tmp_path / "processed"
    exports = tmp_path / "exports"
    data = tmp_path / "data"
    for directory in (imports, processed, exports, data):
        directory.mkdir()
    (processed / "result.ply").write_bytes(b"splat")
    (exports / "report.geojson").write_text('{"type":"FeatureCollection"}')

    database = data / "drone_mapping.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE backups (name TEXT)")
        connection.execute("INSERT INTO backups VALUES ('consistent')")
        connection.commit()
    finally:
        connection.close()

    config = tmp_path / "config.yaml"
    config.write_text("target_crs: EPSG:32617\napi_key: should-not-copy\n")
    return (
        AppConfig(
            imports_dir=str(imports),
            processed_dir=str(processed),
            exports_dir=str(exports),
            data_dir=str(data),
        ),
        config,
        database,
        tmp_path / "backup-target",
    )


def test_local_backup_is_versioned_checksummed_and_uses_sqlite_snapshot(tmp_path):
    cfg, config, database, target = _inputs(tmp_path)

    result = create_backup(
        destination="local",
        local_destination=str(target),
        artifacts=["processed", "exports"],
        cfg=cfg,
        config_path=config,
        database_path=database,
        backup_config={"local_destinations": [str(target)], "rclone_remote": ""},
    )

    snapshot = Path(result["destination"])
    manifest = json.loads((snapshot / "manifest.json").read_text())
    assert snapshot.name.startswith("artifact-backup-v1-")
    assert manifest["version"] == 1
    assert {entry["path"] for entry in manifest["files"]} == {
        "artifacts/exports/report.geojson",
        "artifacts/processed/result.ply",
        "config.yaml",
        "database/drone_mapping.db",
    }
    db_copy = snapshot / "database" / database.name
    connection = sqlite3.connect(db_copy)
    try:
        assert connection.execute("SELECT name FROM backups").fetchone() == ("consistent",)
    finally:
        connection.close()
    assert "should-not-copy" not in (snapshot / "config.yaml").read_text()
    assert (snapshot / "config.yaml").read_text().count("***REDACTED***") == 1
    db_entry = next(entry for entry in manifest["files"] if entry["path"].startswith("database/"))
    assert db_entry["sha256"] == hashlib.sha256(db_copy.read_bytes()).hexdigest()
    assert result["manifest_sha256"] == hashlib.sha256(
        (snapshot / "manifest.json").read_bytes()
    ).hexdigest()


def test_local_backup_rejects_destination_outside_allowlist(tmp_path):
    cfg, config, database, target = _inputs(tmp_path)

    with pytest.raises(ValueError, match="not an approved"):
        create_backup(
            destination="local",
            local_destination=str(tmp_path / "unapproved"),
            artifacts=[],
            cfg=cfg,
            config_path=config,
            database_path=database,
            backup_config={"local_destinations": [str(target)], "rclone_remote": ""},
        )


def test_local_backup_rejects_destination_inside_selected_artifacts(tmp_path):
    cfg, config, database, _ = _inputs(tmp_path)
    target = Path(cfg.exports_dir) / "backups"

    with pytest.raises(ValueError, match="inside selected artifact"):
        create_backup(
            destination="local",
            local_destination=str(target),
            artifacts=["exports"],
            cfg=cfg,
            config_path=config,
            database_path=database,
            backup_config={"local_destinations": [str(target)], "rclone_remote": ""},
        )


def test_rclone_backup_uses_copy_without_deletion_flags(tmp_path, monkeypatch):
    cfg, config, database, _ = _inputs(tmp_path)
    commands = []

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("backend.services.artifact_backup.subprocess.run", fake_run)

    result = create_backup(
        destination="rclone",
        artifacts=["exports"],
        cfg=cfg,
        config_path=config,
        database_path=database,
        backup_config={"local_destinations": [], "rclone_remote": "archive:telemetry"},
    )

    command, kwargs = commands[0]
    assert command[0:2] == ["rclone", "copy"]
    assert command[-1] == result["destination"]
    assert not any("delete" in argument or argument == "sync" for argument in command)
    assert kwargs == {"check": True, "capture_output": True, "text": True}


def test_rclone_failure_does_not_expose_command_output(tmp_path, monkeypatch):
    cfg, config, database, _ = _inputs(tmp_path)

    def fake_run(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr="token=secret")

    monkeypatch.setattr("backend.services.artifact_backup.subprocess.run", fake_run)

    with pytest.raises(BackupError, match="rclone copy failed") as error:
        create_backup(
            destination="rclone",
            artifacts=[],
            cfg=cfg,
            config_path=config,
            database_path=database,
            backup_config={"local_destinations": [], "rclone_remote": "archive:telemetry"},
        )
    assert "token" not in str(error.value)


def test_backup_endpoint_keeps_validation_and_runtime_errors_distinct(client, monkeypatch):
    response = client.post("/storage/backup", json={"destination": "local", "artifacts": []})
    assert response.status_code == 422

    def fail(**kwargs):
        raise BackupError("rclone copy failed")

    monkeypatch.setattr("backend.services.artifact_backup.create_backup", fail)
    response = client.post("/storage/backup", json={"destination": "rclone", "artifacts": []})
    assert response.status_code == 502
    assert response.json()["detail"] == "Backup could not be completed"
