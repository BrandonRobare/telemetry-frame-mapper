from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from backend.db import models  # noqa: F401  (registers all models on Base.metadata)
from backend.db.database import Base, engine

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


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
