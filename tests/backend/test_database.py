from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import sqlalchemy as sa

from backend.db import database as database_module


def test_default_database_url_is_repo_rooted(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    expected = database_module.REPO_ROOT / "data" / "drone_mapping.db"

    assert database_module._default_database_url() == f"sqlite:///{expected.as_posix()}"


def test_frozen_bundle_uses_embedded_migrations_and_writable_working_data(
    monkeypatch, tmp_path
):
    bundle_root = tmp_path / "bundle"
    app_data = tmp_path / "app-data"
    app_data.mkdir()
    monkeypatch.setattr(database_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(database_module.sys, "_MEIPASS", str(bundle_root), raising=False)
    monkeypatch.chdir(app_data)

    assert database_module._alembic_ini_path() == bundle_root / "alembic.ini"
    assert database_module._default_database_url() == (
        f"sqlite:///{(app_data / 'data' / 'drone_mapping.db').as_posix()}"
    )


@pytest.fixture
def isolated_engine(monkeypatch, tmp_path):
    """Bind backend.db.database's module-level `engine`/`DATABASE_URL` to an
    isolated temp SQLite file for the duration of a test, without reloading
    any modules.

    Reloading backend.db.database/backend.db.models would create brand new
    `Base`/model classes distinct from the ones already imported by
    backend.main and tests/conftest.py (e.g. the `get_db` function object
    used as an app.dependency_overrides key), breaking the rest of the test
    session. Monkeypatching just the `engine`/`DATABASE_URL` attributes in
    place keeps `Base`/model identity intact while still pointing init_db()
    at a throwaway database.
    """
    db_path = tmp_path / "isolated.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    isolated_engine = sa.create_engine(db_url, connect_args={"check_same_thread": False})

    monkeypatch.setattr(database_module, "DATABASE_URL", db_url)
    monkeypatch.setattr(database_module, "engine", isolated_engine)

    try:
        yield isolated_engine
    finally:
        isolated_engine.dispose()


def test_init_db_creates_fresh_schema_and_stamps_head(isolated_engine):
    database_module.init_db()

    inspector = sa.inspect(isolated_engine)
    table_names = set(inspector.get_table_names())

    assert "reconstructions" in table_names
    assert "sessions" in table_names
    assert "alembic_version" in table_names

    with isolated_engine.connect() as conn:
        revision = conn.execute(sa.text("select version_num from alembic_version")).scalar()
    assert revision is not None


def test_init_db_upgrades_legacy_shimmed_db(isolated_engine):
    # Simulate a pre-Alembic database: build the full schema via create_all
    # (the old behavior), with no alembic_version table at all, then drop a
    # few of the columns that used to be patched on by the manual
    # ALTER TABLE shim.
    database_module.Base.metadata.create_all(bind=isolated_engine)

    shim_columns_to_drop = ["mesh_glb_path", "mesh_status", "flythrough_path"]
    # Drop job_queue table from the legacy schema since we're simulating
    # pre-job-queue state; the Alembic migration will recreate it properly.
    # The engine's NullPool (check_same_thread=False) makes it tricky to drop
    # across connections, so drop via a raw sqlite3 connection directly.
    db_path = str(isolated_engine.url).split("///")[1]
    raw_conn = sqlite3.connect(db_path)
    raw_conn.execute("DROP TABLE IF EXISTS job_queue")
    raw_conn.commit()
    raw_conn.close()
    with isolated_engine.begin() as conn:
        for col in shim_columns_to_drop:
            conn.execute(sa.text(f"ALTER TABLE reconstructions DROP COLUMN {col}"))

    inspector = sa.inspect(isolated_engine)
    existing_before = {col["name"] for col in inspector.get_columns("reconstructions")}
    for col in shim_columns_to_drop:
        assert col not in existing_before
    assert "alembic_version" not in inspector.get_table_names()

    database_module.init_db()

    inspector = sa.inspect(isolated_engine)
    existing_after = {col["name"] for col in inspector.get_columns("reconstructions")}
    for col in shim_columns_to_drop:
        assert col in existing_after
    assert "alembic_version" in inspector.get_table_names()


def test_legacy_upgrade_covers_every_model_column(isolated_engine):
    """An immutable v2.0.2 schema must upgrade to the complete current model schema."""
    schema = (
        Path(__file__).parent / "db" / "v2_0_2_schema.sql"
    ).read_text(encoding="utf-8")
    db_path = str(isolated_engine.url).split("///")[1]
    raw_conn = sqlite3.connect(db_path)
    try:
        raw_conn.executescript(schema)
        raw_conn.commit()
    finally:
        raw_conn.close()

    database_module.init_db()

    inspector = sa.inspect(isolated_engine)
    for table in database_module.Base.metadata.sorted_tables:
        actual_columns = {column["name"] for column in inspector.get_columns(table.name)}
        assert {column.name for column in table.columns} <= actual_columns


# The FK columns revision 0016 indexes, and the columns it deliberately leaves
# alone (composite-PK leading columns, plus FKs nothing filters on).
FK_INDEXES = {
    "sessions": {"ix_sessions_project_id"},
    "images": {"ix_images_session_id"},
    "footprints": {"ix_footprints_image_id"},
    "flight_logs": {"ix_flight_logs_session_id"},
    "flight_log_points": {"ix_flight_log_points_flight_log_id"},
    "flight_entries": {"ix_flight_entries_session_id"},
    "session_log_entries": {"ix_session_log_entries_session_id"},
    "reconstructions": {
        "ix_reconstructions_session_id",
        "ix_reconstructions_parent_reconstruction_id",
    },
    "share_links": {"ix_share_links_reconstruction_id"},
    "annotations": {"ix_annotations_reconstruction_id"},
    "measurements": {"ix_measurements_reconstruction_id"},
    "defects": {"ix_defects_session_id"},
}


def _index_names(inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table)}


def test_fresh_db_indexes_the_filtered_foreign_key_columns(isolated_engine):
    database_module.init_db()

    inspector = sa.inspect(isolated_engine)
    for table, expected in FK_INDEXES.items():
        assert expected <= _index_names(inspector, table), table


def test_legacy_upgrade_indexes_foreign_keys_and_replays_cleanly(isolated_engine):
    """A v2.0.2 database gains the FK indexes, and 0016 can be replayed over them."""
    schema = (
        Path(__file__).parent / "db" / "v2_0_2_schema.sql"
    ).read_text(encoding="utf-8")
    db_path = str(isolated_engine.url).split("///")[1]
    raw_conn = sqlite3.connect(db_path)
    try:
        raw_conn.executescript(schema)
        raw_conn.commit()
    finally:
        raw_conn.close()

    database_module.init_db()

    inspector = sa.inspect(isolated_engine)
    for table, expected in FK_INDEXES.items():
        assert expected <= _index_names(inspector, table), table

    # Rewind the stamp so 0016 runs a second time against a database that
    # already carries every index it creates: it must be a no-op, not a
    # "index already exists" failure.
    with isolated_engine.begin() as conn:
        conn.execute(sa.text("update alembic_version set version_num = '0015'"))

    database_module.init_db()

    inspector = sa.inspect(isolated_engine)
    for table, expected in FK_INDEXES.items():
        assert expected <= _index_names(inspector, table), table


def test_init_db_is_idempotent(isolated_engine):
    database_module.init_db()
    # Calling init_db() a second time against the same, now-migrated database
    # must not raise (this is the case most likely to break: re-running the
    # baseline migration's add_column/create_table calls against a DB that
    # already has them).
    database_module.init_db()

    inspector = sa.inspect(isolated_engine)
    assert "reconstructions" in inspector.get_table_names()
    assert "alembic_version" in inspector.get_table_names()


# --- pre-migration snapshots (#680) -----------------------------------------


def _revision(db_path: Path) -> str | None:
    """Read alembic_version straight from a SQLite file, engine uninvolved."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "select version_num from alembic_version"
        ).fetchone()
    except sqlite3.OperationalError:  # no alembic_version table at all
        return None
    finally:
        conn.close()
    return row[0] if row else None


def _rewind_to_pending(isolated_engine) -> Path:
    """Build a migrated database, then rewind its stamp so one revision is pending."""
    database_module.init_db()
    with isolated_engine.begin() as conn:
        conn.execute(sa.text("update alembic_version set version_num = '0015'"))
    return Path(isolated_engine.url.database)


def test_fresh_database_takes_no_pre_migration_snapshot(isolated_engine, tmp_path):
    database_module.init_db()

    assert not (tmp_path / "pre-migration").exists()


def test_database_at_head_takes_no_pre_migration_snapshot(isolated_engine, tmp_path):
    database_module.init_db()
    # Second startup against an up-to-date database: nothing to migrate, so
    # nothing to snapshot — an install that never migrates must not pay the
    # copy cost on every start.
    database_module.init_db()

    assert not (tmp_path / "pre-migration").exists()


def test_pending_migration_is_snapshotted_before_the_upgrade_runs(
    isolated_engine, tmp_path, monkeypatch
):
    db_path = _rewind_to_pending(isolated_engine)
    snapshot_dir = tmp_path / "pre-migration"
    seen: list[list[Path]] = []

    real_upgrade = database_module.command.upgrade

    def recording_upgrade(cfg, revision):
        seen.append(sorted(snapshot_dir.glob("*.db")) if snapshot_dir.exists() else [])
        return real_upgrade(cfg, revision)

    monkeypatch.setattr(database_module.command, "upgrade", recording_upgrade)

    database_module.init_db()

    # Ordering, not just existence: the snapshot was already on disk at the
    # moment alembic was asked to upgrade.
    assert len(seen) == 1
    assert len(seen[0]) == 1
    snapshot = seen[0][0]
    assert snapshot.parent == snapshot_dir
    # And it holds the pre-upgrade state, not a copy taken afterwards.
    assert _revision(snapshot) == "0015"
    assert _revision(db_path) not in (None, "0015")


def test_pre_migration_snapshots_keep_the_newest_and_evict_the_oldest(
    isolated_engine, tmp_path, monkeypatch
):
    import backend.core.config as config_module

    monkeypatch.setattr(
        config_module, "get_backup_config", lambda *args, **kwargs: {"pre_migration_keep": 2}
    )
    _rewind_to_pending(isolated_engine)
    snapshot_dir = tmp_path / "pre-migration"
    snapshot_dir.mkdir()
    # Timestamped names sort chronologically; oldest first.
    older = [snapshot_dir / f"isolated-2020010{n}T000000.000000Z.db" for n in (1, 2, 3)]
    for path in older:
        path.write_bytes(b"")

    database_module.init_db()

    remaining = sorted(snapshot_dir.glob("*.db"))
    assert len(remaining) == 2
    assert remaining[0] == older[-1]  # newest of the pre-existing copies survives
    assert remaining[1].name.startswith("isolated-")
    assert remaining[1] not in older  # the copy just taken
    assert not older[0].exists()
    assert not older[1].exists()


def test_failed_snapshot_blocks_startup_and_leaves_the_database_unmigrated(
    isolated_engine, tmp_path, monkeypatch
):
    from backend.services import artifact_backup

    db_path = _rewind_to_pending(isolated_engine)

    def full_disk(source, destination):
        raise OSError("No space left on device")

    monkeypatch.setattr(artifact_backup, "copy_sqlite_database", full_disk)

    with pytest.raises(RuntimeError) as excinfo:
        database_module.init_db()

    message = str(excinfo.value)
    assert "Could not snapshot the database before migrating it" in message
    assert "the app did not start" in message
    assert "No space left on device" in message
    # The migration must not have run behind the failed snapshot.
    assert _revision(db_path) == "0015"
