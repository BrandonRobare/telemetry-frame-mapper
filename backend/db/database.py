from __future__ import annotations

import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]

logger = logging.getLogger(__name__)


def _resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", REPO_ROOT))


def _runtime_root() -> Path:
    return Path.cwd() if getattr(sys, "frozen", False) else REPO_ROOT


def _alembic_ini_path() -> Path:
    return _resource_root() / "alembic.ini"

def _default_database_url() -> str:
    return f"sqlite:///{(_runtime_root() / 'data' / 'drone_mapping.db').as_posix()}"


DATABASE_URL = os.environ.get("DATABASE_URL", _default_database_url())

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _alembic_config() -> Config:
    cfg = Config(str(_alembic_ini_path()))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    return cfg


def _at_migration_head(cfg: Config) -> bool:
    """Report whether the database already sits at every migration head."""
    with engine.connect() as connection:
        current = set(MigrationContext.configure(connection).get_current_heads())
    return current == set(ScriptDirectory.from_config(cfg).get_heads())


def _snapshot_before_migrating() -> None:
    """Copy the database into ``pre-migration/`` beside it, newest ``keep`` kept.

    A failed snapshot is fatal on purpose: migrating with no rollback copy is
    exactly what this guard exists to prevent, so the app refuses to start
    rather than migrating blind (#680).
    """
    from backend.core.config import get_backup_config
    from backend.services.artifact_backup import copy_sqlite_database, sqlite_database_path

    started = time.perf_counter()
    try:
        database_path = sqlite_database_path()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        snapshot = database_path.parent / "pre-migration" / f"{database_path.stem}-{stamp}.db"
        copy_sqlite_database(database_path, snapshot)
        keep = get_backup_config().get("pre_migration_keep", 3)
        if not isinstance(keep, int) or isinstance(keep, bool) or keep < 1:
            keep = 3
        # Names are timestamped to the microsecond, so sorting them is chronological.
        for stale in sorted(snapshot.parent.glob(f"{database_path.stem}-*.db"))[:-keep]:
            stale.unlink(missing_ok=True)
    except Exception as exc:
        raise RuntimeError(
            "Could not snapshot the database before migrating it, so no migration was "
            "attempted and the app did not start. The snapshot is the only rollback copy, "
            "so it is not optional. Free disk space next to the database file, or fix the "
            f"permissions on its directory, then start again. Cause: {exc}"
        ) from exc
    logger.info(
        "Snapshotted the database to %s before migrating (%.2fs)",
        snapshot,
        time.perf_counter() - started,
    )


def init_db():
    from backend.db import models  # noqa: F401

    inspector = inspect(engine)
    is_fresh = "reconstructions" not in inspector.get_table_names()
    cfg = _alembic_config()

    if is_fresh:
        # Genuinely new database: create the full schema directly, then mark
        # it as already up to date so a later `alembic upgrade head` doesn't
        # try to replay the baseline against tables that already exist.
        Base.metadata.create_all(bind=engine)
        if engine.dialect.name == "sqlite":
            from backend.db.session_search import install_session_search_schema

            with engine.begin() as connection:
                install_session_search_schema(connection)
        command.stamp(cfg, "head")
    else:
        # Pre-existing database (legacy create_all/_ensure_sqlite_schema DB,
        # or one already managed by Alembic): upgrading is safe in both
        # cases because the baseline migration is idempotent. Snapshot it
        # first, but not on an up-to-date install, which would pay the copy
        # cost on every single startup for a migration that never runs.
        if engine.dialect.name == "sqlite" and not _at_migration_head(cfg):
            _snapshot_before_migrating()
        command.upgrade(cfg, "head")
