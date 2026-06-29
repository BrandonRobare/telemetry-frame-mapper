"""add flight log sync GPS columns

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IMAGE_SYNC_COLUMNS: dict[str, sa.types.TypeEngine] = {
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
    if "images" not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns("images")}
    for name, col_type in _IMAGE_SYNC_COLUMNS.items():
        if name not in existing_columns:
            op.add_column("images", sa.Column(name, col_type))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "images" not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns("images")}
    for name in reversed(_IMAGE_SYNC_COLUMNS):
        if name in existing_columns:
            op.drop_column("images", name)
