"""add semantic label columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-06
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: dict[str, sa.types.TypeEngine] = {
    "semantic_status": sa.String(),
    "semantic_error": sa.String(),
    "semantic_labels_path": sa.String(),
}

def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "reconstructions" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("reconstructions")}
    for name, col_type in _COLUMNS.items():
        if name not in existing:
            op.add_column("reconstructions", sa.Column(name, col_type))

def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "reconstructions" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("reconstructions")}
    for name in reversed(_COLUMNS):
        if name in existing:
            op.drop_column("reconstructions", name)
