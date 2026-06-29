"""baseline schema

Revision ID: 0001
Revises:
Create Date: 2026-06-22

Idempotent baseline migration. Handles two cases in one pass:

1. A genuinely fresh database with no tables at all: every table in
   ``Base.metadata`` is created.
2. An existing database created by the old hand-rolled
   ``_ensure_sqlite_schema`` / ``create_all`` path, which already has most
   tables but may be missing the mesh/flythrough columns that used to be
   added via manual ``ALTER TABLE`` statements. Only the columns that are
   actually missing are added.

Every operation is conditional on the current DB state via
``sa.inspect``, so re-running this migration (or running it against a
database that already matches the target schema) is a no-op.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from backend.db import models  # noqa: F401  (registers all models on Base.metadata)
from backend.db.database import Base

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Columns that used to be added on the fly by the old _ensure_sqlite_schema
# shim. Kept here explicitly (rather than diffing against models.py) so this
# migration's behavior is stable even if the model definition changes later.
_RECONSTRUCTIONS_SHIM_COLUMNS: dict[str, sa.types.TypeEngine] = {
    "mesh_glb_path": sa.String(),
    "mesh_obj_path": sa.String(),
    "mesh_mtl_path": sa.String(),
    "mesh_status": sa.String(),
    "mesh_error": sa.String(),
    "flythrough_path": sa.String(),
    "flythrough_status": sa.String(),
    "flythrough_error": sa.String(),
}

_IMAGES_CALIBRATION_COLUMNS: dict[str, sa.types.TypeEngine] = {
    "camera_make": sa.String(),
    "camera_model": sa.String(),
    "lens_model": sa.String(),
    "focal_length_35mm": sa.Float(),
    "digital_zoom_ratio": sa.Float(),
}

_IMAGE_FLIGHT_LOG_SYNC_COLUMNS: dict[str, sa.types.TypeEngine] = {
    "original_latitude": sa.Float(),
    "original_longitude": sa.Float(),
    "original_altitude_m": sa.Float(),
    "synced_latitude": sa.Float(),
    "synced_longitude": sa.Float(),
    "synced_altitude_m": sa.Float(),
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Case 1: create any table that doesn't already exist yet (covers both
    # a fresh DB and partially-created ones).
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            table.create(bind=bind)

    # Case 2: backfill any columns missing from pre-existing legacy tables.
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()
    if "reconstructions" in table_names:
        existing_columns = {col["name"] for col in inspector.get_columns("reconstructions")}
        for name, col_type in _RECONSTRUCTIONS_SHIM_COLUMNS.items():
            if name not in existing_columns:
                op.add_column("reconstructions", sa.Column(name, col_type))

    if "images" in table_names:
        existing_columns = {col["name"] for col in inspector.get_columns("images")}
        for column_group in (_IMAGES_CALIBRATION_COLUMNS, _IMAGE_FLIGHT_LOG_SYNC_COLUMNS):
            for name, col_type in column_group.items():
                if name not in existing_columns:
                    op.add_column("images", sa.Column(name, col_type))
                    existing_columns.add(name)


def downgrade() -> None:
    # This is the baseline revision for a hobby project with no production
    # migration history to preserve; downgrading below it is not supported.
    pass
