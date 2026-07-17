from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = REPO_ROOT / "alembic.ini"

def _default_database_url() -> str:
    return f"sqlite:///{(REPO_ROOT / 'data' / 'drone_mapping.db').as_posix()}"


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
    cfg = Config(str(ALEMBIC_INI_PATH))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    return cfg


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
        # cases because the baseline migration is idempotent.
        command.upgrade(cfg, "head")
