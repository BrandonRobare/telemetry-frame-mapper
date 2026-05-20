from __future__ import annotations

import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///./data/drone_mapping.db",
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from backend.db import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_schema()


def _ensure_sqlite_schema() -> None:
    """Add nullable columns needed by newer local builds to existing SQLite DBs."""
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if "reconstructions" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("reconstructions")}
    column_specs = {
        "mesh_glb_path": "VARCHAR",
        "mesh_obj_path": "VARCHAR",
        "mesh_mtl_path": "VARCHAR",
        "mesh_status": "VARCHAR",
        "mesh_error": "VARCHAR",
        "flythrough_path": "VARCHAR",
        "flythrough_status": "VARCHAR",
        "flythrough_error": "VARCHAR",
    }

    missing = [(name, spec) for name, spec in column_specs.items() if name not in existing]
    if not missing:
        return

    with engine.begin() as conn:
        for name, spec in missing:
            conn.execute(text(f"ALTER TABLE reconstructions ADD COLUMN {name} {spec}"))
