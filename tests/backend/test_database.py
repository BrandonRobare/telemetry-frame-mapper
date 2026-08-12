from __future__ import annotations

import sqlite3

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
    """An upgraded legacy database must satisfy the complete current model schema."""
    database_module.Base.metadata.create_all(bind=isolated_engine)
    db_path = str(isolated_engine.url).split("///")[1]
    raw_conn = sqlite3.connect(db_path)
    try:
        for table, column in (
            ("footprints", "pitch_oblique"),
            ("reconstructions", "ortho_path"),
            ("reconstructions", "ortho_status"),
            ("reconstructions", "ortho_error"),
        ):
            raw_conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        raw_conn.commit()
    finally:
        raw_conn.close()

    database_module.init_db()

    inspector = sa.inspect(isolated_engine)
    for table in database_module.Base.metadata.sorted_tables:
        actual_columns = {column["name"] for column in inspector.get_columns(table.name)}
        assert {column.name for column in table.columns} <= actual_columns


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
