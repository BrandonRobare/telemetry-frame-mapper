from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.script import ScriptDirectory

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


# --- foreign-key rules for deletes (#945) -----------------------------------

V3_0_0_SCHEMA = Path(__file__).parent / "db" / "v3_0_0_schema.sql"

# Rows a v3.0.0 user can have: an auto-imported session, a dense re-run pair, and a
# comparison, plus every child table that references reconstructions. Reconstruction 11
# is only a re-run parent, 13 is only compared, and session 3 only holds an import claim,
# so each new rule can be exercised on its own after the upgrade.
V3_0_0_ROWS = """
    INSERT INTO sessions (id, name) VALUES (1, 'watched'), (2, 'surveyed'), (3, 'claim only');
    INSERT INTO images (id, session_id, filename, filepath) VALUES (1, 2, 'a.jpg', '/a.jpg');
    INSERT INTO auto_import_records (id, fingerprint, source_path, session_id)
        VALUES (1, 'fp-1', '/card/1', 1), (2, 'fp-3', '/card/3', 3);
    INSERT INTO reconstructions (id, session_id, status, splat_path) VALUES
        (10, 2, 'complete', '/exports/10/splat.ply'),
        (11, 2, 'complete', '/exports/11/splat.ply'),
        (13, 2, 'complete', '/exports/13/splat.ply');
    INSERT INTO reconstructions (id, session_id, parent_reconstruction_id, status)
        VALUES (12, 2, 11, 'complete');
    INSERT INTO reconstruction_frames (reconstruction_id, image_id) VALUES (10, 1), (12, 1);
    INSERT INTO annotations (reconstruction_id, label, lat, lon, alt_m) VALUES (10, 'pin', 1, 2, 3);
    INSERT INTO measurements (reconstruction_id, kind, points_json) VALUES (12, 'distance', '[]');
    INSERT INTO share_links (id, reconstruction_id, token_hash, expires_at)
        VALUES (1, 10, 'hash', '2030-01-01 00:00:00');
    INSERT INTO share_link_unlock_sessions (share_link_id, token_hash, expires_at)
        VALUES (1, 'unlock', '2030-01-01 00:00:00');
    INSERT INTO session_comparisons
        (id, session_a_id, session_b_id, reconstruction_a_id, reconstruction_b_id, status)
        VALUES (1, 2, 2, 10, 13, 'complete');
"""


def _enforce_foreign_keys(engine) -> None:
    """Turn enforcement on for every connection, exactly as the app's own engine does."""

    @sa.event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")


def _seed_v3_0_0(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(V3_0_0_SCHEMA.read_text(encoding="utf-8"))
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(V3_0_0_ROWS)
        conn.commit()
    finally:
        conn.close()


def _all_rows(db_path: Path) -> dict[str, list[tuple]]:
    conn = sqlite3.connect(db_path)
    try:
        tables = [
            name
            for (name,) in conn.execute(
                "select name from sqlite_master where type = 'table' "
                "and name not like 'sqlite_%' and name not like 'session_search%' "
                "and name != 'alembic_version'"
            )
        ]
        return {
            table: conn.execute(f"select * from {table} order by rowid").fetchall()
            for table in tables
        }
    finally:
        conn.close()


def _reflected_foreign_keys(inspector, table: str) -> list[tuple]:
    return sorted(
        (
            tuple(fk["constrained_columns"]),
            fk["referred_table"],
            (fk.get("options") or {}).get("ondelete"),
        )
        for fk in inspector.get_foreign_keys(table)
    )


def _model_foreign_keys(table: str) -> list[tuple]:
    return sorted(
        (tuple(column.name for column in fk.columns), fk.referred_table.name, fk.ondelete)
        for fk in database_module.Base.metadata.tables[table].foreign_key_constraints
    )


def test_fk_rule_migration_upgrades_a_v3_0_0_database_without_data_loss(isolated_engine):
    _enforce_foreign_keys(isolated_engine)
    db_path = Path(isolated_engine.url.database)
    _seed_v3_0_0(db_path)
    before = _all_rows(db_path)
    indexes_before = {
        table: _index_names(sa.inspect(isolated_engine), table)
        for table in ("reconstructions", "auto_import_records")
    }

    database_module.init_db()

    head = ScriptDirectory.from_config(database_module._alembic_config()).get_current_head()
    assert _revision(db_path) == head
    # Every row of every table survives, byte for byte.
    assert _all_rows(db_path) == before
    inspector = sa.inspect(isolated_engine)
    for table in database_module.Base.metadata.tables:
        assert _reflected_foreign_keys(inspector, table) == _model_foreign_keys(table), table
    claim_columns = {c["name"]: c for c in inspector.get_columns("auto_import_records")}
    assert claim_columns["session_id"]["nullable"] is True
    for table, names in indexes_before.items():
        assert _index_names(inspector, table) == names, table

    with isolated_engine.connect() as conn:
        # The rebuild runs with enforcement off; the pooled connection must get it back.
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        conn.exec_driver_sql("delete from sessions where id = 3")
        conn.exec_driver_sql("delete from reconstructions where id = 11")
        assert conn.exec_driver_sql(
            "select session_id from auto_import_records where id = 2"
        ).scalar() is None
        assert conn.exec_driver_sql(
            "select parent_reconstruction_id from reconstructions where id = 12"
        ).scalar() is None
        with pytest.raises(sa.exc.IntegrityError):
            conn.exec_driver_sql("delete from reconstructions where id = 13")
        conn.rollback()


def test_fk_rule_migration_replays_and_downgrades_cleanly(isolated_engine):
    _enforce_foreign_keys(isolated_engine)
    db_path = Path(isolated_engine.url.database)
    _seed_v3_0_0(db_path)
    database_module.init_db()
    upgraded = _all_rows(db_path)

    # Replaying the revision over a database that already has the rules is a no-op.
    with isolated_engine.begin() as conn:
        conn.execute(sa.text("update alembic_version set version_num = '0017'"))
    database_module.init_db()
    assert _all_rows(db_path) == upgraded

    # A detached import claim cannot satisfy the old NOT NULL column, so downgrading
    # drops it; every other row is kept.
    with isolated_engine.begin() as conn:
        conn.execute(sa.text("delete from sessions where id = 3"))
    command.downgrade(database_module._alembic_config(), "0017")

    inspector = sa.inspect(isolated_engine)
    assert _reflected_foreign_keys(inspector, "reconstructions") == sorted([
        (("parent_reconstruction_id",), "reconstructions", None),
        (("session_id",), "sessions", None),
    ])
    assert _reflected_foreign_keys(inspector, "auto_import_records") == [
        (("session_id",), "sessions", None)
    ]
    rows = _all_rows(db_path)
    assert [row[0] for row in rows["auto_import_records"]] == [1]
    assert rows["reconstructions"] == upgraded["reconstructions"]
    with isolated_engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1

    database_module.init_db()
    head = ScriptDirectory.from_config(database_module._alembic_config()).get_current_head()
    assert _revision(db_path) == head


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
