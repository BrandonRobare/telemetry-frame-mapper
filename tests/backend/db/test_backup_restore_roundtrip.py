"""The documented restore procedure, executed end to end (#610).

Mirrors docs/USER-MANUAL.md "Restoring a snapshot": back up a v2.0.2 install,
verify the manifest, copy the database and artifacts into a fresh install, and
start the backend so `init_db()` migrates the restored database to head.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path

import sqlalchemy as sa
import yaml
from alembic.script import ScriptDirectory

from backend.core.config import AppConfig
from backend.db import database as database_module
from backend.services.artifact_backup import create_backup, verify_backup

LEGACY_SCHEMA = Path(__file__).parent / "v2_0_2_schema.sql"


def _install(root: Path) -> AppConfig:
    for name in ("imports", "processed", "exports", "data"):
        (root / name).mkdir(parents=True)
    return AppConfig(
        imports_dir=str(root / "imports"),
        processed_dir=str(root / "processed"),
        exports_dir=str(root / "exports"),
        data_dir=str(root / "data"),
    )


def test_snapshot_restores_into_a_fresh_install_and_reaches_migration_head(tmp_path, monkeypatch):
    live = _install(tmp_path / "live")
    (Path(live.processed_dir) / "cloud.ply").write_bytes(b"splat")
    (Path(live.exports_dir) / "report.geojson").write_text('{"type":"FeatureCollection"}')

    database = Path(live.data_dir) / "drone_mapping.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(LEGACY_SCHEMA.read_text(encoding="utf-8"))
        connection.execute("INSERT INTO projects (name) VALUES ('pre-upgrade')")
        connection.commit()
    finally:
        connection.close()

    config = tmp_path / "config.yaml"
    config.write_text("target_crs: EPSG:32617\napi_key:\n  enabled: false\n")

    target = tmp_path / "backups"
    snapshot = Path(
        create_backup(
            destination="local",
            local_destination=str(target),
            artifacts=["processed", "exports"],
            cfg=live,
            config_path=config,
            database_path=database,
            backup_config={"local_destinations": [str(target)], "rclone_remote": ""},
        )["destination"]
    )

    # Step 1: verify before restoring anything.
    verify_backup(snapshot)

    # Steps 2-3: copy the database and the artifacts into a fresh install.
    restored = _install(tmp_path / "restored")
    restored_database = Path(restored.data_dir) / database.name
    shutil.copy2(snapshot / "database" / database.name, restored_database)
    for name in ("processed", "exports"):
        shutil.copytree(
            snapshot / "artifacts" / name, getattr(restored, f"{name}_dir"), dirs_exist_ok=True
        )

    # Step 4: the snapshot's config is sanitized, so `api_key` came back as a
    # string and the file is not a drop-in replacement.
    assert yaml.safe_load((snapshot / "config.yaml").read_text())["api_key"] == "***REDACTED***"

    # Step 5: starting the backend migrates the restored database to head.
    url = f"sqlite:///{restored_database.as_posix()}"
    engine = sa.create_engine(url, connect_args={"check_same_thread": False})
    monkeypatch.setattr(database_module, "DATABASE_URL", url)
    monkeypatch.setattr(database_module, "engine", engine)
    try:
        database_module.init_db()

        # The upgrade must not silence the log the operator reads during recovery:
        # Alembic's env.py configures logging and would disable existing loggers.
        assert not logging.getLogger("backend").disabled

        head = ScriptDirectory.from_config(database_module._alembic_config()).get_current_head()
        with engine.connect() as conn:
            assert conn.execute(sa.text("select version_num from alembic_version")).scalar() == head
            assert conn.execute(sa.text("select name from projects")).scalar() == "pre-upgrade"

        inspector = sa.inspect(engine)
        for table in database_module.Base.metadata.sorted_tables:
            actual = {column["name"] for column in inspector.get_columns(table.name)}
            assert {column.name for column in table.columns} <= actual, table.name
    finally:
        engine.dispose()

    assert (Path(restored.processed_dir) / "cloud.ply").read_bytes() == b"splat"
    assert (Path(restored.exports_dir) / "report.geojson").exists()
