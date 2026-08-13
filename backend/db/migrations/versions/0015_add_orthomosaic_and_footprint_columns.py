"""add orthomosaic and footprint columns

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-12
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: dict[str, dict[str, sa.types.TypeEngine]] = {
    "footprints": {"pitch_oblique": sa.Boolean()},
    "reconstructions": {
        "ortho_path": sa.String(),
        "ortho_status": sa.String(),
        "ortho_error": sa.String(),
    },
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table, columns in _COLUMNS.items():
        if table not in tables:
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, column_type in columns.items():
            if name not in existing:
                op.add_column(table, sa.Column(name, column_type))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table, columns in _COLUMNS.items():
        if table not in tables:
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name in reversed(columns):
            if name in existing:
                op.drop_column(table, name)
