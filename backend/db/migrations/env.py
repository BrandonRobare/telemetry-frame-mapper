from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from logging.config import fileConfig

from alembic import context
from alembic.runtime.migration import MigrationInfo
from sqlalchemy.engine import Connection

from backend.db import models  # noqa: F401  (registers all models on Base.metadata)
from backend.db.database import Base, engine

logger = logging.getLogger("backend.db.migrations")

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Point Alembic at the same database the app uses at runtime. Read fresh from
# the live `engine` (rather than caching DATABASE_URL at import time) so this
# stays correct if the module is reloaded with a different DATABASE_URL, e.g.
# under test.
config.set_main_option("sqlalchemy.url", str(engine.url))

# Interpret the config file for Python logging. `disable_existing_loggers` must
# stay off: init_db() runs this inside the app's own process, and the default
# would disable the already-configured "backend" logger for the rest of the
# process — silencing the JSONL application log on every startup that upgrades
# an existing database, which is exactly when an operator needs to read it.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def _warn_about_orphaned_rows(connection: Connection) -> None:
    """Log rows whose foreign key points at a missing row, without failing.

    SQLite's table-rebuild recipe ends with this check. It only warns because
    databases from before the app enforced foreign keys (v1.0.0 never did) can
    already hold such rows, and refusing to start over them would lock people
    out of their data. The rebuilds copy rows verbatim; they add no orphans.
    """
    violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    if not violations:
        return
    counts = Counter((table, parent) for table, _rowid, parent, _fk in violations)
    logger.warning(
        "The foreign-key check after migrating found %d row(s) that reference a "
        "missing row (%s). Startup continues; such rows usually predate foreign-key "
        "enforcement.",
        len(violations),
        ", ".join(
            f"{table} -> {parent}: {count}" for (table, parent), count in sorted(counts.items())
        ),
    )


@contextmanager
def _sqlite_foreign_keys_off(connection: Connection) -> Iterator[list[MigrationInfo]]:
    """Run the migrations with SQLite foreign-key enforcement off, then restore it.

    The app's engine enables ``PRAGMA foreign_keys`` on every connection. A
    revision that has to rebuild a table (``op.batch_alter_table``, SQLite's only
    way to add or drop a constrained column) drops the old table, and with
    enforcement on that DROP runs an implicit DELETE: it fails while other
    tables still reference the rows, and fires their ON DELETE CASCADE actions.
    SQLite ignores the pragma inside a transaction, so it is switched here,
    before the first revision opens one, as SQLite's own table-rebuild recipe
    prescribes. The prior setting is put back before the connection returns to
    the pool the app keeps using.

    Yields the list the caller fills with the steps Alembic applies. When a
    revision actually ran, the recipe's closing foreign-key check runs too; it
    is skipped otherwise, since init_db() calls this on every startup.
    """
    applied: list[MigrationInfo] = []
    if connection.dialect.name != "sqlite":
        yield applied
        return
    enforced = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    connection.commit()
    if connection.exec_driver_sql("PRAGMA foreign_keys").scalar():
        raise RuntimeError("Could not turn off SQLite foreign-key enforcement to migrate.")
    try:
        yield applied
        if enforced and any(not step.is_stamp for step in applied):
            _warn_about_orphaned_rows(connection)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        # Outside any transaction again, so the pragma takes effect.
        connection.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if enforced else 'OFF'}")
        connection.commit()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    with engine.connect() as connection, _sqlite_foreign_keys_off(connection) as applied:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            on_version_apply=lambda *, step, **_: applied.append(step),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
